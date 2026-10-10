"""Tools exposed to the AI support agent (Hermes-style registry: schema + handler + emoji/verb).

Every tool is scoped to the *current user* (tg_id) so the model can never read or
touch another customer's data. Admin-only tools are gated by `admin=True`.
"""
import json
import time
import socket
import subprocess
import urllib.request

from .. import settings
from . import service as svc

TOOLS = {}          # name -> {"schema":..., "fn":..., "emoji":..., "verb":..., "admin": bool}


def tool(name, description, params, emoji="⚙️", verb="", admin=False, required=None):
    def deco(fn):
        TOOLS[name] = {
            "schema": {"type": "function", "function": {"name": name, "description": description,
                                                        "parameters": {"type": "object", "properties": params, "required": required or []}}},
            "fn": fn, "emoji": emoji, "verb": verb or name, "admin": admin}
        return fn
    return deco


def schemas(admin=False):
    return [v["schema"] for v in TOOLS.values() if admin or not v["admin"]]


def preview(name, args):
    """Hermes-style one-line progress: '{emoji} {verb} {preview}'."""
    meta = TOOLS.get(name, {"emoji": "⚙️", "verb": name})
    arg = ""
    for k in ("client", "host", "query", "action", "content", "url"):
        if args.get(k):
            arg = str(args[k])[:60]
            break
    return f"{meta['emoji']} {meta['verb']}" + (f": {arg}" if arg else "")


class ToolContext:
    def __init__(self, bot, user, session):
        self.bot, self.user, self.session = bot, user, session
        self.S = bot.store
        self.svc = bot.svc
        self.admin = bot.is_admin(user["tg_id"])

    def own_client(self, name):
        c = self.S.client((name or "").strip())
        if not c:
            return None, {"error": f"no service named '{name}'"}
        if c["owner_tg"] != self.user["tg_id"] and not self.admin:
            return None, {"error": "this service does not belong to the current user"}
        return c, None


def run(ctx: ToolContext, name, args):
    meta = TOOLS.get(name)
    if not meta:
        return {"error": f"unknown tool {name}"}
    if meta["admin"] and not ctx.admin:
        return {"error": "admin only"}
    try:
        out = meta["fn"](ctx, **(args or {}))
    except TypeError as e:
        out = {"error": f"bad arguments: {e}"}
    except Exception as e:
        out = {"error": str(e)[:300]}
    return out


# =============================================================== user-scoped tools
@tool("get_user_profile", "Profile of the current user: balances, coins, referrals, language, number of services, pending receipts.",
      {}, emoji="👤", verb="Reading profile")
def _profile(ctx):
    u = ctx.S.tg_user(ctx.user["tg_id"])
    pend = ctx.S.receipts(status="pending", tg_id=u["tg_id"], limit=5)
    return {"tg_id": u["tg_id"], "name": u["first_name"], "username": u["username"], "lang": u["lang"], "wallet_toman": u["wallet"],
            "coins": u["coins"], "referrals": u["referrals"], "member_since": time.strftime("%Y-%m-%d", time.localtime(u["created_at"])),
            "services": [c["name"] for c in ctx.S.clients_of(u["tg_id"])],
            "pending_receipts": [{"id": r["id"], "kind": r["kind"], "amount": r["amount"]} for r in pend],
            "orders": [{"client": o["client"], "method": o["method"], "amount": o["amount"],
                        "date": time.strftime("%Y-%m-%d", time.localtime(o["created_at"]))} for o in ctx.S.orders(u["tg_id"], 10)]}


@tool("list_services", "List all services (configs) of the current user with usage, remaining time and status.", {},
      emoji="📦", verb="Listing services")
def _list(ctx):
    out = []
    for c in ctx.S.clients_of(ctx.user["tg_id"]):
        v = ctx.svc.client_view(c, "en")
        out.append({"name": c["name"], "active": bool(c["active"]), "status": c["status"], "used": v["used"], "total": v["total"],
                    "percent": v["pct_num"], "remaining_time": v["rem"], "online_now": v["is_online"]})
    return {"services": out} if out else {"services": [], "hint": "user has no services yet; guide them to buy"}


@tool("get_service_links", "Subscription links and single config for one of the user's services.",
      {"client": {"type": "string", "description": "service name"}}, emoji="🔗", verb="Fetching links", required=["client"])
def _links(ctx, client):
    c, err = ctx.own_client(client)
    return err or ctx.svc.links(c)


