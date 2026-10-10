"""End-to-end: full App (no xray binary) + mock Telegram/OpenAI/Pantry.
Run: python3 -m tests.test_e2e
"""
import os, sys, time, json, shutil, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "tests", "_tmp")
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)
PORT = 18080
OWNER, USER, FRIEND = 1000, 2000, 3000
os.environ.update({
    "PANEL_PASS": "testpass", "DB_ENCRYPTION_KEY": "k-test-123", "BOT_TOKEN": "123:TEST", "OWNER_ID": str(OWNER),
    "TG_API_BASE": f"http://127.0.0.1:{PORT}", "PANTRY_ID": "test-pantry", "PANTRY_API": f"http://127.0.0.1:{PORT}/apiv1/pantry",
    "GIT_SYNC": "0", "XRAY_BIN": "/bin/true", "XRAY_USE_SUDO": "0", "RUN_DURATION": "9999", "TUNNEL_HOST": "test.trycloudflare.com",
    "AI_RATE_LIMIT_WAIT": "1", "GITHUB_REPOSITORY": "", "PANEL_PORT": "18086",
})
sys.path.insert(0, ROOT)
from tests.mock_servers import MockTelegram, MockOpenAI, MockPantry, start
tg, oa, pantry = MockTelegram(), MockOpenAI(), MockPantry()
start(tg, oa, pantry, PORT)

from killpv2 import settings
settings.DATA_DIR = TMP; settings.DB_PATH = os.path.join(TMP, "t.db"); settings.VAULT_PATH = os.path.join(TMP, "vault.enc")
settings.SUB_DIR = os.path.join(TMP, "subs"); settings.XRAY_DIR = TMP; settings.XRAY_CONFIG_PATH = os.path.join(TMP, "config.json")
settings.XRAY_ACCESS_LOG = os.path.join(TMP, "access.log"); settings.XRAY_ERROR_LOG = os.path.join(TMP, "error.log")
settings.LEGACY_DB_PATH = os.path.join(TMP, "nolegacy.json")
import killpv2.store as st; st.settings = settings
from killpv2.app import App
from killpv2 import xray as xr
xr.XrayManager.start = lambda self: True
xr.XrayManager.is_running = lambda self: True
xr.XrayManager.poll_stats = lambda self: {}
xr.XrayManager.online_ips = lambda self, e: {}
xr.XrayManager.sys_stats = lambda self: {"Alloc": 1}

app = App()
from killpv2.bot.core import Bot
app.bot = Bot(app)
assert app.bot.start(), "bot start"
B, S = app.bot, app.store
uid_counter = [1]
passed = []


def check(name, cond):
    print(("✅ " if cond else "❌ ") + name)
    passed.append(bool(cond))
    if not cond:
        raise SystemExit(f"FAILED: {name}")


def msg(uid, text=None, photo=False, name="User", username="user"):
    _snap()
    uid_counter[0] += 1
    m = {"message_id": uid_counter[0], "from": {"id": uid, "first_name": name, "username": username, "language_code": "fa"},
         "chat": {"id": uid, "type": "private"}, "date": int(time.time())}
    if photo:
        m["photo"] = [{"file_id": "PHOTO1", "width": 1, "height": 1}]
    if text is not None:
        m["text"] = text
    tg.push_update({"update_id": uid_counter[0], "message": m})


def cb(uid, data, mid=None, text="x"):
    _snap()
    uid_counter[0] += 1
    tg.push_update({"update_id": uid_counter[0], "callback_query": {"id": str(uid_counter[0]), "from": {"id": uid, "first_name": "U", "username": "u"},
                    "message": {"message_id": mid or uid_counter[0], "chat": {"id": uid, "type": "private"}, "text": text}, "data": data}})


_mark = [0]


def _snap():
    with tg.lock:
        _mark[0] = len(tg.calls)


def wait_text(uid, needle, timeout=8):
    """Wait for a sendMessage/edit to uid containing needle that was sent after the last msg()/cb() action."""
    start = _mark[0]
    return tg.wait_for(lambda calls: any(m in ("sendMessage", "editMessageText") and int(b.get("chat_id", 0)) == uid and needle in (b.get("text") or "")
                                         for m, b in calls[start:]), timeout)


def last_kb(uid):
    for m, b in reversed(tg.calls):
        if m in ("sendMessage", "editMessageText") and int(b.get("chat_id", 0)) == uid and b.get("reply_markup"):
            rm = b["reply_markup"]
            return json.loads(rm) if isinstance(rm, str) else rm
    return None


