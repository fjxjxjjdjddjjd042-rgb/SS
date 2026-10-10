"""User-facing flows: buy, services, wallet, coins/referral, language, help, support entry."""
import time
from urllib.parse import quote

from .. import settings
from .tg import ik, esc
from .i18n import t, fmt_num, LANG_NAMES
from . import service as svc


class Flows:
    def __init__(self, bot):
        self.bot = bot
        self.S = bot.store
        self.svc = bot.svc
        self.tg = bot.tg

    # ------------------------------------------------------------- language
    def lang_menu(self, user, edit=None):
        rows = [[(LANG_NAMES[l], f"lang:{l}")] for l in settings.SUPPORTED_LANGS]
        txt = t(user["lang"], "choose_lang")
        if edit:
            self.tg.edit(edit[0], edit[1], txt, ik(rows))
        else:
            self.tg.send(user["tg_id"], txt, ik(rows))

    def set_lang(self, user, lang, cb=None):
        self.S.tg_update_user(user["tg_id"], lang=lang)
        user["lang"] = lang
        if cb:
            self.tg.answer_cb(cb["id"])
            self.tg.delete(cb["message"]["chat"]["id"], cb["message"]["message_id"])
        self.tg.send(user["tg_id"], t(lang, "lang_set") + "\n" + t(lang, "menu"), self.bot.main_kb(user))

    # ------------------------------------------------------------- buy
    def buy_menu(self, user, edit=None, renew=None):
        lang = user["lang"]
        plans = self.S.plans()
        if not plans:
            self.tg.send(user["tg_id"], t(lang, "buy.none"))
            return
        suffix = f":{renew}" if renew else ""
        rows = [[(svc.plan_text(lang, p), f"plan:{p['id']}{suffix}")] for p in plans]
        txt = t(lang, "buy.title")
        if edit:
            self.tg.edit(edit[0], edit[1], txt, ik(rows))
        else:
            self.tg.send(user["tg_id"], txt, ik(rows))

    def plan_detail(self, user, pid, cb, renew=None):
        lang = user["lang"]
        p = self.S.plan(pid)
        if not p or not p["active"]:
            self.tg.answer_cb(cb["id"], t(lang, "buy.none"), True)
            return
        suffix = f":{renew}" if renew else ""
        rows = [[(t(lang, "buy.pay_card"), f"pay:card:{pid}{suffix}")],
                [(t(lang, "buy.pay_wallet", bal=fmt_num(user["wallet"])), f"pay:wallet:{pid}{suffix}")]]
        if p["coin_price"]:
            rows.append([(t(lang, "buy.pay_coins", bal=fmt_num(user["coins"])), f"pay:coins:{pid}{suffix}")])
        rows.append([(t(lang, "kb.back"), "buy:menu" + (f":{renew}" if renew else ""))])
        txt = t(lang, "buy.detail", title=esc(p["title"]), vol=svc.vol_text(lang, p["gb"]), days=t(lang, "days", n=p["days"]),
                price=fmt_num(p["price"]), coin=fmt_num(p["coin_price"]) if p["coin_price"] else "—")
        if renew:
            txt = f"🔄 <code>{esc(renew)}</code>\n\n" + txt
        self.tg.answer_cb(cb["id"])
        self.tg.edit(cb["message"]["chat"]["id"], cb["message"]["message_id"], txt, ik(rows))

    def pay(self, user, method, pid, cb, renew=None):
        lang = user["lang"]
        p = self.S.plan(pid)
        cid, mid = cb["message"]["chat"]["id"], cb["message"]["message_id"]
        if not p or not p["active"]:
            self.tg.answer_cb(cb["id"], t(lang, "buy.none"), True)
            return
        suffix = f":{renew}" if renew else ""
        if method == "card":
            self.tg.answer_cb(cb["id"])
            self.tg.delete(cid, mid)
            self.bot.payments.start_card(user, "plan", p["price"], plan_id=p["id"], renew=renew)
            return
        if method == "wallet":
            if user["wallet"] < p["price"]:
                self.tg.answer_cb(cb["id"])
                self.tg.edit(cid, mid, t(lang, "buy.wallet_low", bal=fmt_num(user["wallet"]), need=fmt_num(p["price"])),
                             ik([[(t(lang, "buy.charge_wallet"), "wallet:charge")], [(t(lang, "kb.back"), f"plan:{pid}{suffix}")]]))
                return
            self.tg.answer_cb(cb["id"])
            self.tg.edit(cid, mid, t(lang, "buy.confirm_wallet", price=fmt_num(p["price"]), title=esc(p["title"])),
                         ik([[(t(lang, "buy.yes"), f"payok:wallet:{pid}{suffix}"), (t(lang, "buy.no"), f"plan:{pid}{suffix}")]]))
            return
        if method == "coins":
            if not p["coin_price"]:
                self.tg.answer_cb(cb["id"], t(lang, "buy.no_coin_price"), True)
                return
            if user["coins"] < p["coin_price"]:
                self.tg.answer_cb(cb["id"])
                self.tg.edit(cid, mid, t(lang, "buy.coins_low", bal=fmt_num(user["coins"]), need=fmt_num(p["coin_price"])),
                             ik([[(t(lang, "kb.back"), f"plan:{pid}{suffix}")]]))
                return
            self.tg.answer_cb(cb["id"])
            self.tg.edit(cid, mid, t(lang, "buy.confirm_coins", price=fmt_num(p["coin_price"]), title=esc(p["title"])),
                         ik([[(t(lang, "buy.yes"), f"payok:coins:{pid}{suffix}"), (t(lang, "buy.no"), f"plan:{pid}{suffix}")]]))

    def pay_confirm(self, user, method, pid, cb, renew=None):
        lang = user["lang"]
        p = self.S.plan(pid)
        cid, mid = cb["message"]["chat"]["id"], cb["message"]["message_id"]
        if not p:
            self.tg.answer_cb(cb["id"], t(lang, "buy.none"), True)
            return
        # one-shot guard: remove buttons first so double taps can't double-charge
        self.tg.edit_markup(cid, mid, None)
        try:
            if method == "wallet":
                c, bal = self.svc.pay_with_wallet(user["tg_id"], p, renew=renew)
            else:
                c, bal = self.svc.pay_with_coins(user["tg_id"], p, renew=renew)
        except ValueError:
            self.tg.answer_cb(cb["id"], t(lang, "buy.wallet_low" if method == "wallet" else "buy.coins_low",
                                          bal=fmt_num(user["wallet"] if method == "wallet" else user["coins"]),
                                          need=fmt_num(p["price"] if method == "wallet" else p["coin_price"])), True)
            return
        self.tg.answer_cb(cb["id"], "✅")
        self.tg.delete(cid, mid)
        self.send_activation(user, c, p)
        un = f"@{user['username']}" if user.get("username") else ""
        self.bot.notify_owner("sales", f"🛒 خرید با {'کیف پول' if method == 'wallet' else 'سکه'}: {esc(user['first_name'])} {un} "
                                       f"<code>{user['tg_id']}</code>\n📦 {esc(p['title'])} → <code>{c['name']}</code>")

    def send_activation(self, user, c, plan):
        lang = user["lang"]
        L = self.svc.links(c)
        txt = t(lang, "buy.done", name=c["name"], vol=svc.vol_text(lang, plan["gb"]), days=t(lang, "days", n=plan["days"]),
                sub=L["sub"], sub_json=L["sub_json"])
        self.tg.send(user["tg_id"], txt, ik([[(t(lang, "svc.links"), f"svc:links:{c['name']}")]]))

    # ------------------------------------------------------------- services
    def services(self, user, edit=None):
        lang = user["lang"]
        cl = self.S.clients_of(user["tg_id"])
        if not cl:
            txt, kb = t(lang, "svc.none"), ik([[(t(lang, "kb.buy"), "buy:menu")]])
        else:
            txt = t(lang, "svc.list")
            kb = ik([[(f"{'🟢' if c['active'] else '🔴'} {c['name']} • {self.svc.client_view(c, lang)['used']}", f"svc:show:{c['name']}")] for c in cl])
        if edit:
            self.tg.edit(edit[0], edit[1], txt, kb)
        else:
            self.tg.send(user["tg_id"], txt, kb)

    def _own(self, user, name):
        c = self.S.client(name)
        if not c or (c["owner_tg"] != user["tg_id"] and not self.bot.is_admin(user["tg_id"])):
            return None
        return c

    def service_show(self, user, name, cb):
        lang = user["lang"]
        c = self._own(user, name)
        if not c:
            self.tg.answer_cb(cb["id"], "❌", True)
            return
        v = self.svc.client_view(c, lang)
        L = self.svc.links(c)
        txt = t(lang, "svc.detail", name=c["name"], status=v["status"], used=v["used"], total=v["total"], bar=v["bar"], pct=v["pct"],
                rem=v["rem"], online=v["online"], sub=L["sub"], sub_json=L["sub_json"])
        kb = ik([[(t(lang, "svc.renew"), f"buy:menu:{c['name']}"), (t(lang, "svc.links"), f"svc:links:{c['name']}")],
                 [(t(lang, "svc.refresh"), f"svc:show:{c['name']}"), (t(lang, "kb.back"), "svc:list")]])
        self.tg.answer_cb(cb["id"])
        self.tg.edit(cb["message"]["chat"]["id"], cb["message"]["message_id"], txt, kb)

    def service_links(self, user, name, cb):
        lang = user["lang"]
        c = self._own(user, name)
        if not c:
            self.tg.answer_cb(cb["id"], "❌", True)
            return
        L = self.svc.links(c)
        self.tg.answer_cb(cb["id"])
        self.tg.send(user["tg_id"], t(lang, "svc.links_text", name=c["name"], sub=L["sub"], sub_json=L["sub_json"], sub_sb=L["sub_sb"],
                                      config=esc(L["config"])))

    # ------------------------------------------------------------- wallet
    def wallet(self, user, edit=None):
        lang = user["lang"]
        led = self.S.tg_ledger(user["tg_id"], 8)
        lines = []
        for r in led:
            sign = "➕" if r["delta"] > 0 else "➖"
            lines.append(f"{sign} {fmt_num(abs(r['delta']))} {t(lang, 'ledger.' + r['kind'])} — {esc(r['reason'])} "
                         f"<i>({time.strftime('%m/%d %H:%M', time.localtime(r['ts']))})</i>")
        txt = t(lang, "wallet.info", bal=fmt_num(user["wallet"]), coins=fmt_num(user["coins"]),
                orders=len(self.S.orders(user["tg_id"], 100)), ledger="\n".join(lines) or t(lang, "wallet.history_empty"))
        kb = ik([[(t(lang, "wallet.charge"), "wallet:charge")], [(t(lang, "kb.buy"), "buy:menu")]])
        if edit:
            self.tg.edit(edit[0], edit[1], txt, kb)
        else:
            self.tg.send(user["tg_id"], txt, kb)

    def wallet_charge(self, user, cb=None):
        lang = user["lang"]
        amounts = svc.setting(self.S, svc.K_WALLET_AMOUNTS) or []
        rows = []
        row = []
        for a in amounts:
            row.append((f"{fmt_num(a)} {t(lang, 'toman')}", f"wamt:{int(a)}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([(t(lang, "wallet.custom"), "wamt:custom")])
        rows.append([(t(lang, "kb.back"), "wallet:show")])
        if cb:
            self.tg.answer_cb(cb["id"])
            self.tg.edit(cb["message"]["chat"]["id"], cb["message"]["message_id"], t(lang, "wallet.choose_amount"), ik(rows))
        else:
            self.tg.send(user["tg_id"], t(lang, "wallet.choose_amount"), ik(rows))

    def wallet_amount(self, user, val, cb):
        lang = user["lang"]
        cid, mid = cb["message"]["chat"]["id"], cb["message"]["message_id"]
        if val == "custom":
            self.S.tg_set_state(user["tg_id"], "wallet_custom", {})
            self.tg.answer_cb(cb["id"])
            self.tg.edit(cid, mid, t(lang, "wallet.ask_custom", min=fmt_num(svc.setting(self.S, svc.K_WALLET_MIN))),
                         ik([[(t(lang, "kb.cancel"), "cancel")]]))
            return
        self.tg.answer_cb(cb["id"])
        self.tg.delete(cid, mid)
        self.wallet_method(user, int(val))

    def wallet_custom_input(self, user, text):
        lang = user["lang"]
        digits = "".join(ch for ch in text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")) if ch.isdigit())
        if not digits:
            self.tg.send(user["tg_id"], t(lang, "invalid_number"))
            return
        amount = int(digits)
        mn = int(svc.setting(self.S, svc.K_WALLET_MIN) or 0)
        if amount < mn:
            self.tg.send(user["tg_id"], t(lang, "wallet.min", min=fmt_num(mn)))
            return
        self.S.tg_set_state(user["tg_id"], "", {})
        self.wallet_method(user, amount)

    def wallet_method(self, user, amount):
        lang = user["lang"]
        # Only card-to-card is possible for top-ups.
        self.tg.send(user["tg_id"], t(lang, "wallet.method", amount=fmt_num(amount)),
                     ik([[(t(lang, "buy.pay_card"), f"wcard:{amount}")], [(t(lang, "kb.cancel"), "cancel")]]))

    def wallet_card(self, user, amount, cb):
        self.tg.answer_cb(cb["id"])
        self.tg.delete(cb["message"]["chat"]["id"], cb["message"]["message_id"])
        self.bot.payments.start_card(user, "wallet", int(amount))

    # ------------------------------------------------------------- coins / referral
    def coins(self, user):
        lang = user["lang"]
        link = self.svc.referral_link(user["tg_id"])
        per = svc.setting(self.S, svc.K_COIN_PER_REF)
        txt = t(lang, "coins.info", coins=fmt_num(user["coins"]), refs=fmt_num(user["referrals"]), per=fmt_num(per), link=link)
        share = f"https://t.me/share/url?url={quote(link, safe='')}"
        self.tg.send(user["tg_id"], txt, ik([[(t(lang, "coins.share"), share)], [(t(lang, "kb.buy"), "buy:menu")]]))

    # ------------------------------------------------------------- help
    def help(self, user):
        self.tg.send(user["tg_id"], t(user["lang"], "help"), self.bot.main_kb(user))