@tool("diagnose_service", "Full diagnostic of a service: status, expiry, volume, last activity, online IPs, recent hosts/blocked, "
      "server & xray health. Use FIRST when a user says the config is slow/disconnected/not working.",
      {"client": {"type": "string"}}, emoji="🩺", verb="Diagnosing", required=["client"])
def _diag(ctx, client):
    c, err = ctx.own_client(client)
    if err:
        return err
    d = ctx.svc.diagnose(c)
    hints = []
    if not d["active"]:
        hints.append("service inactive -> expired by " + ("volume" if d["expired_by_volume"] else "time" if d["expired_by_time"] else "admin"))
    elif d["last_active_seconds_ago"] is None:
        hints.append("never connected: client app/import problem (wrong link, old app, or ISP blocking TLS handshake)")
    elif d["last_active_seconds_ago"] < 120:
        hints.append("traffic flowing right now on server side -> if user sees issues it's likely ISP throttling / app DNS / specific site")
    else:
        hints.append(f"no traffic for {d['last_active_seconds_ago']}s -> client not reaching server (ISP block, wrong config, app off)")
    if d["ip_limit"] and len(d["online_ips_now"]) > d["ip_limit"]:
        hints.append("ip_limit exceeded: too many devices")
    if not d["xray_running"]:
        hints.append("CORE DOWN: xray not running -> escalate to owner")
    d["analysis_hints"] = hints
    return d


@tool("test_core_connectivity", "Test from the server side: xray health, tunnel reachability (TLS handshake to tunnel host), "
      "and HTTPS egress. Distinguishes 'server problem' from 'user internet problem'.", {}, emoji="🧪", verb="Testing core")