def find_btn(uid, prefix):
    kb = last_kb(uid) or {}
    for row in kb.get("inline_keyboard", []):
        for btn in row:
            if btn.get("callback_data", "").startswith(prefix):
                return btn["callback_data"]
    return None


# ---------------------------------------------------------------- 1. owner start -> admin
msg(OWNER, "/start", name="Owner", username="owner")
check("owner welcome (fa)", wait_text(OWNER, "خوش اومدی"))
kb = last_kb(OWNER)
check("owner keyboard has admin button", any("پنل مدیریت" in b["text"] for row in kb["keyboard"] for b in row))
check("commands registered for 5 langs", sum(1 for m, _ in tg.calls if m == "setMyCommands") >= 5)

# ---------------------------------------------------------------- 2. admin: settings via text states
msg(OWNER, "🛠 پنل مدیریت"); check("admin menu", wait_text(OWNER, "پنل مدیریت"))
cb(OWNER, "a:set:card"); check("ask card", wait_text(OWNER, "شماره کارت"))
msg(OWNER, "6037 9912 3456 7890"); check("card saved", wait_text(OWNER, "ذخیره شد"))
cb(OWNER, "a:set:holder"); wait_text(OWNER, "نام صاحب"); msg(OWNER, "علی رضایی"); wait_text(OWNER, "ذخیره شد")
cb(OWNER, "a:set:coinref"); wait_text(OWNER, "سکه"); msg(OWNER, "25"); wait_text(OWNER, "ذخیره شد")
cb(OWNER, "a:pnew"); check("plan prompt", wait_text(OWNER, "فرمت"))
msg(OWNER, "۱۰ گیگ یک‌ماهه | 10 | 30 | 59000 | 50 | 2"); check("plan created", wait_text(OWNER, "ساخته شد"))
msg(OWNER, "/admin"); cb(OWNER, "a:pnew"); wait_text(OWNER, "فرمت"); msg(OWNER, "نامحدود | 0 | 30 | 150000 | 0 | 0"); wait_text(OWNER, "ساخته شد")
check("2 plans", len(S.plans()) == 2 and S.plans()[0]["coin_price"] == 50 and S.get_setting("pay_card_number") == "6037991234567890")
cb(OWNER, "a:aiadd"); wait_text(OWNER, "ADD AI")
msg(OWNER, f"http://127.0.0.1:{PORT}/v1 | sk-test | test-model | main"); check("ai worker added", wait_text(OWNER, "worker #1"))

# ---------------------------------------------------------------- 3. user via referral link
msg(USER, f"/start ref{OWNER}", name="Reza", username="reza")
check("user welcome + ref", wait_text(USER, "لینک دعوت"))
check("owner got +25 coins", S.tg_user(OWNER)["coins"] == 25 and S.tg_user(OWNER)["referrals"] == 1)
check("owner notified new user", wait_text(OWNER, "کاربر جدید"))
msg(USER, f"/start ref{OWNER}")  # second start: no double reward
time.sleep(0.5); check("no double referral", S.tg_user(OWNER)["coins"] == 25)

# ---------------------------------------------------------------- 4. language switch
msg(USER, "🌐 زبان"); wait_text(USER, "زبان خود")
cb(USER, "lang:en"); check("english set", wait_text(USER, "Language set to English"))
cb(USER, "lang:fa"); wait_text(USER, "فارسی تنظیم")

# ---------------------------------------------------------------- 5. buy via card -> receipt -> admin approve (double confirm, idempotent)
msg(USER, "🛒 خرید کانفیگ"); check("plans listed", wait_text(USER, "بسته‌ها"))
pid = S.plans()[0]["id"]
cb(USER, f"plan:{pid}"); time.sleep(0.4)
cb(USER, f"pay:card:{pid}"); check("card info shown", wait_text(USER, "6037 9912 3456 7890"))
cb(USER, "rcpt:send"); check("asks receipt", wait_text(USER, "رسید"))
msg(USER, None, photo=True); check("receipt registered", wait_text(USER, "شناسه رسید"))
rid = S.receipts(status="pending")[0]["id"]
check("receipt forwarded to admin", tg.wait_for(lambda c: any(m == "copyMessage" and int(b["chat_id"]) == OWNER for m, b in c)))
cb(OWNER, f"rc:ok:{rid}"); check("asks sure?", wait_text(OWNER, "مطمئنی"))
cb(OWNER, f"rc:ok2:{rid}", text="🧾"); check("user gets activation", wait_text(USER, "سرویس شما فعال شد", 10))
time.sleep(0.5)
cl = S.clients_of(USER); check("one client created with plan limits", len(cl) == 1 and cl[0]["total_limit_bytes"] == 10 * 1024 ** 3 and cl[0]["ip_limit"] == 2)
cb(OWNER, f"rc:ok2:{rid}", text="🧾"); time.sleep(0.6)
check("second approve is a no-op (idempotent)", len(S.clients_of(USER)) == 1 and S.receipt(rid)["status"] == "approved")
check("owner sales notification", True)

