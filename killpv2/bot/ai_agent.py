"""AI support agent — a compact port of the Hermes Agent architecture:

* AIAgent-style synchronous turn loop:  model -> tool_calls -> tool results -> model ... -> final text
  (max iterations, strict role alternation, tool results appended as `tool` messages)
* System prompt is built ONCE per session (frozen snapshot: identity + project knowledge + memory + user context)
  and never mutated mid-session (prompt-cache friendly, exactly like Hermes).
* Memory tool (user profile + global notes) persisted in the store; mid-session writes hit the DB,
  not the prompt.
* Tool progress notifications in Hermes "{emoji} {verb}: {preview}" format (sent to the user as a single
  status message that is edited in place, and to the owner log).
* Rate limit handling: on 429 / overload wait AI_RATE_LIMIT_WAIT (10s) and retry the SAME request,
  resuming exactly where the loop was; never surfaced to the user. Retry-After header is honoured.
* Credential pool: several workers (BASE_URL + API key) with round-robin + sticky session affinity;
  a worker that is rate-limited is skipped for the retry so the turn continues on another key.
* Session hygiene: idle 15 min -> session closed & messages wiped; transcript kept in ai_log for the owner.
"""
import json
import time
import threading
import urllib.request
import urllib.error

from .. import settings
from . import ai_tools
from . import service as svc
from .tg import esc


# ------------------------------------------------------------------ errors
class RateLimited(Exception):
    def __init__(self, retry_after=None):
        super().__init__("rate limited")
        self.retry_after = retry_after


class ProviderError(Exception):
    pass


# ------------------------------------------------------------------ worker / provider
class Worker:
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"] or f"worker-{row['id']}"
        self.base_url = row["base_url"].rstrip("/")
        self.api_key = row["api_key"]
        self.model = row["model"]
        self.cooldown_until = 0.0

    def available(self):
        return time.time() >= self.cooldown_until

    def chat(self, messages, tools, model, temperature=0.3, timeout=90):
        url = self.base_url + ("/chat/completions" if not self.base_url.endswith("/chat/completions") else "")
        body = {"model": model or self.model, "messages": messages, "temperature": temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}",
                                              "User-Agent": "kill_pv2-support/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            txt = ""
            try:
                txt = e.read().decode("utf-8", "ignore")[:400]
            except Exception:
                pass
            if e.code == 429 or e.code in (502, 503, 529) or "rate" in txt.lower() and "limit" in txt.lower():
                ra = e.headers.get("Retry-After") if e.headers else None
                try:
                    ra = float(ra) if ra else None
                except Exception:
                    ra = None
                raise RateLimited(ra)
            raise ProviderError(f"HTTP {e.code}: {txt}")
        except urllib.error.URLError as e:
            raise ProviderError(f"network: {e.reason}")
        except TimeoutError:
            raise ProviderError("timeout")
        if "error" in data and not data.get("choices"):
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            if "rate" in msg.lower() or "quota" in msg.lower() or "overload" in msg.lower():
                raise RateLimited(None)
            raise ProviderError(msg[:300])
        try:
            return data["choices"][0]["message"], data.get("usage") or {}
        except Exception:
            raise ProviderError("malformed response")


class WorkerPool:
    """Round-robin over active workers with per-session affinity; rate-limited workers cool down."""

    def __init__(self, store):
        self.store = store
        self._rr = 0
        self._lock = threading.Lock()
        self._cache = {}

    def workers(self):
        rows = self.store.ai_workers(only_active=True)
        out = []
        for r in rows:
            w = self._cache.get(r["id"])
            if not w or (w.base_url, w.api_key, w.model) != (r["base_url"].rstrip("/"), r["api_key"], r["model"]):
                w = Worker(r)
                self._cache[r["id"]] = w
            out.append(w)
        return out

    def pick(self, preferred_id=None, exclude=()):
        ws = [w for w in self.workers() if w.id not in exclude]
        if not ws:
            return None
        if preferred_id:
            for w in ws:
                if w.id == preferred_id and w.available():
                    return w
        avail = [w for w in ws if w.available()] or ws
        with self._lock:
            w = avail[self._rr % len(avail)]
            self._rr += 1
        return w


