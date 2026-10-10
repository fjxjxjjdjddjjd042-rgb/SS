"""Business layer shared by bot flows, payments, admin and the AI support tools.

Everything that touches money or activates a service goes through here so that
rules (idempotency, ledger rows, logging, xray reload) live in exactly one place.
"""
import re
import json
import time
import secrets

from .. import settings
from ..subscription import fmt_bytes, remaining, fmt_duration
from .i18n import t, fmt_num

GB = 1024 ** 3

# settings keys (editable from the admin panel)
K_CARD = "pay_card_number"
K_HOLDER = "pay_card_holder"
K_COIN_PER_REF = "coin_per_referral"
K_WALLET_AMOUNTS = "wallet_amounts"
K_WALLET_MIN = "wallet_min"
K_BRAND = "bot_brand"
K_SUPPORT_ON = "support_enabled"
K_NOTIF = "owner_notifications"
K_AI_PROMPT = "ai_extra_prompt"
K_AI_MODEL = "ai_default_model"
K_AI_USER_PROGRESS = "ai_user_progress"
K_AI_TEMPERATURE = "ai_temperature"
K_ADMINS = "bot_admins"          # extra admin ids (receive receipts, limited panel)
K_ALERT_PCT = "usage_alert_pct"

DEFAULTS = {
    K_COIN_PER_REF: 10, K_WALLET_AMOUNTS: [50000, 100000, 200000, 500000], K_WALLET_MIN: 20000,
    K_BRAND: "kill_pv2", K_SUPPORT_ON: True, K_AI_USER_PROGRESS: True, K_AI_TEMPERATURE: 0.3, K_ADMINS: [],
    K_ALERT_PCT: 80,
    K_NOTIF: {"users": True, "sales": True, "receipts": True, "ai": True, "system": True, "alerts": True, "logs_warn": True},
}


def setting(store, key):
    v = store.get_setting(key, None)
    return DEFAULTS.get(key) if v is None else v


def progress_bar(pct, width=10):
    pct = max(0, min(100, pct))
    full = int(round(pct / 100 * width))
    return "▓" * full + "░" * (width - full)


def vol_text(lang, gb):
    return t(lang, "unlimited") if not gb else t(lang, "gb", n=fmt_num(gb))


def plan_text(lang, p):
    return t(lang, "buy.plan_btn", title=p["title"], vol=vol_text(lang, p["gb"]), days=t(lang, "days", n=p["days"]),
             price=fmt_num(p["price"]) + " " + ("ت" if lang == "fa" else "T"))


def gen_client_name(store, tg_user):
    base = re.sub(r"[^A-Za-z0-9_]", "", (tg_user.get("username") or "")[:12]) or f"u{tg_user['tg_id']}"
    for _ in range(50):
        name = f"{base}_{secrets.token_hex(2)}"
        if not store.client(name):
            return name
    return f"{base}_{secrets.token_hex(4)}"