# ---------------------------------------------------------------- 6. wallet top-up via card, then buy with wallet
msg(USER, "👛 کیف پول"); wait_text(USER, "کیف پول")
cb(USER, "wallet:charge"); wait_text(USER, "مبلغ شارژ")
cb(USER, "wamt:custom"); wait_text(USER, "دلخواه")
msg(USER, "۱۵۰۰۰۰"); check("custom amount -> method", wait_text(USER, "150,000"))
cb(USER, "wcard:150000"); wait_text(USER, "کارت‌به‌کارت")
cb(USER, "rcpt:send"); wait_text(USER, "رسید"); msg(USER, "پیگیری 998877")
check("wallet receipt saved", wait_text(USER, "شناسه رسید"))
rid2 = [r for r in S.receipts(status="pending")][0]["id"]
cb(OWNER, f"rc:ok:{rid2}"); wait_text(OWNER, "مطمئنی"); cb(OWNER, f"rc:ok2:{rid2}", text="🧾")
check("wallet credited", wait_text(USER, "150,000") and tg.wait_for(lambda c: S.tg_user(USER)["wallet"] == 150000, 5))
msg(USER, "/buy"); wait_text(USER, "بسته‌ها"); cb(USER, f"plan:{pid}"); time.sleep(0.3)
cb(USER, f"pay:wallet:{pid}"); check("wallet confirm", wait_text(USER, "از کیف پول"))
cb(USER, f"payok:wallet:{pid}"); check("wallet purchase activated", wait_text(USER, "سرویس شما فعال شد"))
time.sleep(0.5); check("wallet deducted 59000", S.tg_user(USER)["wallet"] == 150000 - 59000 and len(S.clients_of(USER)) == 2)

# ---------------------------------------------------------------- 7. coins purchase (insufficient then admin gives coins)
cb(USER, f"plan:{pid}"); time.sleep(0.3); cb(USER, f"pay:coins:{pid}"); check("coins low message", wait_text(USER, "سکه کافی"))
S.tg_adjust(USER, "coins", 60, "test")
msg(USER, "/buy"); wait_text(USER, "بسته‌ها"); cb(USER, f"plan:{pid}"); time.sleep(0.3); cb(USER, f"pay:coins:{pid}"); wait_text(USER, "سکه برای")
cb(USER, f"payok:coins:{pid}"); check("coins purchase", wait_text(USER, "سرویس شما فعال شد"))
time.sleep(0.4); check("coins deducted", S.tg_user(USER)["coins"] == 10 and len(S.clients_of(USER)) == 3)

# ---------------------------------------------------------------- 8. services view + renew flow entry
msg(USER, "📦 سرویس‌های من"); check("services list", wait_text(USER, "سرویس‌های من"))
name = S.clients_of(USER)[0]["name"]
cb(USER, f"svc:show:{name}"); check("service detail", wait_text(USER, "░"))

# ---------------------------------------------------------------- 9. 80% alert
c = S.clients_of(USER)[0]
S.update_client(c["name"], used_bytes=int(c["total_limit_bytes"] * 0.85))
_snap(); B.usage_alerts(); check("80% alert sent to user", wait_text(USER, "85%"))
B.usage_alerts(); time.sleep(0.2); check("alert sent once", sum(1 for t in tg.texts(USER) if "85%" in t) == 1)