# ------------------------------------------------------------------ prompt
PROJECT_KNOWLEDGE = """
## What this service is
kill_pv2: a VLESS (WebSocket + TLS behind Cloudflare Tunnel) VPN service sold through this Telegram bot.
Users buy a *plan* (volume in GB or unlimited, duration in days). Each purchase creates a *service* (also called config)
with a unique name like `ali_3f2a` and three link types:
- Simple subscription link (base64) -> works in v2rayNG (Android), Hiddify (all platforms), Streisand/Shadowrocket/V2Box (iOS), Nekoray/v2rayN (PC).
- Smart Xray JSON subscription -> v2rayNG "Custom config"/Hiddify; includes automatic clean-IP balancer (leastPing), TLS fragment for peak hours,
  ad-blocking (NoAds) and Iran-bypass (Iranian sites open without VPN).
- sing-box JSON -> for sing-box / Hiddify.
Links are also mirrored on GitHub (raw.githubusercontent.com) so they keep working even when the server address changes.
The server address (Cloudflare tunnel host) changes every ~5.5 hours when the backend rotates; subscription links refresh automatically
(users must "update subscription" in their app if they only imported a single config).

## Bot menu (reply keyboard + slash commands)
🛒 Buy config /buy -> list of plans -> plan -> pay by: 💳 card-to-card (send receipt photo -> admin approves, receipt gets an ID like R1A2B3C),
   👛 wallet (instant), 🪙 coins (instant, if plan has a coin price).
📦 My services /services -> each service: usage bar, remaining time, links, renew button.
👛 Wallet /wallet -> balance (Toman), coins, history, top-up (card-to-card only, preset or custom amount).
🪙 Coins & referral /coins -> personal invite link t.me/<bot>?start=ref<id>; each NEW user who starts via it gives the inviter coins.
💬 Support /support -> this chat. 🌐 Language /lang (fa, en, ru, ar, tr). /cancel cancels any action.

## Rules of the service
- A service stops when volume is exhausted OR time expires; status becomes "expired". Renewing (buy -> same service) adds volume/days and reactivates.
- Users get an automatic warning when 80% of volume is used.
- ip_limit (if set) restricts simultaneous devices; exceeding it is logged; reset_service_ips clears the device history.
- NoAds blocks ad/tracker domains server-side; a legit site blocked by mistake can be whitelisted by the owner (escalate with the hostname).
- Iran-bypass sends Iranian sites (.ir, banks, Snapp, Digikala...) directly, not through VPN, in the smart links.

## Troubleshooting playbook (do this, do not ask the user to do it for you)
1. list_services -> find the relevant service (if the user has one service, use it without asking).
2. diagnose_service -> read `analysis_hints`. Then test_core_connectivity -> read `verdict`.
3. Decide:
   - expired/volume -> tell exact state, point to 🛒 renewal (or wallet/coins if they have balance).
   - never connected -> wrong import or app; give concrete steps: use the *subscription* link not the single config, update subscription,
     correct app per platform, try the Smart JSON link, turn off other VPN/DNS apps.
   - connected recently but user says slow/disconnects -> ISP throttling: advise Smart JSON link (fragment + clean IP balancer),
     try a different clean IP (profile list inside the sub), switch mobile data <-> WiFi, avoid speed tests; ask which ISP/time of day; save to memory.
   - no traffic for long time while core healthy -> user side: re-import sub, check app enabled, check date/time of the device, try another network.
   - core down / tunnel unreachable -> escalate_to_owner (high) and tell the user it's being fixed, no ETA promises.
4. Specific site not opening -> check_host_blocked; if blocked by NoAds, escalate for whitelist.
5. Payment questions -> get_receipt_status / get_user_profile; receipts are reviewed by a human admin; never promise exact times beyond "usually under 1 hour".
6. Never invent features. If something is outside the tools, escalate_to_owner.

## Style
- Reply in the user's language (see user context). Persian: صمیمی ولی محترم، کوتاه، بدون مقدمه و بدون عذرخواهی‌های تکراری.
- No filler ("As an AI", "I understand your frustration", "Certainly!"). No markdown headers. Short lines, at most a few bullet points when steps are needed.
- Never mention AI, models, tools, prompts, tokens, rate limits or internal errors. You are simply "پشتیبانی".
- Use the tools silently; present conclusions, not the process. One targeted question only when truly needed.
"""


