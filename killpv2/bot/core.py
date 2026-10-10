"""Bot core: long-polling dispatcher, keyboards, command list, state machine, owner notifications, alerts."""
import time
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from .. import settings
from .tg import Telegram, TgError, ik, rk, esc
from .i18n import t, KB_ACTIONS, norm_lang, fmt_num
from . import service as svc
from .service import Service
from .flows import Flows
from .payments import Payments
from .admin import Admin
from .ai_agent import SupportAgent

COMMANDS = ["start", "buy", "services", "wallet", "coins", "support", "lang", "help", "cancel"]


class Bot:
    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.tg = Telegram()
        self.svc = Service(app)
        app.bot = self
        self.flows = Flows(self)
        self.payments = Payments(self)
        self.admin = Admin(self)
        self.ai = SupportAgent(self)
        self.stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tg")
        self.ai_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ai")
        self._offset = None
        self._queues = {}          # uid -> pending updates (strict per-user ordering)
        self._active = set()       # uids currently being drained
        self._ql = threading.Lock()

    # ------------------------------------------------------------- roles
    def is_owner(self, tg_id):
        return int(tg_id) == settings.OWNER_ID

    def is_admin(self, tg_id):
        if self.is_owner(tg_id):
            return True
        u = self.store.tg_user(tg_id)
        return bool(u and u["is_admin"]) or int(tg_id) in set(svc.setting(self.store, svc.K_ADMINS) or [])

    def admin_ids(self):
        ids = {settings.OWNER_ID} | set(int(x) for x in svc.setting(self.store, svc.K_ADMINS) or [])
        ids |= {u["tg_id"] for u in self.store._rows("SELECT tg_id FROM tg_users WHERE is_admin=1")}
        return sorted(i for i in ids if i)

    # ------------------------------------------------------------- notifications
    def notify_owner(self, kind, text, force=False, skip=None):
        """Owner-only notification channel (respects per-kind toggles unless force)."""
        if not settings.OWNER_ID:
            return
        if skip == settings.OWNER_ID and not force:
            return
        n = dict(svc.DEFAULTS[svc.K_NOTIF])
        n.update(svc.setting(self.store, svc.K_NOTIF) or {})
        if not force and not n.get(kind, True):
            return
        try:
            self.tg.send(settings.OWNER_ID, text)
        except Exception as e:
            print(f"[bot] notify_owner failed: {e}", flush=True)

    def notify_admins(self, text):
        for aid in self.admin_ids():
            try:
                self.tg.send(aid, text)
            except Exception:
                pass

    # ------------------------------------------------------------- keyboards / commands
    def main_kb(self, user):
        L = user["lang"]
        rows = [[t(L, "kb.buy"), t(L, "kb.services")], [t(L, "kb.wallet"), t(L, "kb.coins")], [t(L, "kb.support"), t(L, "kb.help")],
                [t(L, "kb.lang")]]
        if self.is_admin(user["tg_id"]):
            rows[-1].append(t(L, "kb.admin"))
        return rk(rows)

    def support_kb(self, user):
        return rk([[t(user["lang"], "kb.end_support")]])

    def register_commands(self):
        for lang in settings.SUPPORTED_LANGS:
            cmds = [{"command": c, "description": t(lang, f"cmd.{c}")[:256]} for c in COMMANDS]
            try:
                self.tg.set_commands(cmds, language_code=None if lang == settings.DEFAULT_LANG else lang)
            except TgError as e:
                self.store.log("bot", f"setMyCommands({lang}) failed: {e}", "warn")
        for aid in self.admin_ids():
            try:
                cmds = [{"command": c, "description": t("fa", f"cmd.{c}")} for c in COMMANDS] + [{"command": "admin", "description": t("fa", "cmd.admin")}]
                self.tg.set_commands(cmds, scope={"type": "chat", "chat_id": aid})
            except TgError:
                pass

    # ------------------------------------------------------------- lifecycle
    def start(self):
        if not settings.BOT_ENABLED:
            self.store.log("bot", "disabled (BOT_TOKEN/OWNER_ID missing)", "warn")
            return False
        try:
            me = self.tg.get_me()
        except Exception as e:
            self.store.log("bot", f"getMe failed: {e}", "error")
            return False
        self.store.log("bot", f"@{me.get('username')} online; owner={settings.OWNER_ID}")
        self.register_commands()
        threading.Thread(target=self.poll_loop, daemon=True, name="tg-poll").start()
        threading.Thread(target=self.housekeeping_loop, daemon=True, name="tg-house").start()
        return True

    def poll_loop(self):
        backoff = 1
        while not self.stop.is_set():
            try:
                updates = self.tg.get_updates(self._offset, timeout=25)
                backoff = 1
            except Exception as e:
                self.store.log("bot", f"getUpdates error: {e}", "warn")
                time.sleep(min(30, backoff))
                backoff *= 2
                continue
            for up in updates or []:
                self._offset = up["update_id"] + 1
                self._enqueue(up)

    @staticmethod
    def _uid_of(up):
        if "message" in up:
            return (up["message"].get("from") or {}).get("id") or up["message"]["chat"]["id"]
        if "callback_query" in up:
            return up["callback_query"]["from"]["id"]
        return 0

    def _enqueue(self, up):
        """Different users run in parallel; updates of ONE user run strictly in order."""
        uid = self._uid_of(up)
        with self._ql:
            self._queues.setdefault(uid, []).append(up)
            if uid in self._active:
                return
            self._active.add(uid)
        self.pool.submit(self._drain, uid)

    def _drain(self, uid):
        while True:
            with self._ql:
                q = self._queues.get(uid) or []
                if not q:
                    self._active.discard(uid)
                    self._queues.pop(uid, None)
                    return
                up = q.pop(0)
            self._safe_dispatch(up)

    def housekeeping_loop(self):
        while not self.stop.is_set():
            time.sleep(30)
            try:
                self.ai.sweep_idle()
            except Exception as e:
                self.store.log("bot", f"ai sweep error: {e}", "warn")

    def _safe_dispatch(self, up):
        try:
            self.dispatch(up)
        except TgError as e:
            if e.code == 403:
                return  # user blocked the bot
            self.store.log("bot", f"tg error: {e}", "warn")
        except Exception as e:
            self.store.log("bot", f"dispatch error: {e!r}\n{traceback.format_exc()[-800:]}", "error")

    # ------------------------------------------------------------- dispatch
    def dispatch(self, up):
        if "message" in up:
            m = up["message"]
            if m.get("chat", {}).get("type") != "private":
                return
            frm = m.get("from") or {}
            user = self._ensure_user(frm, m)
            if user is None:
                return
            self.on_message(user, m)
        elif "callback_query" in up:
            cb = up["callback_query"]
            frm = cb["from"]
            user = self._ensure_user(frm, None)
            if user is None:
                self.tg.answer_cb(cb["id"])
                return
            self.on_callback(user, cb)

    def _ensure_user(self, frm, m):
        S = self.store
        referred = None
        text = (m or {}).get("text") or ""
        if text.startswith("/start") and "ref" in text:
            try:
                rid = int(text.split("ref", 1)[1].strip().split()[0])
                if rid != frm["id"]:
                    referred = rid
            except Exception:
                referred = None
        lang = norm_lang(frm.get("language_code"))
        user, new = S.tg_upsert_user(frm["id"], frm.get("username", "") or "", frm.get("first_name", "") or "", lang=lang,
                                     referred_by=referred)
        if new:
            S.log("bot", f"new user {frm['id']} @{frm.get('username', '')} lang={lang} ref={referred or '-'}")
            un = f"@{frm.get('username')}" if frm.get("username") else ""
            self.notify_owner("users", f"👤 کاربر جدید: {esc(frm.get('first_name'))} {un} <code>{frm['id']}</code>"
                                       f"{' (دعوت از ' + str(referred) + ')' if referred else ''} — مجموع {S.tg_user_count()}")
            if referred:
                res = self.svc.reward_referral(referred, frm["id"])
                if res:
                    ru = S.tg_user(referred)
                    try:
                        self.tg.send(referred, t(ru["lang"], "coins.new_ref", per=fmt_num(res[0]), coins=fmt_num(res[1])))
                    except Exception:
                        pass
        if self.is_owner(frm["id"]) and not user["is_admin"]:
            S.tg_update_user(frm["id"], is_admin=1)
            user = S.tg_user(frm["id"])
        if user["banned"] and not self.is_owner(user["tg_id"]):
            if m:
                self.tg.send(user["tg_id"], t(user["lang"], "banned"))
            return None
        return user

    # ------------------------------------------------------------- messages
    def on_message(self, user, m):
        S, uid, L = self.store, user["tg_id"], user["lang"]
        text = (m.get("text") or "").strip()
        state = user["state"]

        # ---- commands always win
        if text.startswith("/"):
            cmd = text.split()[0].lower().split("@")[0][1:]
            if cmd == "start":
                if state == "support":
                    self.end_support(user, silent=True)
                S.tg_set_state(uid, "", {})
                brand = svc.setting(S, svc.K_BRAND)
                msg = t(L, "welcome", name=esc(user["first_name"]), bot=esc(brand))
                if "ref" in text and user["referred_by"]:
                    msg += "\n" + t(L, "welcome_ref")
                self.tg.send(uid, msg, self.main_kb(user))
                return
            if cmd == "cancel":
                return self.cancel(user)
            if cmd == "admin":
                if self.is_admin(uid):
                    if state == "support":
                        self.end_support(user, silent=True)
                    return self.admin.menu(user)
                return self.tg.send(uid, t(L, "unknown"))
            action = {"buy": "kb.buy", "services": "kb.services", "wallet": "kb.wallet", "coins": "kb.coins", "support": "kb.support",
                      "lang": "kb.lang", "help": "kb.help"}.get(cmd)
            if action:
                if state == "support" and action != "kb.support":
                    self.end_support(user, silent=True)
                elif state:
                    S.tg_set_state(uid, "", {})
                user["state"] = ""
                return self.menu_action(user, action)
            return self.tg.send(uid, t(L, "unknown"))

        # ---- keyboard labels (any language)
        action = KB_ACTIONS.get(text)
        if action == "kb.cancel":
            return self.cancel(user)
        if action == "kb.end_support":
            return self.end_support(user)
        if action and state != "support":
            if state:
                S.tg_set_state(uid, "", {})
                user["state"] = ""
            return self.menu_action(user, action)
        if action and state == "support":
            # main-menu button pressed during support -> leave support and do it
            self.end_support(user, silent=True)
            user["state"] = ""
            return self.menu_action(user, action)

        # ---- stateful input
        if state == "support":
            if not text and not (m.get("photo") or m.get("document") or m.get("voice")):
                return
            payload = text or "[user sent a file/photo instead of text — ask them to describe the problem in text]"
            self.ai_pool.submit(self._ai_turn, user, payload)
            return
        if state == "card_receipt":
            return self.payments.receive_receipt(user, m)
        if state == "card_wait":
            # typed/sent something without tapping the button -> treat as receipt
            S.tg_set_state(uid, "card_receipt", user["state_data"])
            user["state"] = "card_receipt"
            return self.payments.receive_receipt(user, m)
        if state == "wallet_custom":
            return self.flows.wallet_custom_input(user, text)
        if state and self.is_admin(uid) and self.admin.handle_state(user, text):
            return
        if state:
            S.tg_set_state(uid, "", {})
        self.tg.send(uid, t(L, "unknown"), self.main_kb(user))

    def _ai_turn(self, user, text):
        try:
            if not self.ai.available():
                self.tg.send(user["tg_id"], t(user["lang"], "sup.unavailable"), self.main_kb(user))
                self.store.tg_set_state(user["tg_id"], "", {})
                return
            self.ai.handle_message(user, text)
        except Exception as e:
            self.store.log("ai", f"turn crashed: {e!r}", "error")

    def menu_action(self, user, action):
        uid = user["tg_id"]
        if action == "kb.buy":
            return self.flows.buy_menu(user)
        if action == "kb.services":
            return self.flows.services(user)
        if action == "kb.wallet":
            return self.flows.wallet(user)
        if action == "kb.coins":
            return self.flows.coins(user)
        if action == "kb.support":
            return self.start_support(user)
        if action == "kb.lang":
            return self.flows.lang_menu(user)
        if action == "kb.help":
            return self.flows.help(user)
        if action == "kb.admin" and self.is_admin(uid):
            return self.admin.menu(user)
        return self.tg.send(uid, t(user["lang"], "unknown"))

    def cancel(self, user):
        uid, L = user["tg_id"], user["lang"]
        if user["state"] == "support":
            return self.end_support(user)
        if not user["state"]:
            return self.tg.send(uid, t(L, "nothing_to_cancel"), self.main_kb(user))
        self.store.tg_set_state(uid, "", {})
        self.tg.send(uid, t(L, "cancelled"), self.main_kb(user))

    # ------------------------------------------------------------- support
    def start_support(self, user):
        uid, L = user["tg_id"], user["lang"]
        if not self.ai.available():
            return self.tg.send(uid, t(L, "sup.unavailable"), self.main_kb(user))
        self.store.tg_set_state(uid, "support", {})
        self.tg.send(uid, t(L, "sup.start"), self.support_kb(user))

    def end_support(self, user, silent=False):
        uid, L = user["tg_id"], user["lang"]
        s = self.store.ai_session_open(uid)
        if s:
            self.ai.close_session(s, reason="user")
        self.store.tg_set_state(uid, "", {})
        if not silent:
            self.tg.send(uid, t(L, "sup.ended"), self.main_kb(user))

    # ------------------------------------------------------------- callbacks
    def on_callback(self, user, cb):
        data = cb.get("data") or ""
        parts = data.split(":")
        head = parts[0]
        uid = user["tg_id"]
        msg = cb.get("message") or {}
        edit_ref = (msg.get("chat", {}).get("id"), msg.get("message_id"))
        try:
            if head == "cancel":
                self.tg.answer_cb(cb["id"])
                self.tg.delete(*edit_ref)
                if user["state"] and user["state"] != "support":
                    self.store.tg_set_state(uid, "", {})
                    self.tg.send(uid, t(user["lang"], "cancelled"), self.main_kb(user))
                return
            if head == "lang":
                return self.flows.set_lang(user, norm_lang(parts[1]), cb)
            if head == "buy":
                self.tg.answer_cb(cb["id"])
                renew = parts[2] if len(parts) > 2 else None
                return self.flows.buy_menu(user, edit=edit_ref, renew=renew)
            if head == "plan":
                return self.flows.plan_detail(user, int(parts[1]), cb, renew=parts[2] if len(parts) > 2 else None)
            if head == "pay":
                return self.flows.pay(user, parts[1], int(parts[2]), cb, renew=parts[3] if len(parts) > 3 else None)
            if head == "payok":
                return self.flows.pay_confirm(user, parts[1], int(parts[2]), cb, renew=parts[3] if len(parts) > 3 else None)
            if head == "svc":
                if parts[1] == "list":
                    self.tg.answer_cb(cb["id"])
                    return self.flows.services(user, edit=edit_ref)
                if parts[1] == "show":
                    return self.flows.service_show(user, parts[2], cb)
                if parts[1] == "links":
                    return self.flows.service_links(user, parts[2], cb)
            if head == "wallet":
                if parts[1] == "charge":
                    return self.flows.wallet_charge(user, cb)
                self.tg.answer_cb(cb["id"])
                return self.flows.wallet(user, edit=edit_ref)
            if head == "wamt":
                return self.flows.wallet_amount(user, parts[1], cb)
            if head == "wcard":
                return self.flows.wallet_card(user, parts[1], cb)
            if head == "rcpt" and parts[1] == "send":
                self.tg.answer_cb(cb["id"])
                return self.payments.ask_receipt(user)
            if head == "rc":
                if not self.is_admin(uid):
                    return self.tg.answer_cb(cb["id"], "⛔️", True)
                return self.payments.handle_callback(user, cb, parts)
            if head == "adm" and parts[1] == "user":
                if not self.is_admin(uid):
                    return self.tg.answer_cb(cb["id"], "⛔️", True)
                r = self.store.receipt(parts[2])
                if r:
                    return self.admin.user_view(user, r["tg_id"], cb)
            if head == "a":
                if not self.is_admin(uid):
                    return self.tg.answer_cb(cb["id"], "⛔️", True)
                return self.admin.handle_callback(user, cb, parts)
            self.tg.answer_cb(cb["id"])
        except TgError as e:
            self.tg.answer_cb(cb["id"], "⚠️ " + e.description[:150], True)
            raise

    # ------------------------------------------------------------- alerts (called from app loops)
    def usage_alerts(self):
        """Usage-threshold warnings + expiry notices to service owners (once per event)."""
        S = self.store
        pct_thr = int(svc.setting(S, svc.K_ALERT_PCT) or 80)
        for c in S.clients():
            if not c["owner_tg"]:
                continue
            total = c["total_limit_bytes"]
            if c["active"] and total > 0:
                pct = c["used_bytes"] / total * 100
                if pct >= pct_thr and not S.alert_sent(c["name"], "80"):
                    u = S.tg_user(c["owner_tg"])
                    if u:
                        v = self.svc.client_view(c, u["lang"])
                        try:
                            self.tg.send(u["tg_id"], t(u["lang"], "svc.alert80", name=c["name"], pct=int(pct), used=v["used"], total=v["total"]),
                                         ik([[(t(u["lang"], "svc.renew"), f"buy:menu:{c['name']}")]]))
                        except Exception:
                            pass
                    S.mark_alert(c["name"], "80")
                    self.notify_owner("alerts", f"⚠️ {c['name']} به {int(pct)}% مصرف رسید (کاربر <code>{c['owner_tg']}</code>)")
            if not c["active"] and c["status"] == "EXPIRED" and not S.alert_sent(c["name"], "expired"):
                u = S.tg_user(c["owner_tg"])
                if u:
                    why = t(u["lang"], "svc.why_volume" if (total and c["used_bytes"] >= total) else "svc.why_time")
                    try:
                        self.tg.send(u["tg_id"], t(u["lang"], "svc.alert_expired", name=c["name"], why=why),
                                     ik([[(t(u["lang"], "svc.renew"), f"buy:menu:{c['name']}")]]))
                    except Exception:
                        pass
                S.mark_alert(c["name"], "expired")
                self.notify_owner("alerts", f"🔴 {c['name']} منقضی شد (کاربر <code>{c['owner_tg']}</code>)")