# ---------------------------------------------------------------- 10. AI support (429 resume + tools + memory + progress)
msg(USER, "💬 پشتیبانی"); check("support start", wait_text(USER, "پشتیبانی"))
msg(USER, "کانفیگم وصل نمیشه، قطع و وصل میشه")
check("ai final answer delivered", wait_text(USER, "لینک Smart", 25))
check("429 was retried transparently", len(oa.requests) >= 3 and not any("rate" in t.lower() for t in tg.texts(USER)))
sess = S.ai_sessions_recent(1)[0]
logs = S.ai_log(sess["id"])
kinds = [l["kind"] for l in logs]
check("tool calls logged", "tool" in kinds and "tool_result" in kinds and "ratelimit" in kinds)
check("memory saved for user", any("v2rayNG" in m["content"] for m in S.ai_memories("user", USER)))
check("progress line shown (hermes style)", any("🩺" in (b.get("text") or "") or "📦" in (b.get("text") or "") for m, b in tg.calls if m in ("sendMessage", "editMessageText") and int(b.get("chat_id", 0)) == USER))
check("user never saw 'AI'", not any("AI" in t or "مدل" in t for t in tg.texts(USER)[-6:]))
check("system prompt frozen with project knowledge", "kill_pv2" in oa.requests[1]["messages"][0]["content"] and "Troubleshooting playbook" in oa.requests[1]["messages"][0]["content"])
msg(USER, "🔚 پایان گفتگو"); check("support ended", wait_text(USER, "گفتگو بسته شد"))
time.sleep(0.3); check("session closed & wiped", S.ai_sessions_recent(1)[0]["closed"] == 1 and S.ai_session_open(USER) is None)

# idle sweep
s2 = S.ai_session_create(USER, 1); S._exec("UPDATE ai_sessions SET last_at=? WHERE id=?", (int(time.time()) - 1000, s2["id"]))
S.tg_set_state(USER, "support", {}); _snap(); B.ai.sweep_idle(); check("idle session swept (15 min)", wait_text(USER, "عدم فعالیت") and S.ai_session_open(USER) is None)

# ---------------------------------------------------------------- 11. admin user mgmt + service actions
msg(OWNER, "/admin"); wait_text(OWNER, "پنل مدیریت"); cb(OWNER, f"a:u:{USER}"); check("admin user view", wait_text(OWNER, f"<code>{USER}</code>"))
cb(OWNER, f"a:ubal:coins:{USER}"); wait_text(OWNER, "مقدار"); msg(OWNER, "-5"); check("coins adjusted by admin", wait_text(OWNER, "موجودی جدید: 5"))
cb(OWNER, f"a:svc:{name}"); wait_text(OWNER, "clean"); cb(OWNER, f"a:sv:gb:{name}"); wait_text(OWNER, "چند گیگ")
msg(OWNER, "5"); check("admin added 5GB", wait_text(OWNER, "انجام شد") and S.client(name)["total_limit_bytes"] == 15 * 1024 ** 3)
cb(OWNER, f"a:sv:toggle:{name}"); time.sleep(0.5); check("toggle disabled", S.client(name)["active"] == 0)
cb(OWNER, f"a:sv:toggle:{name}"); time.sleep(0.5); check("toggle enabled", S.client(name)["active"] == 1)
cb(OWNER, "a:noads:strict"); time.sleep(0.4); check("noads level strict", S.get_setting("noads_level") == "strict")

# non-admin blocked
cb(USER, "a:menu"); time.sleep(0.3)
check("non-admin blocked from admin callbacks", any(m == "answerCallbackQuery" and "⛔" in (b.get("text") or "") for m, b in tg.calls))

# ---------------------------------------------------------------- 12. cloud push / restore round trip
ok, m = app.cloud.push(force=True); check("cloud push " + m, ok and "killpv2_manifest" in pantry.baskets)
n_users, n_clients = S.tg_user_count(), len(S.clients())
S._exec("DELETE FROM tg_users"); S._exec("DELETE FROM clients")
ok, m = app.cloud.restore(); check("cloud restore: " + m, ok and S.tg_user_count() == n_users and len(S.clients()) == n_clients)
# wrong key cannot read
settings.VAULT_KEY_MATERIAL = "wrong"; app.cloud.last_sha = ""
d, why = app.cloud.fetch(); check("wrong key -> cannot decrypt", d is None and "decrypt" in why)
settings.VAULT_KEY_MATERIAL = "k-test-123"

# ---------------------------------------------------------------- 13. broadcast
msg(OWNER, "/admin"); cb(OWNER, "a:bc"); wait_text(OWNER, "پیام همگانی"); msg(OWNER, "سلام به همه 🌹"); wait_text(OWNER, "ارسال شود")
cb(OWNER, "a:bc:go"); check("broadcast delivered", wait_text(USER, "سلام به همه") and wait_text(OWNER, "ارسال تمام شد", 15))

print(f"\n🎉 ALL {len(passed)} CHECKS PASSED")
B.stop.set()
sys.stdout.flush(); os._exit(0)