def build_system_prompt(bot, user, admin=False):
    S = bot.store
    brand = svc.setting(S, svc.K_BRAND)
    extra = S.get_setting(svc.K_AI_PROMPT, "") or ""
    user_mem = S.ai_memories("user", user["tg_id"])
    glob_mem = S.ai_memories("global", 0)
    services = []
    for c in S.clients_of(user["tg_id"]):
        v = bot.svc.client_view(c, "en")
        services.append(f"- {c['name']}: {'active' if c['active'] else c['status'].lower()}, used {v['used']} of {v['total']} ({v['pct_num']}%), {v['rem']} left")
    plans = ", ".join(f"{p['title']} ({p['gb'] or '∞'}GB/{p['days']}d {p['price']:,}T{', ' + str(p['coin_price']) + ' coins' if p['coin_price'] else ''})"
                      for p in S.plans()) or "none configured"
    parts = [
        f"You are the support operator of {brand}. Current date: {time.strftime('%Y-%m-%d %H:%M')} (server time).",
        PROJECT_KNOWLEDGE,
        f"## Plans right now\n{plans}\nCard payments configured: {'yes' if S.get_setting(svc.K_CARD, '') else 'no'}",
        f"## Current user\nname: {user['first_name']} | username: @{user['username'] or '-'} | id: {user['tg_id']} | language: {user['lang']} | "
        f"wallet: {user['wallet']:,} Toman | coins: {user['coins']} | referrals: {user['referrals']} | role: {'ADMIN/OWNER (admin tools enabled)' if admin else 'customer'}\n"
        f"services:\n" + ("\n".join(services) if services else "- (none)"),
    ]
    if user_mem:
        parts.append("## Memory about this user\n" + "\n".join(f"- [{m['id']}] {m['content']}" for m in user_mem))
    if glob_mem:
        parts.append("## Global memory (learned from all conversations)\n" + "\n".join(f"- [{m['id']}] {m['content']}" for m in glob_mem))
    parts.append("## Memory guidance\nYou have persistent memory via the `memory` tool. Save durable facts only: the user's device/OS/app, ISP, "
                 "recurring problems and what fixed them (target=user); new ISP blocking patterns or app quirks that help every future chat (target=global). "
                 "Never store secrets, links or one-off chatter. Memory is loaded fresh at the start of each session.")
    if extra.strip():
        parts.append("## Owner instructions\n" + extra.strip())
    return "\n\n".join(parts)