class Service:
    def __init__(self, app):
        self.app = app          # killpv2.app.App (store, xray, state, bot)
        self.store = app.store

    # ------------------------------------------------------------------ views
    def client_view(self, c, lang="fa"):
        now = int(time.time())
        rem_b, rem_s = remaining(c, now)
        total = int(c["total_limit_bytes"] or 0)
        pct = min(100, round(c["used_bytes"] / total * 100, 1)) if total > 0 else 0
        online = bool(c["active"]) and now - (c["last_active_time"] or 0) <= 45
        if c["active"]:
            status = t(lang, "svc.status.active")
        else:
            status = t(lang, "svc.status.expired") if c["status"] == "EXPIRED" else t(lang, "svc.status.disabled")
        return {
            "name": c["name"], "status": status, "used": fmt_bytes(c["used_bytes"], zero="0 B"),
            "total": fmt_bytes(total, zero=t(lang, "unlimited")), "pct": pct, "bar": progress_bar(pct),
            "rem": fmt_duration(rem_s), "online": t(lang, "svc.online" if online else "svc.offline"),
            "rem_bytes": rem_b, "rem_seconds": rem_s, "active": bool(c["active"]), "pct_num": pct, "is_online": online,
        }

    def links(self, c):
        subs = self.app.state.subs
        base = f"https://{self.app.state.tunnel_host}"
        lines = subs.classic_lines(c)
        gh = subs.github_raw(c["name"])
        return {
            "sub": gh or f"{base}/sub/{c['name']}",
            "sub_json": subs.github_raw(c["name"], "json") or f"{base}/sub/{c['name']}.json",
            "sub_sb": subs.github_raw(c["name"], "singbox") or f"{base}/sub/{c['name']}.sb.json",
            "sub_live": f"{base}/sub/{c['name']}", "config": lines[0] if lines else "",
        }

    # ------------------------------------------------------------- fulfilment
    def activate_plan(self, tg_id, plan, method, amount, receipt_id=None, renew=None):
        """Create a new client (or extend `renew`) for tg_id according to plan. Returns client row."""
        S = self.store
        user = S.tg_user(tg_id)
        if not user:
            raise ValueError("unknown user")
        now = int(time.time())
        c = S.client(renew) if renew else None
        if c:
            if not plan["gb"] or c["total_limit_bytes"] == 0:
                total = 0  # unlimited plan or already unlimited
            else:
                total = (c["total_limit_bytes"] if c["active"] else c["used_bytes"]) + plan["gb"] * GB
            exp_at = c["created_at"] + c["expire_seconds"]
            if exp_at < now or not c["active"]:
                created_at, expire = now, plan["days"] * 86400
            else:
                created_at, expire = c["created_at"], c["expire_seconds"] + plan["days"] * 86400
            S.update_client(c["name"], total_limit_bytes=total, created_at=created_at, expire_seconds=expire, active=1,
                            status="OFFLINE", plan_id=plan["id"], owner_tg=int(tg_id))
            S.clear_alerts(c["name"])
            name = c["name"]
        else:
            name = gen_client_name(S, user)
            S.create_client(name, total_limit_bytes=plan["gb"] * GB, expire_seconds=plan["days"] * 86400,
                            ip_limit=plan.get("ip_limit", 0), owner_tg=int(tg_id), plan_id=plan["id"],
                            note=f"tg:{tg_id} plan:{plan['title']} via {method}")
        S.add_order(tg_id, plan["id"], name, method, amount, receipt_id)
        S.log("sale", f"{method}: user {tg_id} -> {name} plan={plan['title']} amount={amount} receipt={receipt_id or '-'}")
        self.app.on_change()
        return S.client(name)

    def pay_with_wallet(self, tg_id, plan, renew=None):
        bal = self.store.tg_adjust(tg_id, "wallet", -int(plan["price"]), reason=f"buy {plan['title']}", ref=f"plan:{plan['id']}")
        c = self.activate_plan(tg_id, plan, "wallet", plan["price"], renew=renew)
        return c, bal

    def pay_with_coins(self, tg_id, plan, renew=None):
        if not plan["coin_price"]:
            raise ValueError("no coin price")
        bal = self.store.tg_adjust(tg_id, "coins", -int(plan["coin_price"]), reason=f"buy {plan['title']}", ref=f"plan:{plan['id']}")
        c = self.activate_plan(tg_id, plan, "coins", 0, renew=renew)
        return c, bal

    def credit_wallet(self, tg_id, amount, reason, ref=""):
        return self.store.tg_adjust(tg_id, "wallet", int(amount), reason=reason, ref=ref)

    def fulfil_receipt(self, r):
        """Called exactly once after an approved receipt (decide_receipt guarantees it)."""
        S = self.store
        if r["kind"] == "wallet":
            bal = self.credit_wallet(r["tg_id"], r["amount"], "card top-up", ref=r["id"])
            return {"kind": "wallet", "balance": bal}
        plan = S.plan(r["plan_id"]) if r["plan_id"] else None
        if not plan:
            raise ValueError("plan deleted")
        renew = None
        txt = r.get("text") or ""
        if txt.startswith("{"):
            try:
                renew = (json.loads(txt) or {}).get("renew")
            except Exception:
                renew = None
        c = self.activate_plan(r["tg_id"], plan, "card", r["amount"], receipt_id=r["id"], renew=renew)
        return {"kind": "plan", "client": c, "plan": plan}

    # ------------------------------------------------------------- referrals
    def reward_referral(self, referrer_id, new_user_id):
        per = int(setting(self.store, K_COIN_PER_REF) or 0)
        if per <= 0 or not self.store.tg_user(referrer_id):
            return None
        bal = self.store.tg_adjust(referrer_id, "coins", per, reason="referral", ref=str(new_user_id))
        self.store.log("referral", f"{referrer_id} invited {new_user_id} (+{per} coins -> {bal})")
        return per, bal

    def referral_link(self, tg_id):
        me = (self.app.bot.tg.me if getattr(self.app, "bot", None) else None) or {}
        return f"https://t.me/{me.get('username', 'bot')}?start=ref{tg_id}"

    # ------------------------------------------------------------- diagnostics (used by AI + admin)
    def diagnose(self, c):
        """Collect everything relevant to 'my config does not work'. Pure facts, no LLM."""
        S, X = self.store, self.app.xray
        now = int(time.time())
        v = self.client_view(c)
        online_ips = X.online_ips(c["name"])
        ips = S.client_ips(c["name"])[:5]
        visits = S.visits(c["name"], limit=15)
        exp_at = c["created_at"] + c["expire_seconds"]
        return {
            "name": c["name"], "active": bool(c["active"]), "status": c["status"], "used": v["used"], "total": v["total"],
            "percent_used": v["pct_num"], "remaining_time": v["rem"], "expired_by_time": exp_at <= now,
            "expired_by_volume": bool(c["total_limit_bytes"] and c["used_bytes"] >= c["total_limit_bytes"]),
            "last_active_seconds_ago": int(now - (c["last_active_time"] or 0)) if c["last_active_time"] else None,
            "online_ips_now": list(online_ips.keys()) if isinstance(online_ips, dict) else online_ips,
            "recent_ips": [{"ip": r["ip"], "last_seen_seconds_ago": now - r["last_seen"], "hits": r["hits"]} for r in ips],
            "recent_hosts": [{"host": r["host"], "blocked": bool(r["blocked"]), "seconds_ago": now - r["last_seen"]} for r in visits],
            "ip_limit": c["ip_limit"], "clean_ip": c["clean_ip"], "noads": bool(c["noads"]), "bypass_iran": bool(c["bypass_iran"]),
            "xray_running": X.is_running(), "tunnel_host": self.app.state.tunnel_host,
            "server_uptime_seconds": int(now - self.app.state.started_at),
            "run_remaining_seconds": max(0, int(settings.RUN_DURATION - (now - self.app.state.started_at))),
        }
