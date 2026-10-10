"""Card-to-card payments with receipt IDs and idempotent two-step admin approval.

Flow:  user picks plan/amount -> card info -> sends receipt (photo/text)
       -> receipt R#### stored (pending) -> forwarded to all admins with [✅ تأیید] [❌ رد]
       -> admin taps ✅ -> "مطمئنی؟" [✅ بله] [↩️ خیر]
       -> decide_receipt() flips pending->approved atomically (first admin wins; later taps get "قبلاً انجام شده")
       -> fulfil (wallet credit or plan activation) -> user notified, admins' messages updated.
"""
import json
import time

from .. import settings
from .tg import ik, esc
from .i18n import t, fmt_num
from . import service as svc


class Payments:
    def __init__(self, bot):
        self.bot = bot
        self.S = bot.store
        self.svc = bot.svc

    # ------------------------------------------------------------- user side
    def card_info_text(self, lang, amount):
        card = self.S.get_setting(svc.K_CARD, "")
        holder = self.S.get_setting(svc.K_HOLDER, "")
        if not card:
            return None
        pretty = " ".join(card[i:i + 4] for i in range(0, len(card), 4)) if card.isdigit() else card
        return t(lang, "card.info", amount=fmt_num(amount), card=pretty, holder=esc(holder or "-"))

    def start_card(self, user, kind, amount, plan_id=None, renew=None):
        """Show card details + 'send receipt' button. kind: 'plan' | 'wallet'."""
        lang = user["lang"]
        pend = [r for r in self.S.receipts(status="pending", tg_id=user["tg_id"], limit=3)]
        if pend:
            self.bot.tg.send(user["tg_id"], t(lang, "card.pending_exists", rid=pend[0]["id"]))
            return
        txt = self.card_info_text(lang, amount)
        if not txt:
            self.bot.tg.send(user["tg_id"], t(lang, "card.not_set"))
            return
        data = {"kind": kind, "amount": int(amount), "plan_id": plan_id, "renew": renew}
        self.S.tg_set_state(user["tg_id"], "", {})  # no state until they tap the button
        kb = ik([[(t(lang, "card.send_receipt"), "rcpt:send")], [(t(lang, "kb.cancel"), "cancel")]])
        m = self.bot.tg.send(user["tg_id"], txt, kb)
        self.S.tg_set_state(user["tg_id"], "card_wait", data)

    def ask_receipt(self, user):
        lang = user["lang"]
        data = user["state_data"] if user["state"] == "card_wait" else None
        if not data:
            self.bot.tg.send(user["tg_id"], t(lang, "unknown"))
            return
        self.S.tg_set_state(user["tg_id"], "card_receipt", data)
        self.bot.tg.send(user["tg_id"], t(lang, "card.ask_receipt"), ik([[(t(lang, "kb.cancel"), "cancel")]]))

    def receive_receipt(self, user, msg):
        """msg is a Telegram Message with photo/document/text."""
        lang = user["lang"]
        data = user["state_data"] or {}
        file_id, text = "", ""
        if msg.get("photo"):
            file_id = msg["photo"][-1]["file_id"]
            text = msg.get("caption", "")
        elif msg.get("document"):
            file_id = msg["document"]["file_id"]
            text = msg.get("caption", "")
        else:
            text = msg.get("text", "")
        if not file_id and len(text.strip()) < 4:
            self.bot.tg.send(user["tg_id"], t(lang, "card.ask_receipt"))
            return
        meta = {"user_text": text[:300]}
        if data.get("renew"):
            meta["renew"] = data["renew"]
        r = self.S.create_receipt(user["tg_id"], data.get("kind", "wallet"), data.get("amount", 0),
                                  plan_id=data.get("plan_id"), file_id=file_id, text=json.dumps(meta, ensure_ascii=False))
        self.S.tg_set_state(user["tg_id"], "", {})
        self.bot.tg.send(user["tg_id"], t(lang, "card.received", rid=r["id"]), self.bot.main_kb(user))
        self.S.log("receipt", f"new {r['id']} from {user['tg_id']} kind={r['kind']} amount={r['amount']}")
        self.notify_admins(r, user, msg)

    # ------------------------------------------------------------- admin side
    def admin_caption(self, r, user, status_line=""):
        S = self.S
        plan = S.plan(r["plan_id"]) if r["plan_id"] else None
        try:
            meta = json.loads(r["text"] or "{}")
        except Exception:
            meta = {"user_text": r["text"]}
        kind = "👛 شارژ کیف پول" if r["kind"] == "wallet" else f"📦 خرید بسته: {plan['title'] if plan else '؟'}"
        if meta.get("renew"):
            kind += f" (تمدید {meta['renew']})"
        un = f"@{user['username']}" if user.get("username") else "-"
        lines = [f"🧾 <b>رسید جدید</b> <code>{r['id']}</code>", "",
                 f"👤 کاربر: {esc(user.get('first_name'))} {un} | <code>{user['tg_id']}</code>",
                 f"{kind}", f"💰 مبلغ: <b>{fmt_num(r['amount'])}</b> تومان",
                 f"🗓 {time.strftime('%Y-%m-%d %H:%M', time.localtime(r['created_at']))}"]
        if meta.get("user_text"):
            lines.append(f"📝 {esc(meta['user_text'])}")
        if status_line:
            lines += ["", status_line]
        return "\n".join(lines)

    def admin_kb(self, rid):
        return ik([[("✅ تأیید", f"rc:ok:{rid}"), ("❌ رد", f"rc:no:{rid}")], [("👤 کاربر", f"adm:user:{rid}")]])

    def notify_admins(self, r, user, msg):
        sent = {}
        cap = self.admin_caption(r, user)
        for aid in self.bot.admin_ids():
            try:
                if r["file_id"]:
                    m = self.bot.tg.copy_message(aid, user["tg_id"], msg["message_id"], caption=cap, reply_markup=self.admin_kb(r["id"]))
                else:
                    m = self.bot.tg.send(aid, cap, self.admin_kb(r["id"]))
                sent[str(aid)] = m["message_id"]
            except Exception as e:
                self.S.log("receipt", f"notify admin {aid} failed: {e}", "warn")
        self.S.set_receipt_admin_msg(r["id"], sent)

    def _update_admin_msgs(self, r, status_line):
        user = self.S.tg_user(r["tg_id"]) or {"tg_id": r["tg_id"], "first_name": "?", "username": ""}
        cap = self.admin_caption(r, user, status_line)
        for aid, mid in (r.get("admin_msg") or {}).items():
            try:
                if r["file_id"]:
                    self.bot.tg.edit_caption(int(aid), mid, cap, None)
                else:
                    self.bot.tg.edit(int(aid), mid, cap, None)
            except Exception:
                pass

    def handle_callback(self, admin, cb, parts):
        """parts: ['rc', action, rid] with action in ok|no|ok2|no2|back. Returns True if handled."""
        action, rid = parts[1], parts[2]
        r = self.S.receipt(rid)
        tg, cid, mid = self.bot.tg, cb["message"]["chat"]["id"], cb["message"]["message_id"]
        if not r:
            tg.answer_cb(cb["id"], "رسید پیدا نشد", True)
            return True
        if r["status"] != "pending":
            tg.answer_cb(cb["id"], f"این رسید قبلاً {'تأیید' if r['status'] == 'approved' else 'رد'} شده ✅", True)
            self._update_admin_msgs(r, self._status_line(r))
            return True
        if action in ("ok", "no"):
            q = "مطمئنی که این رسید را <b>تأیید</b> می‌کنی؟" if action == "ok" else "مطمئنی که این رسید را <b>رد</b> می‌کنی؟"
            kb = ik([[("✅ بله، مطمئنم", f"rc:{action}2:{rid}"), ("↩️ خیر", f"rc:back:{rid}")]])
            tg.answer_cb(cb["id"])
            try:
                tg.edit_markup(cid, mid, kb)
            except Exception:
                pass
            # Also send a small confirmation line (works for photo messages too)
            tg.send(cid, f"🧾 <code>{rid}</code> — {q}", kb)
            return True
        if action == "back":
            tg.answer_cb(cb["id"], "لغو شد")
            try:
                tg.edit_markup(cid, mid, self.admin_kb(rid))
            except Exception:
                pass
            if cb["message"].get("text", "").startswith("🧾"):
                tg.delete(cid, mid)
            return True
        if action == "no2":
            if not self.S.decide_receipt(rid, "rejected", admin["tg_id"]):
                tg.answer_cb(cb["id"], "قبلاً تصمیم‌گیری شده", True)
                return True
            r = self.S.receipt(rid)
            tg.answer_cb(cb["id"], "رد شد ❌")
            if cb["message"].get("text", "").startswith("🧾"):
                tg.delete(cid, mid)
            self._update_admin_msgs(r, self._status_line(r))
            self.S.log("receipt", f"{rid} rejected by {admin['tg_id']}")
            u = self.S.tg_user(r["tg_id"])
            if u:
                try:
                    tg.send(u["tg_id"], t(u["lang"], "card.rejected", rid=rid, reason=""))
                except Exception:
                    pass
            self.bot.notify_owner("receipts", f"❌ رسید <code>{rid}</code> توسط <code>{admin['tg_id']}</code> رد شد.", skip=admin["tg_id"])
            return True
        if action == "ok2":
            if not self.S.decide_receipt(rid, "approved", admin["tg_id"]):
                tg.answer_cb(cb["id"], "قبلاً تصمیم‌گیری شده", True)
                return True
            r = self.S.receipt(rid)
            if cb["message"].get("text", "").startswith("🧾"):
                tg.delete(cid, mid)
            try:
                res = self.svc.fulfil_receipt(r)
            except Exception as e:
                self.S.log("receipt", f"{rid} fulfil failed: {e}", "error")
                self.S._exec("UPDATE receipts SET result=? WHERE id=?", (f"error: {e}"[:400], rid))
                tg.answer_cb(cb["id"], f"خطا در فعال‌سازی: {e}", True)
                self._update_admin_msgs(r, f"⚠️ تأیید شد ولی فعال‌سازی خطا داد: {esc(e)}")
                return True
            tg.answer_cb(cb["id"], "تأیید شد ✅")
            self._after_approve(r, res, admin)
            return True
        return False

    def _status_line(self, r):
        who = r.get("admin_id") or "-"
        when = time.strftime("%H:%M", time.localtime(r.get("decided_at") or time.time()))
        if r["status"] == "approved":
            return f"✅ <b>تأیید شده</b> توسط <code>{who}</code> در {when}" + (f"\n{esc(r['result'])}" if r.get("result") else "")
        if r["status"] == "rejected":
            return f"❌ <b>رد شده</b> توسط <code>{who}</code> در {when}"
        return "⏳ در انتظار بررسی"

    def _after_approve(self, r, res, admin):
        S, tg = self.S, self.bot.tg
        u = S.tg_user(r["tg_id"])
        lang = u["lang"] if u else "fa"
        if res["kind"] == "wallet":
            result = f"wallet +{r['amount']} -> {res['balance']}"
            S._exec("UPDATE receipts SET result=? WHERE id=?", (result, r["id"]))
            if u:
                tg.send(u["tg_id"], t(lang, "card.approved_wallet", rid=r["id"], amount=fmt_num(r["amount"]), bal=fmt_num(res["balance"])))
            summary = f"👛 کیف پول کاربر <code>{r['tg_id']}</code> +{fmt_num(r['amount'])} تومان (موجودی {fmt_num(res['balance'])})"
        else:
            c, plan = res["client"], res["plan"]
            result = f"client {c['name']}"
            S._exec("UPDATE receipts SET result=? WHERE id=?", (result, r["id"]))
            if u:
                tg.send(u["tg_id"], t(lang, "card.approved_plan", rid=r["id"]))
                self.bot.flows.send_activation(u, c, plan)
            summary = f"📦 بسته <b>{esc(plan['title'])}</b> برای <code>{r['tg_id']}</code> فعال شد → <code>{c['name']}</code>"
        r = S.receipt(r["id"])
        self._update_admin_msgs(r, self._status_line(r))
        S.log("receipt", f"{r['id']} approved by {admin['tg_id']}: {result}")
        self.bot.notify_owner("sales", f"✅ رسید <code>{r['id']}</code> تأیید شد (توسط <code>{admin['tg_id']}</code>)\n{summary}", skip=admin["tg_id"])