def _core(ctx):
    res = {"xray_running": ctx.bot.app.xray.is_running(), "tunnel_host": ctx.bot.app.state.tunnel_host}
    host = ctx.bot.app.state.tunnel_host
    t0 = time.time()
    try:
        s = socket.create_connection((host, 443), timeout=6)
        s.close()
        res["tunnel_tcp_443"] = {"ok": True, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        res["tunnel_tcp_443"] = {"ok": False, "error": str(e)[:120]}
    try:
        req = urllib.request.Request(f"https://{host}/", headers={"User-Agent": "kpv2-selftest"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read(64).decode(errors="ignore")
        res["tunnel_https"] = {"ok": True, "status": r.status, "ms": int((time.time() - t0) * 1000), "body": body.strip()[:40]}
    except Exception as e:
        res["tunnel_https"] = {"ok": False, "error": str(e)[:120]}
    try:
        t0 = time.time()
        with urllib.request.urlopen("https://www.gstatic.com/generate_204", timeout=8) as r:
            res["server_egress"] = {"ok": r.status == 204, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        res["server_egress"] = {"ok": False, "error": str(e)[:120]}
    try:
        res["xray_sys"] = ctx.bot.app.xray.sys_stats()
    except Exception:
        pass
    res["verdict"] = ("server healthy -> issue is on the user side (ISP filtering, wrong app settings, DNS, old link)"
                      if res["xray_running"] and res["tunnel_https"].get("ok") else "server side problem -> escalate to owner")
    return res


@tool("check_host_blocked", "Check whether a hostname is blocked by NoAds or routed direct by Iran-bypass for this user's config.",
      {"host": {"type": "string"}}, emoji="🔍", verb="Checking host", required=["host"])
def _host(ctx, host):
    X = ctx.bot.app.xray
    return {"host": host, "blocked_by_noads": X.noads.is_blocked(host), "direct_iran_bypass": X.bypass.is_direct(host),
            "note": "if blocked_by_noads is true and the user needs it, owner can whitelist it"}


@tool("list_plans", "Available plans with price (Toman) and coin price.", {}, emoji="🛒", verb="Loading plans")
def _plans(ctx):
    return {"plans": [{"id": p["id"], "title": p["title"], "gb": p["gb"] or "unlimited", "days": p["days"], "price_toman": p["price"],
                       "coin_price": p["coin_price"] or None} for p in ctx.S.plans()],
            "payment_methods": ["card_to_card (receipt reviewed by admin)", "wallet", "coins"],
            "card_configured": bool(ctx.S.get_setting(svc.K_CARD, ""))}


@tool("get_receipt_status", "Status of one of the user's receipts by ID (e.g. R1A2B3C).",
      {"receipt_id": {"type": "string"}}, emoji="🧾", verb="Checking receipt", required=["receipt_id"])
def _receipt(ctx, receipt_id):
    r = ctx.S.receipt(receipt_id.strip().upper())
    if not r or (r["tg_id"] != ctx.user["tg_id"] and not ctx.admin):
        return {"error": "receipt not found"}
    return {"id": r["id"], "kind": r["kind"], "amount": r["amount"], "status": r["status"],
            "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["created_at"])), "result": r["result"]}


@tool("reset_service_uuid", "Regenerate the UUID of the user's service (new links). Use ONLY if the user explicitly agrees, "
      "e.g. link leaked or suspected sharing.", {"client": {"type": "string"}}, emoji="🔑", verb="Rotating UUID", required=["client"])
def _regen(ctx, client):
    import uuid
    c, err = ctx.own_client(client)
    if err:
        return err
    ctx.S.update_client(c["name"], uuid=str(uuid.uuid4()))
    ctx.S.log("ai", f"uuid rotated for {c['name']} by support session {ctx.session['id']}")
    ctx.bot.app.on_change()
    return {"ok": True, "links": ctx.svc.links(ctx.S.client(c["name"]))}


@tool("reset_service_ips", "Forget the device/IP history of a service (fixes 'too many devices' / ip_limit lockouts).",
      {"client": {"type": "string"}}, emoji="📱", verb="Resetting devices", required=["client"])
def _reset_ips(ctx, client):
    c, err = ctx.own_client(client)
    if err:
        return err
    ctx.S._exec("DELETE FROM client_ips WHERE client=?", (c["name"],))
    ctx.S.log("ai", f"ips reset for {c['name']} (session {ctx.session['id']})")
    return {"ok": True}


@tool("send_links_to_user", "Send the subscription links message of a service directly to the user chat (nicely formatted).",
      {"client": {"type": "string"}}, emoji="📨", verb="Sending links", required=["client"])
def _send_links(ctx, client):
    c, err = ctx.own_client(client)
    if err:
        return err
    from .i18n import t
    from .tg import esc
    L = ctx.svc.links(c)
    ctx.bot.tg.send(ctx.user["tg_id"], t(ctx.user["lang"], "svc.links_text", name=c["name"], sub=L["sub"], sub_json=L["sub_json"],
                                          sub_sb=L["sub_sb"], config=esc(L["config"])))
    return {"ok": True, "note": "links delivered; do not repeat them in your reply"}


@tool("escalate_to_owner", "Notify the human owner about something you cannot solve (core down, payment dispute, refund, abuse). "
      "Include a precise summary. The user is NOT told that this is an escalation to a human.",
      {"summary": {"type": "string"}, "urgency": {"type": "string", "enum": ["low", "normal", "high"]}},
      emoji="🚨", verb="Escalating", required=["summary"])
def _escalate(ctx, summary, urgency="normal"):
    u = ctx.user
    icon = {"low": "ℹ️", "normal": "⚠️", "high": "🚨"}.get(urgency, "⚠️")
    from .tg import esc
    ctx.bot.notify_owner("ai", f"{icon} <b>ارجاع از پشتیبانی</b> (session <code>{ctx.session['id']}</code>)\n"
                               f"👤 {esc(u['first_name'])} @{u['username'] or '-'} <code>{u['tg_id']}</code>\n\n{esc(summary)}", force=True)
    ctx.S.log("ai", f"escalation ({urgency}) from {u['tg_id']}: {summary[:200]}", "warn")
    return {"ok": True, "note": "owner notified; tell the user it is being followed up"}


@tool("memory", "Persistent notes. target='user' = facts about THIS user (devices, ISP, recurring problems, preferences); "
      "target='global' = facts useful for every future conversation (new ISP block patterns, app quirks). "
      "Only durable, non-trivial facts. action=add|replace|remove.",
      {"action": {"type": "string", "enum": ["add", "replace", "remove", "list"]}, "target": {"type": "string", "enum": ["user", "global"]},
       "content": {"type": "string"}, "memory_id": {"type": "integer", "description": "for replace/remove"}},
      emoji="🧠", verb="Updating memory", required=["action", "target"])
def _memory(ctx, action, target, content="", memory_id=None):
    tg_id = ctx.user["tg_id"] if target == "user" else 0
    if action == "list":
        return {"memories": [{"id": m["id"], "content": m["content"]} for m in ctx.S.ai_memories(target, tg_id)]}
    if action == "add":
        if not content.strip():
            return {"error": "empty"}
        if len(ctx.S.ai_memories(target, tg_id)) >= (30 if target == "user" else 80):
            return {"error": "memory full; replace or remove an existing entry"}
        return {"ok": True, "id": ctx.S.ai_memory_add(target, content, tg_id)}
    rows = {m["id"] for m in ctx.S.ai_memories(target, tg_id)}
    if memory_id not in rows:
        return {"error": "memory_id not found in this target"}
    if action == "replace":
        ctx.S.ai_memory_replace(memory_id, content)
    else:
        ctx.S.ai_memory_remove(memory_id)
    return {"ok": True}


# =============================================================== admin-only tools (owner chatting with support)
@tool("admin_find_user", "ADMIN: find a telegram user by id/username/name, or the owner of a service.",
      {"query": {"type": "string"}}, emoji="🔎", verb="Searching users", admin=True, required=["query"])
def _find(ctx, query):
    q = query.strip().lstrip("@")
    c = ctx.S.client(q)
    if c and c["owner_tg"]:
        u = ctx.S.tg_user(c["owner_tg"])
        return {"owner_of_service": q, "user": u}
    return {"users": [{k: v for k, v in u.items() if k not in ("state_data",)} for u in ctx.S.tg_users(limit=10, q=q)]}


@tool("admin_service_action", "ADMIN: act on any service. action=add_gb|add_days|enable|disable|reset_usage|info",
      {"client": {"type": "string"}, "action": {"type": "string"}, "value": {"type": "number"}},
      emoji="🛠", verb="Admin action", admin=True, required=["client", "action"])
def _admin_svc(ctx, client, action, value=0):
    c = ctx.S.client(client)
    if not c:
        return {"error": "no such service"}
    GB = 1024 ** 3
    if action == "info":
        return ctx.svc.diagnose(c)
    if action == "add_gb":
        new = 0 if c["total_limit_bytes"] == 0 else c["total_limit_bytes"] + int(float(value) * GB)
        ctx.S.update_client(c["name"], total_limit_bytes=new, active=1, status="OFFLINE")
    elif action == "add_days":
        ctx.S.update_client(c["name"], expire_seconds=c["expire_seconds"] + int(float(value) * 86400), active=1, status="OFFLINE")
    elif action == "enable":
        ctx.S.update_client(c["name"], active=1, status="OFFLINE")
    elif action == "disable":
        ctx.S.update_client(c["name"], active=0, status="DISABLED")
    elif action == "reset_usage":
        ctx.S.update_client(c["name"], used_bytes=0, up_bytes=0, down_bytes=0, active=1, status="OFFLINE")
    else:
        return {"error": "unknown action"}
    ctx.S.clear_alerts(c["name"])
    ctx.S.log("ai", f"admin {ctx.user['tg_id']} via support: {action} {value} on {c['name']}")
    ctx.bot.app.on_change()
    return {"ok": True, "service": ctx.svc.client_view(ctx.S.client(c["name"]), "en")}


@tool("admin_adjust_balance", "ADMIN: add/remove wallet toman or coins for a user (delta may be negative).",
      {"tg_id": {"type": "integer"}, "kind": {"type": "string", "enum": ["wallet", "coins"]}, "delta": {"type": "integer"}, "reason": {"type": "string"}},
      emoji="💰", verb="Adjusting balance", admin=True, required=["tg_id", "kind", "delta"])
def _adjust(ctx, tg_id, kind, delta, reason="admin via support"):
    try:
        bal = ctx.S.tg_adjust(tg_id, kind, delta, reason=reason, ref=f"admin:{ctx.user['tg_id']}")
    except ValueError as e:
        return {"error": str(e)}
    ctx.S.log("ai", f"admin {ctx.user['tg_id']} adjusted {kind} {delta:+} for {tg_id}")
    return {"ok": True, "balance": bal}


@tool("admin_recent_logs", "ADMIN: recent system events (optionally filtered by kind: xray, client, sale, receipt, ai, security, sync, cloud).",
      {"kind": {"type": "string"}, "limit": {"type": "integer"}}, emoji="📜", verb="Reading logs", admin=True)
def _logs(ctx, kind=None, limit=30):
    return {"events": [{"t": time.strftime("%H:%M:%S", time.localtime(e["ts"])), "lvl": e["level"], "kind": e["kind"], "msg": e["message"][:200]}
                       for e in ctx.S.events(min(100, limit or 30), kind or None)]}