# ------------------------------------------------------------------ agent
class SupportAgent:
    def __init__(self, bot):
        self.bot = bot
        self.S = bot.store
        self.pool = WorkerPool(bot.store)
        self._busy = set()
        self._lock = threading.Lock()

    # ---- availability
    def available(self):
        return bool(self.pool.workers()) and bool(svc.setting(self.S, svc.K_SUPPORT_ON))

    # ---- session lifecycle
    def get_session(self, user, create=True):
        s = self.S.ai_session_open(user["tg_id"])
        if s and time.time() - s["last_at"] > settings.AI_SESSION_IDLE:
            self.close_session(s, reason="idle")
            s = None
        if s or not create:
            return s
        w = self.pool.pick()
        s = self.S.ai_session_create(user["tg_id"], w.id if w else 0)
        admin = self.bot.is_admin(user["tg_id"])
        s["messages"] = [{"role": "system", "content": build_system_prompt(self.bot, user, admin)}]
        self.S.ai_session_save(s["id"], s["messages"])
        self.S.ai_log_add(s["id"], user["tg_id"], "open", f"worker={w.id if w else 0} admin={admin}")
        self.S.log("ai", f"session {s['id']} opened for {user['tg_id']} (worker {w.name if w else '-'})")
        self.bot.notify_owner("ai", f"💬 گفتگوی پشتیبانی جدید <code>{s['id']}</code> — {esc(user['first_name'])} @{user['username'] or '-'} <code>{user['tg_id']}</code>")
        return s

    def close_session(self, s, reason="user"):
        turns = s.get("turns", 0)
        summary = f"closed ({reason}) after {turns} turns, {s.get('tool_calls', 0)} tool calls"
        self.S.ai_session_close(s["id"], summary)
        self.S.ai_log_add(s["id"], s["tg_id"], "close", reason)
        self.S.log("ai", f"session {s['id']} {summary}")
        self.bot.notify_owner("ai", f"🔚 گفتگوی <code>{s['id']}</code> بسته شد ({reason}) — {turns} پیام، {s.get('tool_calls', 0)} ابزار")

    def sweep_idle(self):
        for s in self.S.ai_sessions_idle(settings.AI_SESSION_IDLE):
            self.close_session(s, reason="idle")
            u = self.S.tg_user(s["tg_id"])
            if u and u["state"] == "support":
                self.S.tg_set_state(u["tg_id"], "", {})
                from .i18n import t
                try:
                    self.bot.tg.send(u["tg_id"], t(u["lang"], "sup.timeout"), self.bot.main_kb(u))
                except Exception:
                    pass

    # ---- turn
    def handle_message(self, user, text):
        """Runs one full agent turn synchronously (called from a worker thread)."""
        from .i18n import t
        tg, S = self.bot.tg, self.S
        uid = user["tg_id"]
        with self._lock:
            if uid in self._busy:
                tg.send(uid, t(user["lang"], "sup.busy"))
                return
            self._busy.add(uid)
        status_msg = None
        try:
            s = self.get_session(user)
            s["messages"].append({"role": "user", "content": text})
            S.ai_log_add(s["id"], uid, "user", text)
            show_progress = bool(svc.setting(S, svc.K_AI_USER_PROGRESS))
            typing_stop = threading.Event()
            threading.Thread(target=self._keep_typing, args=(uid, typing_stop), daemon=True).start()
            try:
                final, status_msg = self._run_loop(user, s, show_progress)
            finally:
                typing_stop.set()
            if status_msg:
                tg.delete(uid, status_msg)
            if final:
                S.ai_log_add(s["id"], uid, "assistant", final)
                tg.send(uid, esc(final), self.bot.support_kb(user))
            S.ai_session_save(s["id"], s["messages"], turns=s.get("turns", 0) + 1, tool_calls=s.get("tool_calls", 0))
        except ProviderError as e:
            S.log("ai", f"provider error for {uid}: {e}", "error")
            self.bot.notify_owner("ai", f"⚠️ خطای سرویس‌دهنده AI: <code>{esc(str(e)[:200])}</code>", force=True)
            tg.send(uid, t(user["lang"], "sup.unavailable"))
        except Exception as e:
            S.log("ai", f"turn failed for {uid}: {e!r}", "error")
            tg.send(uid, t(user["lang"], "sup.unavailable"))
        finally:
            with self._lock:
                self._busy.discard(uid)

    def _keep_typing(self, chat_id, stop):
        while not stop.is_set():
            self.bot.tg.typing(chat_id)
            stop.wait(4.5)

    def _call_model(self, s, tools, user):
        """One API call with Hermes-style retry: 429 -> wait (Retry-After or 10s) -> same request, rotating worker."""
        model = svc.setting(self.S, svc.K_AI_MODEL) or ""
        temp = float(svc.setting(self.S, svc.K_AI_TEMPERATURE) or 0.3)
        tried_limited = set()
        attempts = 0
        while True:
            w = self.pool.pick(preferred_id=s.get("worker"), exclude=tried_limited) or self.pool.pick(preferred_id=s.get("worker"))
            if not w:
                raise ProviderError("no AI worker configured")
            attempts += 1
            try:
                msg, usage = w.chat(s["messages"], tools, model or w.model, temperature=temp)
                self.S.ai_worker_stat(w.id, requests=1)
                if s.get("worker") != w.id:
                    s["worker"] = w.id
                    self.S._exec("UPDATE ai_sessions SET worker=? WHERE id=?", (w.id, s["id"]))
                return msg, usage
            except RateLimited as e:
                self.S.ai_worker_stat(w.id, requests=1, rate_limits=1)
                wait = min(60, e.retry_after) if e.retry_after else settings.AI_RATE_LIMIT_WAIT
                w.cooldown_until = time.time() + wait
                tried_limited.add(w.id)
                self.S.log("ai", f"rate limited on {w.name}; waiting {wait}s then resuming (attempt {attempts})", "warn")
                self.S.ai_log_add(s["id"], user["tg_id"], "ratelimit", f"{w.name} wait={wait}")
                if attempts >= 12:
                    raise ProviderError("persistent rate limit")
                # if another worker is free, switch immediately; else honour the wait
                alt = self.pool.pick(exclude=tried_limited)
                if not alt or not alt.available():
                    time.sleep(wait)
                    tried_limited.clear()
            except ProviderError as e:
                self.S.ai_worker_stat(w.id, requests=1, errors=1)
                if attempts >= 3:
                    raise
                time.sleep(2)

    def _run_loop(self, user, s, show_progress):
        """Hermes conversation loop. Returns (final_text, status_message_id)."""
        tg, S = self.bot.tg, self.S
        uid = user["tg_id"]
        admin = self.bot.is_admin(uid)
        tools = ai_tools.schemas(admin=admin)
        ctx = ai_tools.ToolContext(self.bot, user, s)
        status_id = None
        progress_lines = []
        for _ in range(settings.AI_MAX_ITERATIONS):
            msg, usage = self._call_model(s, tools, user)
            content = (msg.get("content") or "").strip()
            calls = msg.get("tool_calls") or []
            assistant = {"role": "assistant", "content": content or None}
            if calls:
                assistant["tool_calls"] = [{"id": c.get("id") or f"call_{i}", "type": "function",
                                            "function": {"name": c["function"]["name"], "arguments": c["function"].get("arguments") or "{}"}}
                                           for i, c in enumerate(calls)]
            s["messages"].append(assistant)
            if not calls:
                return content, status_id
            for tc in assistant["tool_calls"]:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except Exception:
                    args = {}
                line = ai_tools.preview(name, args)
                S.ai_log_add(s["id"], uid, "tool", f"{line} | args={json.dumps(args, ensure_ascii=False)[:300]}")
                if show_progress:
                    progress_lines.append(line)
                    txt = "\n".join(progress_lines[-6:])
                    try:
                        if status_id:
                            tg.edit(uid, status_id, f"<i>{esc(txt)}</i>")
                        else:
                            status_id = tg.send(uid, f"<i>{esc(txt)}</i>")["message_id"]
                    except Exception:
                        pass
                t0 = time.time()
                result = ai_tools.run(ctx, name, args)
                dur = time.time() - t0
                s["tool_calls"] = s.get("tool_calls", 0) + 1
                out = json.dumps(result, ensure_ascii=False, default=str)
                if len(out) > 6000:
                    out = out[:6000] + "...(truncated)"
                S.ai_log_add(s["id"], uid, "tool_result", f"{name} ({dur:.1f}s): {out[:1500]}")
                s["messages"].append({"role": "tool", "tool_call_id": tc["id"], "name": name, "content": out})
            S.ai_session_save(s["id"], s["messages"], tool_calls=s["tool_calls"])
        # iteration budget exhausted: one grace call without tools (Hermes "grace call")
        s["messages"].append({"role": "user", "content": "(Wrap up now with your best answer for the user based on what you found. No more tools.)"})
        msg, _ = self._call_model(s, None, user)
        s["messages"].append({"role": "assistant", "content": msg.get("content") or ""})
        return (msg.get("content") or "").strip(), status_id
