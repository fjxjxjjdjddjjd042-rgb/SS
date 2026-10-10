"""Admin panel inside Telegram (owner = full access; extra admins = receipts + users + services).

Everything the web panel can do is reachable here through inline menus + short text prompts:
  📊 status | 👥 users | 📦 services (create/edit/limits/links/delete) | 🧾 receipts | 💰 plans
  💳 payment settings | 🪙 coin settings | 🤖 AI (workers, memory, sessions, prompt) | 🛡 noads/bypass
  📣 broadcast | 📜 logs | ☁️ backup/cloud | ⚙️ notifications
"""
import json
import time

from .. import settings
from ..subscription import fmt_bytes, fmt_duration
from .tg import ik, esc
from .i18n import fmt_num, t
from . import service as svc

GB = 1024 ** 3


def _ts(ts):
    return time.strftime("%m/%d %H:%M", time.localtime(ts or 0))


def _yes(v):
    return "✅" if v else "❌"


class Admin:
    def __init__(self, bot):
        self.bot = bot
        self.S = bot.store
        self.tg = bot.tg
        self.svc = bot.svc

    # ------------------------------------------------------------- helpers
    def _edit_or_send(self, user, text, kb, cb=None):
        if cb:
            self.tg.answer_cb(cb["id"])
            m = cb["message"]
            if m.get("text") is not None:
                self.tg.edit(m["chat"]["id"], m["message_id"], text, kb)
                return
            self.tg.delete(m["chat"]["id"], m["message_id"])
        self.tg.send(user["tg_id"], text, kb)

    def ask(self, user, state, prompt, data=None, cb=None):
        """Put the admin into a text-input state."""
        self.S.tg_set_state(user["tg_id"], state, data or {})
        kb = ik([[("❌ انصراف", "cancel")]])
        if cb:
            self.tg.answer_cb(cb["id"])
        self.tg.send(user["tg_id"], prompt, kb)

    def owner_only(self, user, cb=None):
        if user["tg_id"] == settings.OWNER_ID:
            return True
        if cb:
            self.tg.answer_cb(cb["id"], "فقط مالک ربات", True)
        else:
            self.tg.send(user["tg_id"], "⛔️ فقط مالک ربات.")
        return False

    # ------------------------------------------------------------- main menu
    def menu(self, user, cb=None):
        S = self.S
        now = int(time.time())
        cl = S.clients()
        online = sum(1 for c in cl if c["active"] and now - (c["last_active_time"] or 0) <= 45)
        pend = len(S.receipts(status="pending", limit=100))
        sales = S.sales_stats(now - 86400)
        txt = (f"🛠 <b>پنل مدیریت</b>\n\n👥 کاربران: <b>{S.tg_user_count()}</b> | 📦 سرویس‌ها: <b>{len(cl)}</b> (🟢 {online} آنلاین)\n"
               f"🧾 رسید در انتظار: <b>{pend}</b>\n💵 فروش ۲۴h: <b>{sales['n']}</b> سفارش / <b>{fmt_num(sales['toman'])}</b> تومان\n"
               f"🧠 Xray: {'🟢' if self.bot.app.xray.is_running() else '🔴'} | ⏳ ران: {fmt_duration(max(0, settings.RUN_DURATION - (now - self.bot.app.state.started_at)))}\n"
               f"🌐 <code>{self.bot.app.state.tunnel_host}</code>")
        rows = [[("📊 وضعیت", "a:status"), ("🧾 رسیدها" + (f" ({pend})" if pend else ""), "a:rc:pending")],
                [("👥 کاربران", "a:users:0"), ("📦 سرویس‌ها", "a:svcs:0")],
                [("💰 بسته‌ها", "a:plans"), ("💳 پرداخت", "a:pay")],
                [("🪙 سکه", "a:coin"), ("🤖 پشتیبانی AI", "a:ai")]]
        if user["tg_id"] == settings.OWNER_ID:
            rows += [[("🛡 NoAds / بای‌پس", "a:net"), ("📣 اطلاع‌رسانی", "a:bc")],
                     [("📜 لاگ‌ها", "a:logs:"), ("☁️ بکاپ", "a:backup")],
                     [("⚙️ تنظیمات", "a:set"), ("🌐 پنل وب", f"https://{self.bot.app.state.tunnel_host}{settings.PANEL_PREFIX}")]]
        self._edit_or_send(user, txt, ik(rows), cb)

    def status(self, user, cb):
        api = self.bot.app.state
        S = self.S
        now = int(time.time())
        day = S.traffic_totals_since(now - 86400)
        blocked = S.blocked_stats(now - 86400)
        sysst = self.bot.app.xray.sys_stats()
        cloud = self.bot.app.cloud.status() if getattr(self.bot.app, "cloud", None) else "—"
        txt = (f"📊 <b>وضعیت سیستم</b>\n\n"
               f"🧠 Xray: {'🟢 فعال' if self.bot.app.xray.is_running() else '🔴 خاموش'} | RAM {fmt_bytes(sysst.get('Alloc', 0), '0')} | goroutines {sysst.get('NumGoroutine', 0)}\n"
               f"⬇️ دانلود ۲۴h: {fmt_bytes(sum(r['down'] or 0 for r in day), '0')} | ⬆️ آپلود: {fmt_bytes(sum(r['up'] or 0 for r in day), '0')}\n"
               f"🚫 تبلیغ مسدود ۲۴h: {fmt_num(blocked['blocked'])} از {fmt_num(blocked['total'])}\n"
               f"⏱ آپتایم: {fmt_duration(now - int(api.started_at))}\n"
               f"☁️ کلود: {esc(cloud)}\n🔐 vault: {settings.VAULT_KEY_ID}\n"
               f"🤖 AI workers: {len(S.ai_workers(only_active=True))} | sessions open: {len([1 for s in S.ai_sessions_recent(50) if not s['closed']])}\n"
               f"📁 repo: {settings.REPO_FULL_NAME or '-'}")
        self._edit_or_send(user, txt, ik([[("♻️ بروزرسانی", "a:status"), ("🔄 اعمال/ری‌استارت Xray", "a:apply")], [("🔙", "a:menu")]]), cb)

    # ------------------------------------------------------------- receipts
    def receipts(self, user, status, cb):
        rs = self.S.receipts(status=status if status != "all" else None, limit=15)
        lines = [f"🧾 <b>رسیدها</b> — {status}"]
        rows = []
        for r in rs:
            icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}[r["status"]]
            lines.append(f"{icon} <code>{r['id']}</code> {r['kind']} {fmt_num(r['amount'])} — <code>{r['tg_id']}</code> {_ts(r['created_at'])}")
            if r["status"] == "pending":
                rows.append([(f"{r['id']} • {fmt_num(r['amount'])}", f"a:rcv:{r['id']}")])
        if not rs:
            lines.append("— خالی")
        rows.append([("⏳ در انتظار", "a:rc:pending"), ("✅ تأیید", "a:rc:approved"), ("❌ رد", "a:rc:rejected")])
        rows.append([("🔙", "a:menu")])
        self._edit_or_send(user, "\n".join(lines), ik(rows), cb)

    def receipt_view(self, user, rid, cb):
        r = self.S.receipt(rid)
        if not r:
            self.tg.answer_cb(cb["id"], "پیدا نشد", True)
            return
        u = self.S.tg_user(r["tg_id"]) or {"tg_id": r["tg_id"], "first_name": "?", "username": ""}
        cap = self.bot.payments.admin_caption(r, u, self.bot.payments._status_line(r))
        self.tg.answer_cb(cb["id"])
        kb = self.bot.payments.admin_kb(rid) if r["status"] == "pending" else ik([[("🔙", "a:rc:pending")]])
        if r["file_id"]:
            try:
                self.tg.send_photo(user["tg_id"], r["file_id"], cap, kb)
                return
            except Exception:
                try:
                    self.tg.send_document(user["tg_id"], r["file_id"], cap, kb)
                    return
                except Exception:
                    pass
        self.tg.send(user["tg_id"], cap, kb)

    # ------------------------------------------------------------- users
    def users(self, user, page, cb, q=None):
        per = 10
        rows_db = self.S.tg_users(limit=per + 1, offset=page * per, q=q)
        more = len(rows_db) > per
        rows_db = rows_db[:per]
        lines = [f"👥 <b>کاربران</b> ({fmt_num(self.S.tg_user_count())})" + (f" — جستجو: {esc(q)}" if q else "")]
        rows = []
        for u in rows_db:
            flag = "⛔️" if u["banned"] else ("👑" if u["tg_id"] == settings.OWNER_ID else ("🛡" if u["is_admin"] else "👤"))
            lines.append(f"{flag} <code>{u['tg_id']}</code> {esc(u['first_name'])} @{u['username'] or '-'} | 👛{fmt_num(u['wallet'])} 🪙{u['coins']}")
            rows.append([(f"{u['first_name'][:14]} • {u['tg_id']}", f"a:u:{u['tg_id']}")])
        nav = []
        if page > 0:
            nav.append(("◀️", f"a:users:{page - 1}"))
        nav.append(("🔎 جستجو", "a:usearch"))
        if more:
            nav.append(("▶️", f"a:users:{page + 1}"))
        rows.append(nav)
        rows.append([("🔙", "a:menu")])
        self._edit_or_send(user, "\n".join(lines), ik(rows), cb)

    def user_view(self, user, uid, cb=None):
        u = self.S.tg_user(uid)
        if not u:
            if cb:
                self.tg.answer_cb(cb["id"], "کاربر پیدا نشد", True)
            else:
                self.tg.send(user["tg_id"], "کاربر پیدا نشد")
            return
        cl = self.S.clients_of(uid)
        led = self.S.tg_ledger(uid, 5)
        refby = f"<code>{u['referred_by']}</code>" if u["referred_by"] else "-"
        txt = (f"👤 <b>{esc(u['first_name'])}</b> @{u['username'] or '-'}\n<code>{u['tg_id']}</code>\n\n"
               f"🌐 زبان: {u['lang']} | عضویت: {_ts(u['created_at'])} | آخرین: {_ts(u['last_seen'])}\n"
               f"👛 کیف پول: <b>{fmt_num(u['wallet'])}</b> تومان | 🪙 سکه: <b>{u['coins']}</b>\n"
               f"👥 زیرمجموعه: {u['referrals']} | معرف: {refby}\n"
               f"🚫 مسدود: {_yes(u['banned'])} | 🛡 ادمین: {_yes(u['is_admin'])}\n"
               f"📝 {esc(u['note']) or '-'}\n\n📦 سرویس‌ها ({len(cl)}):\n" +
               ("\n".join(f"{'🟢' if c['active'] else '🔴'} <code>{c['name']}</code> {self.svc.client_view(c)['used']}/{self.svc.client_view(c)['total']}" for c in cl) or "—") +
               "\n\n💳 تراکنش‌های اخیر:\n" + ("\n".join(f"{'➕' if r['delta'] > 0 else '➖'}{fmt_num(abs(r['delta']))} {r['kind']} {esc(r['reason'])}" for r in led) or "—"))
        rows = [[("➕ کیف پول", f"a:ubal:wallet:{uid}"), ("➕/➖ سکه", f"a:ubal:coins:{uid}")],
                [("🎁 سرویس رایگان", f"a:ugift:{uid}"), ("✉️ پیام", f"a:umsg:{uid}")],
                [("🚫 رفع مسدودی" if u["banned"] else "⛔️ مسدود", f"a:uban:{uid}"), ("📝 یادداشت", f"a:unote:{uid}")]]
        for c in cl[:5]:
            rows.append([(f"📦 {c['name']}", f"a:svc:{c['name']}")])
        if user["tg_id"] == settings.OWNER_ID and uid != settings.OWNER_ID:
            rows.append([("🛡 حذف ادمین" if u["is_admin"] else "🛡 ادمین کن", f"a:uadmin:{uid}")])
        rows.append([("🧠 حافظه AI", f"a:aimem:user:{uid}"), ("🔙", "a:users:0")])
        self._edit_or_send(user, txt, ik(rows), cb)

    # ------------------------------------------------------------- services
    def services(self, user, page, cb, q=None):
        per = 10
        cl = self.S.clients()
        if q:
            cl = [c for c in cl if q.lower() in c["name"].lower() or q in str(c["owner_tg"])]
        total = len(cl)
        cl = cl[page * per:(page + 1) * per + 1]
        more = len(cl) > per
        cl = cl[:per]
        now = int(time.time())
        lines = [f"📦 <b>سرویس‌ها</b> ({total})"]
        rows = []
        for c in cl:
            v = self.svc.client_view(c)
            on = "🟢" if c["active"] and now - (c["last_active_time"] or 0) <= 45 else ("⚪️" if c["active"] else "🔴")
            lines.append(f"{on} <code>{c['name']}</code> {v['used']}/{v['total']} • {v['rem']}" + (f" • <code>{c['owner_tg']}</code>" if c["owner_tg"] else ""))
            rows.append([(f"{c['name']} • {v['pct']}%", f"a:svc:{c['name']}")])
        nav = []
        if page > 0:
            nav.append(("◀️", f"a:svcs:{page - 1}"))
        nav += [("➕ جدید", "a:snew"), ("🔎", "a:ssearch")]
        if more:
            nav.append(("▶️", f"a:svcs:{page + 1}"))
        rows.append(nav)
        rows.append([("🔙", "a:menu")])
        self._edit_or_send(user, "\n".join(lines), ik(rows), cb)

    def service_view(self, user, name, cb=None):
        c = self.S.client(name)
        if not c:
            if cb:
                self.tg.answer_cb(cb["id"], "سرویس پیدا نشد", True)
            return
        d = self.svc.diagnose(c)
        v = self.svc.client_view(c)
        L = self.svc.links(c)
        txt = (f"📦 <b>{c['name']}</b>  {v['status']}\n\n📊 {v['used']} / {v['total']}  {v['bar']} {v['pct']}%\n⏳ {v['rem']}\n"
               f"📶 {v['online']} | آخرین فعالیت: {d['last_active_seconds_ago'] if d['last_active_seconds_ago'] is not None else '-'}s پیش\n"
               f"📱 IP آنلاین: {len(d['online_ips_now'])} | حد IP: {c['ip_limit'] or '∞'}\n"
               f"🛡 NoAds {_yes(c['noads'])} | 🇮🇷 بای‌پس {_yes(c['bypass_iran'])}\n"
               f"👤 مالک: <code>{c['owner_tg'] or '-'}</code> | 🧩 clean: <code>{c['clean_ip']}</code>\n"
               f"📝 {esc(c['note']) or '-'}\n🆔 <code>{c['uuid']}</code>\n\n🔗 <code>{L['sub']}</code>")
        rows = [[("➕ حجم", f"a:sv:gb:{name}"), ("➕ روز", f"a:sv:days:{name}"), ("♾ نامحدود", f"a:sv:unl:{name}")],
                [("🔄 صفر کردن مصرف", f"a:sv:reset:{name}"), ("🔑 UUID جدید", f"a:sv:uuid:{name}")],
                [("⛔️ غیرفعال" if c["active"] else "✅ فعال", f"a:sv:toggle:{name}"), ("📱 حد IP", f"a:sv:iplim:{name}")],
                [("🛡 NoAds", f"a:sv:noads:{name}"), ("🇮🇷 بای‌پس", f"a:sv:bypass:{name}"), ("🧩 clean IP", f"a:sv:clean:{name}")],
                [("📝 یادداشت", f"a:sv:note:{name}"), ("👤 تغییر مالک", f"a:sv:owner:{name}"), ("✏️ نام", f"a:sv:rename:{name}")],
                [("🔗 لینک‌ها", f"a:sv:links:{name}"), ("🩺 عیب‌یابی", f"a:sv:diag:{name}"), ("📜 تاریخچه", f"a:sv:hist:{name}")],
                [("🗑 حذف", f"a:sv:del:{name}"), ("🔙", "a:svcs:0")]]
        if c["owner_tg"]:
            rows.insert(-1, [("👤 مالک", f"a:u:{c['owner_tg']}")])
        self._edit_or_send(user, txt, ik(rows), cb)

    def service_action(self, user, action, name, cb):
        S, c = self.S, self.S.client(name)
        if not c:
            self.tg.answer_cb(cb["id"], "پیدا نشد", True)
            return
        prompts = {"gb": ("sv_gb", f"چند گیگ به <code>{name}</code> اضافه شود؟ (عدد منفی = کم کردن، 0 = تنظیم دقیق در مرحله بعد)"),
                   "days": ("sv_days", f"چند روز به <code>{name}</code> اضافه شود؟ (منفی = کم کردن)"),
                   "iplim": ("sv_iplim", "حد تعداد IP همزمان؟ (0 = بدون محدودیت)"),
                   "clean": ("sv_clean", "آی‌پی/دامنه تمیز جدید؟"),
                   "note": ("sv_note", "یادداشت جدید:"), "owner": ("sv_owner", "آیدی عددی تلگرام مالک جدید؟ (0 = بدون مالک)"),
                   "rename": ("sv_rename", "نام جدید (فقط حروف انگلیسی/عدد/_/-):")}
        if action in prompts:
            st, p = prompts[action]
            self.ask(user, st, p, {"name": name}, cb)
            return
        if action == "unl":
            S.update_client(name, total_limit_bytes=0, active=1, status="OFFLINE")
        elif action == "reset":
            S.update_client(name, used_bytes=0, up_bytes=0, down_bytes=0, active=1, status="OFFLINE")
            S.clear_alerts(name)
        elif action == "uuid":
            import uuid
            S.update_client(name, uuid=str(uuid.uuid4()))
        elif action == "toggle":
            self.bot.app.state  # noqa
            from ..server import Api
            Api(self.bot.app.state).toggle_client(c, int(time.time()))
            self.tg.answer_cb(cb["id"], "انجام شد")
            self.service_view(user, name, cb=None)
            return
        elif action == "noads":
            S.update_client(name, noads=0 if c["noads"] else 1)
        elif action == "bypass":
            S.update_client(name, bypass_iran=0 if c["bypass_iran"] else 1)
        elif action == "links":
            L = self.svc.links(c)
            self.tg.answer_cb(cb["id"])
            self.tg.send(user["tg_id"], t("fa", "svc.links_text", name=name, sub=L["sub"], sub_json=L["sub_json"], sub_sb=L["sub_sb"], config=esc(L["config"])))
            return
        elif action == "diag":
            d = self.svc.diagnose(c)
            self.tg.answer_cb(cb["id"])
            self.tg.send(user["tg_id"], f"🩺 <b>{name}</b>\n<pre>{esc(json.dumps(d, ensure_ascii=False, indent=1)[:3500])}</pre>")
            return
        elif action == "hist":
            ips = S.client_ips(name)[:10]
            vis = S.visits(name, limit=20)
            txt = (f"📜 <b>{name}</b>\n\n📱 IPها:\n" + ("\n".join(f"• <code>{r['ip']}</code> ×{r['hits']} ({_ts(r['last_seen'])})" for r in ips) or "—") +
                   "\n\n🌐 سایت‌های اخیر:\n" + ("\n".join(f"{'🚫' if r['blocked'] else '•'} {esc(r['host'])}" for r in vis) or "—"))
            self.tg.answer_cb(cb["id"])
            self.tg.send(user["tg_id"], txt)
            return
        elif action == "del":
            self.tg.answer_cb(cb["id"])
            self.tg.send(user["tg_id"], f"⚠️ حذف <code>{name}</code>؟ این کار برگشت‌ناپذیر است.",
                         ik([[("🗑 بله حذف کن", f"a:sv:del2:{name}"), ("↩️ خیر", f"a:svc:{name}")]]))
            return
        elif action == "del2":
            S.delete_client(name, purge_history=True)
            S.log("client", f"deleted {name} by admin {user['tg_id']}")
            self.bot.app.on_change()
            self.tg.answer_cb(cb["id"], "حذف شد")
            self.services(user, 0, cb)
            return
        else:
            self.tg.answer_cb(cb["id"], "؟")
            return
        S.log("client", f"admin {user['tg_id']}: {action} on {name}")
        self.bot.app.on_change()
        self.tg.answer_cb(cb["id"], "✅")
        self.service_view(user, name, cb=None)

    # ------------------------------------------------------------- plans
    def plans(self, user, cb):
        ps = self.S.plans(only_active=False)
        lines = ["💰 <b>بسته‌ها</b>"]
        rows = []
        for p in ps:
            lines.append(f"{'✅' if p['active'] else '⚪️'} <b>{esc(p['title'])}</b> — {p['gb'] or '∞'}GB / {p['days']}d — {fmt_num(p['price'])}ت"
                         + (f" / 🪙{p['coin_price']}" if p["coin_price"] else "") + (f" / IP {p['ip_limit']}" if p["ip_limit"] else ""))
            rows.append([(f"{p['title']}", f"a:plan:{p['id']}")])
        rows.append([("➕ بسته جدید", "a:pnew"), ("🔙", "a:menu")])
        lines.append("\nفرمت سریع ساخت: <code>عنوان | گیگ | روز | قیمت | سکه | حدIP</code>\nمثال: <code>۱۰ گیگ یک‌ماهه | 10 | 30 | 59000 | 150 | 0</code>  (گیگ 0 = نامحدود)")
        self._edit_or_send(user, "\n".join(lines), ik(rows), cb)

    def plan_view(self, user, pid, cb):
        p = self.S.plan(pid)
        if not p:
            self.tg.answer_cb(cb["id"], "پیدا نشد", True)
            return
        txt = (f"💰 <b>{esc(p['title'])}</b>\n💾 {p['gb'] or 'نامحدود'} GB | ⏳ {p['days']} روز\n💵 {fmt_num(p['price'])} تومان | 🪙 {p['coin_price'] or '-'} سکه\n"
               f"📱 حد IP: {p['ip_limit'] or '∞'} | ترتیب: {p['sort']} | فعال: {_yes(p['active'])}")
        rows = [[("✏️ عنوان", f"a:pe:title:{pid}"), ("💾 گیگ", f"a:pe:gb:{pid}"), ("⏳ روز", f"a:pe:days:{pid}")],
                [("💵 قیمت", f"a:pe:price:{pid}"), ("🪙 سکه", f"a:pe:coin_price:{pid}"), ("📱 IP", f"a:pe:ip_limit:{pid}")],
                [("⚪️ غیرفعال" if p["active"] else "✅ فعال", f"a:ptoggle:{pid}"), ("🔢 ترتیب", f"a:pe:sort:{pid}")],
                [("🗑 حذف", f"a:pdel:{pid}"), ("🔙", "a:plans")]]
        self._edit_or_send(user, txt, ik(rows), cb)

    def plan_parse_create(self, user, text):
        parts = [x.strip() for x in text.split("|")]
        if len(parts) < 4:
            self.tg.send(user["tg_id"], "❌ فرمت: عنوان | گیگ | روز | قیمت | سکه | حدIP")
            return False
        try:
            nums = [int(float(_fa(x) or 0)) for x in parts[1:6]] + [0] * 5
            pid = self.S.add_plan(parts[0], nums[0], nums[1], nums[2], nums[3], nums[4], sort=len(self.S.plans(False)))
        except Exception as e:
            self.tg.send(user["tg_id"], f"❌ {e}")
            return False
        self.S.log("admin", f"plan {pid} created: {parts[0]}")
        self.S.tg_set_state(user["tg_id"], "", {})
        self.tg.send(user["tg_id"], f"✅ بسته <b>{esc(parts[0])}</b> ساخته شد.")
        self.plans(user, None)
        return True

    # ------------------------------------------------------------- payment / coin / settings
    def pay_settings(self, user, cb):
        S = self.S
        txt = (f"💳 <b>تنظیمات پرداخت</b>\n\nشماره کارت: <code>{S.get_setting(svc.K_CARD, '') or '—'}</code>\n"
               f"به نام: <b>{esc(S.get_setting(svc.K_HOLDER, '') or '—')}</b>\n\n"
               f"مبالغ شارژ کیف پول: {', '.join(fmt_num(a) for a in svc.setting(S, svc.K_WALLET_AMOUNTS))}\n"
               f"حداقل شارژ دلخواه: {fmt_num(svc.setting(S, svc.K_WALLET_MIN))} تومان")
        rows = [[("💳 شماره کارت", "a:set:card"), ("👤 نام صاحب کارت", "a:set:holder")],
                [("💵 مبالغ شارژ", "a:set:wamounts"), ("⬇️ حداقل شارژ", "a:set:wmin")], [("🔙", "a:menu")]]
        self._edit_or_send(user, txt, ik(rows), cb)

    def coin_settings(self, user, cb):
        S = self.S
        txt = (f"🪙 <b>سکه و زیرمجموعه</b>\n\n🎁 سکه هر دعوت: <b>{svc.setting(S, svc.K_COIN_PER_REF)}</b>\n"
               f"قیمت سکه‌ای هر بسته از بخش «💰 بسته‌ها» تنظیم می‌شود.\n"
               f"برای افزودن/کم‌کردن سکه یک کاربر: 👥 کاربران → کاربر → ➕/➖ سکه")
        rows = [[("🎁 سکه هر دعوت", "a:set:coinref")], [("🏆 برترین دعوت‌کننده‌ها", "a:topref")], [("🔙", "a:menu")]]
        self._edit_or_send(user, txt, ik(rows), cb)

    def top_ref(self, user, cb):
        rows = self.S._rows("SELECT tg_id, first_name, username, referrals, coins FROM tg_users WHERE referrals>0 ORDER BY referrals DESC LIMIT 15")
        txt = "🏆 <b>برترین دعوت‌کننده‌ها</b>\n\n" + ("\n".join(f"{i + 1}. {esc(r['first_name'])} @{r['username'] or '-'} <code>{r['tg_id']}</code> — 👥{r['referrals']} 🪙{r['coins']}"
                                                          for i, r in enumerate(rows)) or "—")
        self._edit_or_send(user, txt, ik([[("🔙", "a:coin")]]), cb)

    def settings_menu(self, user, cb):
        S = self.S
        n = svc.setting(S, svc.K_NOTIF)
        admins = svc.setting(S, svc.K_ADMINS)
        txt = (f"⚙️ <b>تنظیمات</b>\n\n🏷 برند: <b>{esc(svc.setting(S, svc.K_BRAND))}</b>\n"
               f"🛡 ادمین‌های اضافه: {', '.join(f'<code>{a}</code>' for a in admins) or '—'}\n"
               f"⚠️ هشدار مصرف در: {svc.setting(S, svc.K_ALERT_PCT)}%\n\n🔔 نوتیف‌های مالک:\n" +
               "\n".join(f"{_yes(v)} {k}" for k, v in n.items()))
        rows = [[("🏷 برند", "a:set:brand"), ("⚠️ درصد هشدار", "a:set:alertpct")],
                [("🔔 نوتیف‌ها", "a:notif")], [("🔙", "a:menu")]]
        self._edit_or_send(user, txt, ik(rows), cb)

    def notif_menu(self, user, cb):
        n = dict(svc.DEFAULTS[svc.K_NOTIF])
        n.update(svc.setting(self.S, svc.K_NOTIF) or {})
        labels = {"users": "👤 کاربر جدید", "sales": "🛒 فروش", "receipts": "🧾 رسید", "ai": "🤖 پشتیبانی AI",
                  "system": "🧠 سیستم/ران", "alerts": "⚠️ هشدار مصرف", "logs_warn": "📜 خطاها/هشدارهای لاگ"}
        rows = [[(f"{_yes(n[k])} {labels[k]}", f"a:ntog:{k}")] for k in labels]
        rows.append([("🔙", "a:set")])
        self._edit_or_send(user, "🔔 <b>نوتیف‌های مالک</b>\nبا لمس هر مورد روشن/خاموش می‌شود.", ik(rows), cb)

    # ------------------------------------------------------------- AI
    def ai_menu(self, user, cb):
        S = self.S
        ws = S.ai_workers()
        open_s = [s for s in S.ai_sessions_recent(100) if not s["closed"]]
        txt = (f"🤖 <b>پشتیبانی AI</b>\n\nوضعیت: {_yes(svc.setting(S, svc.K_SUPPORT_ON))} | workers: {len([w for w in ws if w['active']])}/{len(ws)}\n"
               f"مدل پیش‌فرض: <code>{esc(S.get_setting(svc.K_AI_MODEL, '') or '(از worker)')}</code> | دما: {svc.setting(S, svc.K_AI_TEMPERATURE)}\n"
               f"نمایش پیشرفت ابزار به کاربر: {_yes(svc.setting(S, svc.K_AI_USER_PROGRESS))}\n"
               f"گفتگوهای باز: {len(open_s)} | حافظه: {len(S.ai_memory_all())} مورد\n\n")
        for w in ws:
            txt += (f"{'🟢' if w['active'] else '⚪️'} <b>#{w['id']} {esc(w['name'])}</b> <code>{esc(w['base_url'])}</code> model=<code>{esc(w['model'] or '-')}</code>\n"
                    f"   req {w['requests']} | err {w['errors']} | 429 {w['rate_limits']}\n")
        rows = [[("➕ ADD AI (worker جدید)", "a:aiadd"), ("⛔️ خاموش" if svc.setting(S, svc.K_SUPPORT_ON) else "✅ روشن", "a:aitog")],
                [("🧠 حافظه", "a:aimem:global:0"), ("💬 گفتگوها", "a:aisess")],
                [("📝 پرامپت اضافه", "a:set:aiprompt"), ("🎛 مدل پیش‌فرض", "a:set:aimodel")],
                [("👁 پیشرفت ابزار", "a:aiprog"), ("🌡 دما", "a:set:aitemp")]]
        for w in ws:
            rows.append([(f"⚙️ #{w['id']} {w['name'][:12]}", f"a:aiw:{w['id']}")])
        rows.append([("🔙", "a:menu")])
        self._edit_or_send(user, txt, ik(rows), cb)

    def ai_worker_view(self, user, wid, cb):
        w = self.S.ai_worker(wid)
        if not w:
            self.tg.answer_cb(cb["id"], "پیدا نشد", True)
            return
        key = w["api_key"]
        masked = key[:6] + "…" + key[-4:] if len(key) > 12 else "***"
        txt = (f"⚙️ <b>Worker #{w['id']} {esc(w['name'])}</b>\n\nBASE_URL: <code>{esc(w['base_url'])}</code>\nKEY: <code>{masked}</code>\n"
               f"model: <code>{esc(w['model'] or '-')}</code>\nفعال: {_yes(w['active'])}\nدرخواست: {w['requests']} | خطا: {w['errors']} | 429: {w['rate_limits']}\n"
               f"آخرین استفاده: {_ts(w['last_used']) if w['last_used'] else '-'}")
        rows = [[("🔗 BASE_URL", f"a:aiwe:base_url:{wid}"), ("🔑 KEY_API", f"a:aiwe:api_key:{wid}")],
                [("🎛 مدل", f"a:aiwe:model:{wid}"), ("🏷 نام", f"a:aiwe:name:{wid}")],
                [("⚪️ غیرفعال" if w["active"] else "✅ فعال", f"a:aiwtog:{wid}"), ("🧪 تست", f"a:aiwtest:{wid}")],
                [("🗑 حذف", f"a:aiwdel:{wid}"), ("🔙", "a:ai")]]
        self._edit_or_send(user, txt, ik(rows), cb)

    def ai_worker_test(self, user, wid, cb):
        from .ai_agent import Worker, RateLimited, ProviderError
        w = self.S.ai_worker(wid)
        self.tg.answer_cb(cb["id"], "در حال تست…")
        try:
            t0 = time.time()
            msg, usage = Worker(w).chat([{"role": "user", "content": "Reply with exactly: OK"}], None, w["model"], timeout=40)
            self.tg.send(user["tg_id"], f"✅ worker #{wid} پاسخ داد در {time.time() - t0:.1f}s:\n<code>{esc((msg.get('content') or '')[:200])}</code>\nusage: {esc(json.dumps(usage))}")
        except RateLimited as e:
            self.tg.send(user["tg_id"], f"⏳ worker #{wid}: rate limit (retry_after={e.retry_after})")
        except (ProviderError, Exception) as e:
            self.tg.send(user["tg_id"], f"❌ worker #{wid}: <code>{esc(str(e)[:300])}</code>")

    def ai_memory(self, user, target, uid, cb):
        mems = self.S.ai_memories(target, int(uid))
        head = "🧠 <b>حافظه سراسری AI</b>" if target == "global" else f"🧠 <b>حافظه AI برای کاربر <code>{uid}</code></b>"
        lines = [head, ""] + [f"[{m['id']}] {esc(m['content'])}  <i>({_ts(m['updated_at'])})</i>" for m in mems] or [head, "", "—"]
        if not mems:
            lines.append("—")
        rows = [[("➕ افزودن", f"a:aimemadd:{target}:{uid}"), ("🗑 حذف با شماره", f"a:aimemdel:{target}:{uid}")]]
        if target == "global":
            allm = self.S.ai_memory_all()
            users = sorted({m["tg_id"] for m in allm if m["target"] == "user"})
            for u in users[:8]:
                rows.append([(f"👤 حافظه کاربر {u}", f"a:aimem:user:{u}")])
        rows.append([("🔙", "a:ai" if target == "global" else f"a:u:{uid}")])
        self._edit_or_send(user, "\n".join(lines), ik(rows), cb)

    def ai_sessions(self, user, cb):
        ss = self.S.ai_sessions_recent(15)
        lines = ["💬 <b>گفتگوهای پشتیبانی</b>", ""]
        rows = []
        for s in ss:
            lines.append(f"{'🟢' if not s['closed'] else '⚪️'} <code>{s['id']}</code> 👤<code>{s['tg_id']}</code> {s['turns']}↔ {s['tool_calls']}🔧 {_ts(s['last_at'])}")
            rows.append([(f"{s['id']} • {s['tg_id']}", f"a:aisv:{s['id']}")])
        rows.append([("🔙", "a:ai")])
        self._edit_or_send(user, "\n".join(lines), ik(rows), cb)

    def ai_session_view(self, user, sid, cb):
        logs = self.S.ai_log(sid, 60)
        icons = {"user": "👤", "assistant": "🤖", "tool": "🔧", "tool_result": "📎", "open": "▶️", "close": "⏹", "ratelimit": "⏳"}
        lines = [f"💬 <b>{sid}</b>", ""]
        for l in logs:
            lines.append(f"{icons.get(l['kind'], '•')} <i>{time.strftime('%H:%M:%S', time.localtime(l['ts']))}</i> {esc(l['content'][:350])}")
        self.tg.answer_cb(cb["id"])
        self.tg.send(user["tg_id"], "\n".join(lines), ik([[("🔙", "a:aisess")]]))

    # ------------------------------------------------------------- noads / bypass
    def net_menu(self, user, cb):
        X = self.bot.app.xray
        ns, bs = X.noads.summary(), X.bypass.summary()
        txt = (f"🛡 <b>NoAds</b>: سطح <b>{ns['level']}</b> | دامنه‌های curated: {ns['curated_domains']} | remote: {ns.get('remote_domains', 0)}\n"
               f"سفارشی: {len(ns['custom_block'])} | سفید: {len(ns['whitelist'])} | تبلیغات ایرانی: {_yes(ns['block_iran_ads'])}\n\n"
               f"🇮🇷 <b>بای‌پس</b>: {bs['iran_mode']} | مستقیم سفارشی: {len(bs['custom_direct'])} | اجباری VPN: {len(bs['custom_proxy'])}\n\n"
               f"🧩 clean pool: {', '.join(self.S.get_setting('clean_pool', settings.DEFAULT_CLEAN_POOL))}")
        rows = [[("off", "a:noads:off"), ("balanced", "a:noads:balanced"), ("aggressive", "a:noads:aggressive"), ("strict", "a:noads:strict")],
                [("➕ بلاک دامنه", "a:set:noads_add"), ("➕ سفید", "a:set:noads_white")],
                [("🇮🇷 بای‌پس: " + ("خاموش کن" if bs["iran_mode"] == "direct" else "روشن کن"), "a:bypass:toggle"), ("➕ مستقیم", "a:set:bypass_add")],
                [("🧪 تست دامنه", "a:set:nettest"), ("🧩 clean pool", "a:set:pool")], [("🔙", "a:menu")]]
        self._edit_or_send(user, txt, ik(rows), cb)

    # ------------------------------------------------------------- logs / backup / broadcast
    def logs(self, user, kind, cb):
        ev = self.S.events(25, kind or None)
        icons = {"info": "•", "warn": "⚠️", "error": "❌"}
        txt = f"📜 <b>لاگ‌ها</b>{' — ' + kind if kind else ''}\n\n" + "\n".join(
            f"{icons.get(e['level'], '•')} <i>{time.strftime('%H:%M:%S', time.localtime(e['ts']))}</i> [{e['kind']}] {esc(e['message'][:160])}" for e in ev)
        kinds = ["", "xray", "client", "sale", "receipt", "ai", "security", "sync", "cloud", "bot"]
        rows = [[(k or "همه", f"a:logs:{k}") for k in kinds[:5]], [(k, f"a:logs:{k}") for k in kinds[5:]], [("♻️", f"a:logs:{kind}"), ("🔙", "a:menu")]]
        self._edit_or_send(user, txt, ik(rows), cb)

    def backup_menu(self, user, cb):
        cloud = self.bot.app.cloud
        txt = (f"☁️ <b>بکاپ و ذخیره‌سازی</b>\n\n{esc(cloud.status() if cloud else 'cloud غیرفعال (PANTRY_ID تنظیم نشده)')}\n\n"
               f"🔐 vault محلی: data/vault.enc (کلید {settings.VAULT_KEY_ID})\n"
               f"ذخیره خودکار: هر {settings.CLOUD_SYNC_INTERVAL // 60} دقیقه در کلود + هر {settings.GIT_SYNC_INTERVAL}s در گیت")
        rows = [[("☁️ ذخیره الان در کلود", "a:cloud:push"), ("⬇️ دریافت vault", "a:cloud:dl")],
                [("♻️ بازیابی از کلود (خطرناک)", "a:cloud:restore")], [("🔙", "a:menu")]]
        self._edit_or_send(user, txt, ik(rows), cb)

    def broadcast_ask(self, user, cb):
        self.ask(user, "bc_text", f"📣 متن پیام همگانی را بفرست (HTML مجاز). به {self.S.tg_user_count()} کاربر ارسال می‌شود.", cb=cb)

    def broadcast_confirm(self, user, text):
        self.S.tg_set_state(user["tg_id"], "bc_confirm", {"text": text})
        self.tg.send(user["tg_id"], f"پیش‌نمایش:\n\n{text}\n\nارسال شود؟", ik([[("📣 بله ارسال کن", "a:bc:go"), ("❌ خیر", "cancel")]]))

    def broadcast_go(self, user, cb):
        u = self.S.tg_user(user["tg_id"])
        text = (u["state_data"] or {}).get("text") if u["state"] == "bc_confirm" else None
        self.S.tg_set_state(user["tg_id"], "", {})
        if not text:
            self.tg.answer_cb(cb["id"], "متنی نیست", True)
            return
        self.tg.answer_cb(cb["id"], "شروع شد")
        import threading

        def _run():
            ok = fail = 0
            for uid in self.S.tg_all_ids():
                try:
                    self.tg.send(uid, text)
                    ok += 1
                except Exception:
                    fail += 1
                time.sleep(0.05)
            self.tg.send(user["tg_id"], f"📣 ارسال تمام شد: ✅ {ok} | ❌ {fail}")
            self.S.log("bot", f"broadcast by {user['tg_id']}: ok={ok} fail={fail}")
        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------- text input handler for admin states
    def handle_state(self, user, text):
        """Returns True if the text was consumed by an admin state."""
        S, st, d = self.S, user["state"], user["state_data"] or {}
        uid = user["tg_id"]
        txt = text.strip()

        def done(msg=None):
            S.tg_set_state(uid, "", {})
            if msg:
                self.tg.send(uid, msg)

        # ---- service edits
        if st in ("sv_gb", "sv_days", "sv_iplim", "sv_clean", "sv_note", "sv_owner", "sv_rename"):
            name = d.get("name")
            c = S.client(name)
            if not c:
                done("سرویس پیدا نشد")
                return True
            try:
                if st == "sv_gb":
                    v = float(_fa(txt))
                    if v == 0:
                        S.tg_set_state(uid, "sv_gb_exact", d)
                        self.tg.send(uid, "حجم کل دقیق به گیگ؟ (0 = نامحدود)")
                        return True
                    new = 0 if c["total_limit_bytes"] == 0 else max(0, c["total_limit_bytes"] + int(v * GB))
                    S.update_client(name, total_limit_bytes=new, active=1, status="OFFLINE")
                elif st == "sv_days":
                    v = float(_fa(txt))
                    S.update_client(name, expire_seconds=max(3600, c["expire_seconds"] + int(v * 86400)), active=1, status="OFFLINE")
                elif st == "sv_iplim":
                    S.update_client(name, ip_limit=max(0, int(float(_fa(txt)))))
                elif st == "sv_clean":
                    S.update_client(name, clean_ip=txt[:120])
                elif st == "sv_note":
                    S.update_client(name, note=txt[:200])
                elif st == "sv_owner":
                    S.update_client(name, owner_tg=int(_fa(txt)))
                elif st == "sv_rename":
                    from ..server import NAME_RE
                    if not NAME_RE.match(txt) or S.client(txt):
                        self.tg.send(uid, "❌ نام نامعتبر یا تکراری")
                        return True
                    S.rename_client(name, txt)
                    name = txt
            except ValueError:
                self.tg.send(uid, "❌ عدد معتبر وارد کن")
                return True
            S.clear_alerts(name)
            S.log("client", f"admin {uid}: {st} on {name} = {txt[:50]}")
            self.bot.app.on_change()
            done("✅ انجام شد")
            self.service_view(user, name)
            return True
        if st == "sv_gb_exact":
            try:
                v = float(_fa(txt))
            except ValueError:
                self.tg.send(uid, "❌ عدد")
                return True
            S.update_client(d["name"], total_limit_bytes=int(v * GB), active=1, status="OFFLINE")
            self.bot.app.on_change()
            done("✅")
            self.service_view(user, d["name"])
            return True
        if st == "svc_new":
            # name | gb | days | owner_tg(optional)
            parts = [x.strip() for x in txt.split("|")]
            from ..server import NAME_RE
            if not parts or not NAME_RE.match(parts[0]) or S.client(parts[0]):
                self.tg.send(uid, "❌ نام نامعتبر/تکراری. فرمت: name | گیگ | روز | آیدی‌مالک(اختیاری)")
                return True
            try:
                gb = float(_fa(parts[1])) if len(parts) > 1 else 0
                days = int(float(_fa(parts[2]))) if len(parts) > 2 else 30
                owner = int(_fa(parts[3])) if len(parts) > 3 and parts[3] else 0
            except ValueError:
                self.tg.send(uid, "❌ عدد نامعتبر")
                return True
            S.create_client(parts[0], total_limit_bytes=int(gb * GB), expire_seconds=days * 86400, owner_tg=owner, note=f"by admin {uid}")
            S.log("client", f"admin {uid} created {parts[0]}")
            self.bot.app.on_change()
            done("✅ ساخته شد")
            self.service_view(user, parts[0])
            return True
        if st in ("svc_search", "user_search"):
            done()
            if st == "svc_search":
                self.services(user, 0, None, q=txt)
            else:
                if txt.isdigit() and S.tg_user(int(txt)):
                    self.user_view(user, int(txt))
                else:
                    self.users(user, 0, None, q=txt.lstrip("@"))
            return True
        # ---- user edits
        if st in ("ubal_wallet", "ubal_coins"):
            try:
                delta = int(float(_fa(txt)))
            except ValueError:
                self.tg.send(uid, "❌ عدد (مثبت=افزودن، منفی=کم کردن)")
                return True
            kind = "wallet" if st == "ubal_wallet" else "coins"
            try:
                bal = S.tg_adjust(d["uid"], kind, delta, reason=f"admin {uid}", ref="admin")
            except ValueError as e:
                done(f"❌ {e}")
                return True
            S.log("admin", f"{uid} adjusted {kind} {delta:+} for {d['uid']} -> {bal}")
            done(f"✅ موجودی جدید: {fmt_num(bal)}")
            tu = S.tg_user(d["uid"])
            if tu:
                try:
                    label = t(tu["lang"], "ledger." + kind)
                    self.tg.send(tu["tg_id"], f"{'➕' if delta > 0 else '➖'} {fmt_num(abs(delta))} {label} → {fmt_num(bal)}")
                except Exception:
                    pass
            self.user_view(user, d["uid"])
            return True
        if st == "unote":
            S.tg_update_user(d["uid"], note=txt[:300])
            done("✅")
            self.user_view(user, d["uid"])
            return True
        if st == "umsg":
            try:
                self.tg.send(d["uid"], txt)
                done("✅ ارسال شد")
            except Exception as e:
                done(f"❌ {e}")
            return True
        if st == "ugift":
            # plan id -> activate free
            p = S.plan(int(_fa(txt))) if _fa(txt).isdigit() else None
            if not p:
                self.tg.send(uid, "❌ شماره بسته معتبر نیست. شماره‌ها در «💰 بسته‌ها».")
                return True
            tu = S.tg_user(d["uid"])
            c = self.svc.activate_plan(d["uid"], p, "gift", 0)
            done(f"✅ {p['title']} برای {d['uid']} فعال شد → <code>{c['name']}</code>")
            if tu:
                self.bot.flows.send_activation(tu, c, p)
            return True
        # ---- plans
        if st == "plan_new":
            return self.plan_parse_create(user, txt)
        if st == "plan_edit":
            field, pid = d["field"], d["pid"]
            val = txt if field == "title" else None
            if field != "title":
                try:
                    val = int(float(_fa(txt)))
                except ValueError:
                    self.tg.send(uid, "❌ عدد")
                    return True
            S.update_plan(pid, **{field: val})
            done("✅")
            self.plan_view(user, pid, None)
            return True
        # ---- settings
        if st.startswith("set_"):
            key = st[4:]
            try:
                if key == "card":
                    S.set_setting(svc.K_CARD, "".join(ch for ch in _fa(txt) if ch.isdigit()) or txt)
                elif key == "holder":
                    S.set_setting(svc.K_HOLDER, txt[:60])
                elif key == "wamounts":
                    S.set_setting(svc.K_WALLET_AMOUNTS, sorted({int(float(_fa(x))) for x in txt.replace("،", ",").replace(" ", ",").split(",") if x.strip()}))
                elif key == "wmin":
                    S.set_setting(svc.K_WALLET_MIN, int(float(_fa(txt))))
                elif key == "coinref":
                    S.set_setting(svc.K_COIN_PER_REF, int(float(_fa(txt))))
                elif key == "brand":
                    S.set_setting(svc.K_BRAND, txt[:40])
                elif key == "alertpct":
                    S.set_setting(svc.K_ALERT_PCT, max(1, min(99, int(float(_fa(txt))))))
                elif key == "aiprompt":
                    S.set_setting(svc.K_AI_PROMPT, "" if txt == "-" else txt[:4000])
                elif key == "aimodel":
                    S.set_setting(svc.K_AI_MODEL, "" if txt == "-" else txt[:80])
                elif key == "aitemp":
                    S.set_setting(svc.K_AI_TEMPERATURE, max(0.0, min(1.5, float(_fa(txt)))))
                elif key in ("noads_add", "noads_white", "bypass_add", "pool"):
                    from ..server import _domains
                    m = {"noads_add": "noads_custom_block", "noads_white": "noads_whitelist", "bypass_add": "bypass_custom_direct", "pool": "clean_pool"}[key]
                    cur = S.get_setting(m, [] if key != "pool" else settings.DEFAULT_CLEAN_POOL)
                    if txt.startswith("-"):
                        rem = set(_domains(txt[1:]))
                        S.set_setting(m, [x for x in cur if x not in rem])
                    else:
                        S.set_setting(m, list(dict.fromkeys(cur + _domains(txt)))[:500])
                    self.bot.app.on_change()
                elif key == "nettest":
                    X = self.bot.app.xray
                    from ..server import _domains
                    res = "\n".join(f"• {h}: {'🚫 blocked' if X.noads.is_blocked(h) else '✅ allowed'} | {'🇮🇷 direct' if X.bypass.is_direct(h) else '🌍 proxy'}" for h in _domains(txt))
                    done(res or "—")
                    return True
                else:
                    done("؟")
                    return True
            except ValueError:
                self.tg.send(uid, "❌ مقدار نامعتبر")
                return True
            S.log("admin", f"{uid} set {key}")
            done("✅ ذخیره شد")
            return True
        if st == "ai_add":
            # BASE_URL | KEY | model | name
            parts = [x.strip() for x in txt.split("|")]
            if len(parts) < 2 or not parts[0].startswith("http"):
                self.tg.send(uid, "❌ فرمت: BASE_URL | KEY_API | model(اختیاری) | نام(اختیاری)\nمثال: https://api.openai.com/v1 | sk-xxx | gpt-4o-mini | main")
                return True
            wid = S.ai_worker_add(parts[0], parts[1], parts[2] if len(parts) > 2 else "", parts[3] if len(parts) > 3 else f"worker-{len(S.ai_workers()) + 1}")
            S.log("ai", f"worker #{wid} added by {uid}")
            done(f"✅ worker #{wid} اضافه شد. با «🧪 تست» بررسی کن.")
            self.ai_menu(user, None)
            return True
        if st == "ai_wedit":
            S.ai_worker_update(d["wid"], **{d["field"]: txt})
            done("✅")
            self.ai_worker_view(user, d["wid"], None)
            return True
        if st == "ai_memadd":
            S.ai_memory_add(d["target"], txt, int(d["uid"]))
            done("✅ به حافظه اضافه شد")
            self.ai_memory(user, d["target"], d["uid"], None)
            return True
        if st == "ai_memdel":
            ids = {m["id"] for m in S.ai_memories(d["target"], int(d["uid"]))}
            mid = int(_fa(txt)) if _fa(txt).isdigit() else -1
            if mid not in ids:
                self.tg.send(uid, "❌ شماره معتبر نیست")
                return True
            S.ai_memory_remove(mid)
            done("✅ حذف شد")
            self.ai_memory(user, d["target"], d["uid"], None)
            return True
        if st == "bc_text":
            self.broadcast_confirm(user, text)
            return True
        return False

    # ------------------------------------------------------------- callback router
    def handle_callback(self, user, cb, parts):
        """parts[0] == 'a'. Returns True if handled."""
        S = self.S
        op = parts[1] if len(parts) > 1 else "menu"
        arg = parts[2] if len(parts) > 2 else ""
        arg2 = parts[3] if len(parts) > 3 else ""
        uid = user["tg_id"]
        owner = uid == settings.OWNER_ID
        if op == "menu":
            self.menu(user, cb)
        elif op == "status":
            self.status(user, cb)
        elif op == "apply":
            self.tg.answer_cb(cb["id"], "در حال اعمال…")
            self.bot.app.on_change()
            self.status(user, cb=None)
        elif op == "rc":
            self.receipts(user, arg or "pending", cb)
        elif op == "rcv":
            self.receipt_view(user, arg, cb)
        elif op == "users":
            self.users(user, int(arg or 0), cb)
        elif op == "usearch":
            self.ask(user, "user_search", "آیدی عددی، یوزرنیم یا نام کاربر:", cb=cb)
        elif op == "u":
            self.user_view(user, int(arg), cb)
        elif op == "ubal":
            self.ask(user, f"ubal_{arg}", f"مقدار {'تومان' if arg == 'wallet' else 'سکه'} برای <code>{arg2}</code>؟ (مثبت=افزودن، منفی=کم کردن)", {"uid": int(arg2)}, cb)
        elif op == "unote":
            self.ask(user, "unote", "یادداشت:", {"uid": int(arg)}, cb)
        elif op == "umsg":
            self.ask(user, "umsg", f"پیام برای <code>{arg}</code>:", {"uid": int(arg)}, cb)
        elif op == "ugift":
            ps = "\n".join(f"{p['id']}. {p['title']}" for p in S.plans())
            self.ask(user, "ugift", f"شماره بسته برای فعال‌سازی رایگان:\n{ps}", {"uid": int(arg)}, cb)
        elif op == "uban":
            u = S.tg_user(int(arg))
            if u and int(arg) != settings.OWNER_ID:
                S.tg_update_user(int(arg), banned=0 if u["banned"] else 1)
                S.log("admin", f"{uid} {'unbanned' if u['banned'] else 'banned'} {arg}")
            self.user_view(user, int(arg), cb)
        elif op == "uadmin" and owner:
            u = S.tg_user(int(arg))
            if u:
                S.tg_update_user(int(arg), is_admin=0 if u["is_admin"] else 1)
                admins = set(svc.setting(S, svc.K_ADMINS))
                (admins.discard if u["is_admin"] else admins.add)(int(arg))
                S.set_setting(svc.K_ADMINS, sorted(admins))
                S.log("admin", f"{uid} {'removed' if u['is_admin'] else 'added'} admin {arg}")
            self.user_view(user, int(arg), cb)
        elif op == "svcs":
            self.services(user, int(arg or 0), cb)
        elif op == "ssearch":
            self.ask(user, "svc_search", "نام سرویس یا آیدی مالک:", cb=cb)
        elif op == "snew":
            self.ask(user, "svc_new", "فرمت: <code>name | گیگ | روز | آیدی‌مالک(اختیاری)</code>\nمثال: <code>ali_vip | 50 | 30 | 123456</code> (گیگ 0 = نامحدود)", cb=cb)
        elif op == "svc":
            self.service_view(user, arg, cb)
        elif op == "sv":
            self.service_action(user, arg, arg2, cb)
        elif op == "plans":
            self.plans(user, cb)
        elif op == "plan":
            self.plan_view(user, int(arg), cb)
        elif op == "pnew":
            self.ask(user, "plan_new", "فرمت: <code>عنوان | گیگ | روز | قیمت | سکه | حدIP</code>", cb=cb)
        elif op == "pe":
            self.ask(user, "plan_edit", f"مقدار جدید برای <b>{arg}</b>:", {"field": arg, "pid": int(arg2)}, cb)
        elif op == "ptoggle":
            p = S.plan(int(arg))
            if p:
                S.update_plan(int(arg), active=0 if p["active"] else 1)
            self.plan_view(user, int(arg), cb)
        elif op == "pdel":
            S.delete_plan(int(arg))
            S.log("admin", f"{uid} deleted plan {arg}")
            self.plans(user, cb)
        elif op == "pay":
            self.pay_settings(user, cb)
        elif op == "coin":
            self.coin_settings(user, cb)
        elif op == "topref":
            self.top_ref(user, cb)
        elif op == "set":
            if not arg:
                if self.owner_only(user, cb):
                    self.settings_menu(user, cb)
                return True
            prompts = {"card": "شماره کارت (۱۶ رقم):", "holder": "نام صاحب کارت:", "wamounts": "مبالغ شارژ با کاما (مثال: 50000,100000,200000):",
                       "wmin": "حداقل مبلغ شارژ دلخواه (تومان):", "coinref": "سکه برای هر دعوت موفق:", "brand": "نام برند:",
                       "alertpct": "درصد مصرف برای ارسال هشدار (مثلاً 80):",
                       "aiprompt": "دستورالعمل اضافه برای AI (برای پاک کردن «-» بفرست):", "aimodel": "نام مدل پیش‌فرض (برای پاک کردن «-»):",
                       "aitemp": "دمای مدل (0 تا 1.5):",
                       "noads_add": "دامنه‌ها برای بلاک (با فاصله/کاما؛ برای حذف ابتدای پیام «-» بگذار):",
                       "noads_white": "دامنه‌های سفید (برای حذف با «-» شروع کن):", "bypass_add": "دامنه‌های مستقیم ایران (برای حذف با «-»):",
                       "nettest": "دامنه‌ها برای تست NoAds/بای‌پس:", "pool": "لیست clean IP/دامنه (با فاصله؛ برای حذف با «-»):"}
            self.ask(user, f"set_{arg}", prompts.get(arg, "مقدار:"), cb=cb)
        elif op == "notif":
            self.notif_menu(user, cb)
        elif op == "ntog":
            n = dict(svc.DEFAULTS[svc.K_NOTIF])
            n.update(svc.setting(S, svc.K_NOTIF) or {})
            n[arg] = not n.get(arg, True)
            S.set_setting(svc.K_NOTIF, n)
            self.notif_menu(user, cb)
        elif op == "ai":
            self.ai_menu(user, cb)
        elif op == "aiadd":
            self.ask(user, "ai_add", "<b>ADD AI</b>\nفرمت: <code>BASE_URL | KEY_API | model | نام</code>\nمثال: <code>https://api.openai.com/v1 | sk-xxxx | gpt-4o-mini | main</code>", cb=cb)
        elif op == "aitog":
            S.set_setting(svc.K_SUPPORT_ON, not svc.setting(S, svc.K_SUPPORT_ON))
            self.ai_menu(user, cb)
        elif op == "aiprog":
            S.set_setting(svc.K_AI_USER_PROGRESS, not svc.setting(S, svc.K_AI_USER_PROGRESS))
            self.ai_menu(user, cb)
        elif op == "aiw":
            self.ai_worker_view(user, int(arg), cb)
        elif op == "aiwe":
            self.ask(user, "ai_wedit", f"مقدار جدید {arg}:", {"wid": int(arg2), "field": arg}, cb)
        elif op == "aiwtog":
            w = S.ai_worker(int(arg))
            if w:
                S.ai_worker_update(int(arg), active=0 if w["active"] else 1)
            self.ai_worker_view(user, int(arg), cb)
        elif op == "aiwtest":
            self.ai_worker_test(user, int(arg), cb)
        elif op == "aiwdel":
            S.ai_worker_delete(int(arg))
            S.log("ai", f"worker #{arg} deleted by {uid}")
            self.ai_menu(user, cb)
        elif op == "aimem":
            self.ai_memory(user, arg, arg2 or 0, cb)
        elif op == "aimemadd":
            self.ask(user, "ai_memadd", "متن حافظه:", {"target": arg, "uid": arg2 or 0}, cb)
        elif op == "aimemdel":
            self.ask(user, "ai_memdel", "شماره [id] حافظه برای حذف:", {"target": arg, "uid": arg2 or 0}, cb)
        elif op == "aisess":
            self.ai_sessions(user, cb)
        elif op == "aisv":
            self.ai_session_view(user, arg, cb)
        elif op == "net" and owner:
            self.net_menu(user, cb)
        elif op == "noads" and owner:
            S.set_setting("noads_level", arg)
            S.log("noads", f"level={arg} by {uid}")
            self.bot.app.on_change()
            self.net_menu(user, cb)
        elif op == "bypass" and owner:
            cur = S.get_setting("bypass_iran_mode", "direct")
            S.set_setting("bypass_iran_mode", "proxy" if cur == "direct" else "direct")
            self.bot.app.on_change()
            self.net_menu(user, cb)
        elif op == "bc" and owner:
            if arg == "go":
                self.broadcast_go(user, cb)
            else:
                self.broadcast_ask(user, cb)
        elif op == "logs" and owner:
            self.logs(user, arg, cb)
        elif op == "backup" and owner:
            self.backup_menu(user, cb)
        elif op == "cloud" and owner:
            cloud = self.bot.app.cloud
            if not cloud:
                self.tg.answer_cb(cb["id"], "کلود غیرفعال است (PANTRY_ID)", True)
                return True
            if arg == "push":
                self.tg.answer_cb(cb["id"], "در حال ذخیره…")
                ok, msg = cloud.push(force=True)
                self.tg.send(uid, ("✅ " if ok else "❌ ") + esc(msg))
            elif arg == "dl":
                self.tg.answer_cb(cb["id"])
                self.bot.app.store.save_vault()
                with open(settings.VAULT_PATH, "rb") as f:
                    data = f.read()
                self.tg.upload_document(uid, f"vault_{time.strftime('%Y%m%d_%H%M')}.enc", data, caption="🔐 vault رمزنگاری‌شده")
            elif arg == "restore":
                self.tg.answer_cb(cb["id"])
                self.tg.send(uid, "⚠️ بازیابی از کلود همهٔ داده‌های فعلی را جایگزین می‌کند. مطمئنی؟",
                             ik([[("♻️ بله بازیابی کن", "a:cloud:restore2"), ("❌ خیر", "a:backup")]]))
            elif arg == "restore2":
                self.tg.answer_cb(cb["id"], "در حال بازیابی…")
                ok, msg = cloud.restore()
                if ok:
                    self.bot.app.on_change()
                self.tg.send(uid, ("✅ " if ok else "❌ ") + esc(msg))
        else:
            self.tg.answer_cb(cb["id"], "دسترسی نداری یا دستور نامعتبر", True)
        return True


def _fa(s):
    """Persian/Arabic digits -> ascii, strip separators."""
    return (s or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).replace(",", "").replace("،", "").strip()
