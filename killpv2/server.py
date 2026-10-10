"""Panel HTTP server. Everything lives under PANEL_PREFIX (/KILLPV2); "/" is bland."""
import os
import re
import json
import time
import hmac
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from . import settings, crypto
from .subscription import SubscriptionBuilder, fmt_bytes, fmt_speed, remaining, fmt_duration

NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,40}$")
GB = 1024 ** 3
MB = 1024 ** 2


class PanelState:
    def __init__(self, store, xray, tunnel_host):
        self.store = store
        self.xray = xray
        self.tunnel_host = tunnel_host
        self.subs = SubscriptionBuilder(store, tunnel_host)
        self.sessions = {}
        self.started_at = time.time()
        self.on_change = lambda: None
        self.password = settings.PANEL_PASS
        self.generated_password = False
        if not self.password:
            self.password = secrets.token_urlsafe(10)
            self.generated_password = True
        self.live_speed = {}

    def new_session(self):
        tok = secrets.token_urlsafe(32)
        self.sessions[tok] = time.time() + settings.SESSION_TTL_SECONDS
        return tok

    def valid(self, tok):
        exp = self.sessions.get(tok)
        if not exp:
            return False
        if exp < time.time():
            self.sessions.pop(tok, None)
            return False
        return True


def _to_bytes(value, unit):
    try:
        v = float(value or 0)
    except Exception:
        v = 0
    return int(v * (GB if (unit or "GB").upper() == "GB" else MB))


def _flag(v):
    return v in (True, "true", 1, "1", "on")


def _domains(v):
    if isinstance(v, str):
        v = re.split(r"[\s,;]+", v)
    out, seen = [], set()
    for d in v or []:
        d = re.sub(r"^https?://", "", str(d).strip().lower()).split("/")[0].lstrip("*.").rstrip(".")
        if d and re.match(r"^[a-z0-9\.\-_:]+$", d) and d not in seen:
            seen.add(d)
            out.append(d)
    return out[:500]


def client_view(state, c, now):
    S = state.store
    rem_b, rem_s = remaining(c, now)
    total = int(c["total_limit_bytes"] or 0)
    pct = min(100, round(c["used_bytes"] / total * 100, 1)) if total > 0 else 0
    online = c["active"] and (now - (c["last_active_time"] or 0) <= 45)
    status = "ONLINE" if online else "OFFLINE"
    if not c["active"]:
        status = "EXPIRED" if c["status"] == "EXPIRED" else "DISABLED"
    up_s, down_s = state.live_speed.get(c["name"], (0, 0))
    return {
        "name": c["name"], "uuid": c["uuid"], "status": status, "active": bool(c["active"]),
        "used_bytes": c["used_bytes"], "up_bytes": c["up_bytes"], "down_bytes": c["down_bytes"],
        "total_bytes": total, "remaining_bytes": rem_b, "progress": pct,
        "used": fmt_bytes(c["used_bytes"], zero="0 B"), "total": fmt_bytes(total),
        "remaining": fmt_bytes(rem_b) if total > 0 else "نامحدود",
        "expire_at": int(c["created_at"]) + int(c["expire_seconds"]), "rem_seconds": rem_s, "rem_text": fmt_duration(rem_s),
        "created_at": c["created_at"], "expire_seconds": c["expire_seconds"], "clean_ip": c["clean_ip"], "note": c["note"],
        "noads": bool(c["noads"]), "bypass_iran": bool(c["bypass_iran"]), "ip_limit": c["ip_limit"],
        "online_ips": S.active_ip_count(c["name"], 120), "down_speed": fmt_speed(down_s), "up_speed": fmt_speed(up_s),
    }


# ---------------------------------------------------------------- API logic (testable without HTTP)
class Api:
    def __init__(self, state: PanelState):
        self.state = state
        self.S = state.store

    def login(self, ip, body):
        S, state = self.S, self.state
        fails, last = S.failed_logins(ip, settings.LOGIN_WINDOW_SECONDS)
        if fails >= settings.LOGIN_MAX_ATTEMPTS and time.time() - last < settings.LOGIN_LOCK_SECONDS:
            wait = int(settings.LOGIN_LOCK_SECONDS - (time.time() - last))
            S.log("security", f"locked login attempt from {ip}", "warn")
            return 429, {"error": "locked", "retry_after": wait}, None
        user = str(body.get("username", "")).strip()
        pw = str(body.get("password", ""))
        ok = hmac.compare_digest(user, settings.PANEL_USER) and hmac.compare_digest(pw, state.password)
        S.record_login(ip, ok)
        if not ok:
            time.sleep(min(3.0, 0.3 + 0.3 * fails))
            left = max(0, settings.LOGIN_MAX_ATTEMPTS - fails - 1)
            S.log("security", f"failed login from {ip} ({fails + 1}/{settings.LOGIN_MAX_ATTEMPTS})", "warn")
            return 401, {"error": "invalid", "attempts_left": left}, None
        S.clear_failed(ip)
        tok = state.new_session()
        S.log("security", f"login ok from {ip}")
        return 200, {"ok": True}, tok

    def overview(self, now):
        S, state = self.S, self.state
        cl = S.clients()
        online = sum(1 for c in cl if c["active"] and now - (c["last_active_time"] or 0) <= 45)
        day = S.traffic_totals_since(now - 86400)
        blocked = S.blocked_stats(now - 86400)
        sysst = state.xray.sys_stats()
        return {
            "tunnel_host": state.tunnel_host, "prefix": settings.PANEL_PREFIX, "uptime": int(now - state.started_at),
            "run_remaining": max(0, int(settings.RUN_DURATION - (now - state.started_at))),
            "clients_total": len(cl), "clients_active": sum(1 for c in cl if c["active"]), "online": online,
            "used_total": sum(c["used_bytes"] for c in cl),
            "day_up": sum(r["up"] or 0 for r in day), "day_down": sum(r["down"] or 0 for r in day),
            "ads_blocked_24h": blocked["blocked"], "requests_24h": blocked["total"],
            "xray_running": state.xray.is_running(), "xray_mem": sysst.get("Alloc", 0), "goroutines": sysst.get("NumGoroutine", 0),
            "repo": settings.REPO_FULL_NAME, "vault": settings.VAULT_KEY_ID != "none",
            "generated_password": state.generated_password,
            "noads_level": S.get_setting("noads_level", "balanced"), "bypass_mode": S.get_setting("bypass_iran_mode", "direct"),
            "top_blocked": S.top_blocked(8),
        }

    def links(self, c):
        state = self.state
        lines = state.subs.classic_lines(c)
        base = f"https://{state.tunnel_host}"
        return {"config": lines[0], "direct": lines[1] if len(lines) > 1 else None,
                "sub_live": f"{base}/sub/{c['name']}", "sub_json_live": f"{base}/sub/{c['name']}.json",
                "sub_singbox_live": f"{base}/sub/{c['name']}.sb.json",
                "sub_github": state.subs.github_raw(c["name"]), "sub_json_github": state.subs.github_raw(c["name"], "json"),
                "sub_singbox_github": state.subs.github_raw(c["name"], "singbox")}

    def _parse_common(self, body):
        f = {}
        if "unlimited" in body or "volume_value" in body:
            f["total_limit_bytes"] = 0 if _flag(body.get("unlimited")) else _to_bytes(body.get("volume_value", 0), body.get("volume_unit", "GB"))
        if "expire_days" in body or "expire_hours" in body:
            secs = int(float(body.get("expire_days") or 0)) * 86400 + int(float(body.get("expire_hours") or 0)) * 3600
            f["expire_seconds"] = secs if secs > 0 else 2592000
        if "clean_ip" in body:
            ip = str(body.get("clean_ip") or "").strip()
            if ip and not re.match(r"^[A-Za-z0-9\.\-:\[\]]{3,253}$", ip):
                raise ValueError("آی‌پی تمیز نامعتبر است")
            f["clean_ip"] = ip or settings.DEFAULT_CLEAN_IP
        if "note" in body:
            f["note"] = str(body.get("note") or "")[:200]
        for flag in ("noads", "bypass_iran"):
            if flag in body:
                f[flag] = 1 if _flag(body.get(flag)) else 0
        if "ip_limit" in body:
            f["ip_limit"] = max(0, int(float(body.get("ip_limit") or 0)))
        return f

    def create_client(self, body):
        S = self.S
        name = str(body.get("name") or body.get("username") or "").strip()
        if not NAME_RE.match(name):
            return 400, {"error": "نام فقط حروف انگلیسی/عدد/خط تیره (حداکثر ۴۰)"}
        if S.client(name):
            return 409, {"error": "این نام قبلاً وجود دارد"}
        f = self._parse_common(body)
        used = _to_bytes(body.get("initial_used_value", 0), body.get("initial_used_unit", "GB"))
        row = S.create_client(name, total_limit_bytes=f.get("total_limit_bytes", 0), used_bytes=used, down_bytes=used,
                              clean_ip=f.get("clean_ip"), expire_seconds=f.get("expire_seconds", 2592000), note=f.get("note", ""),
                              noads=f.get("noads", 1), bypass_iran=f.get("bypass_iran", 1), ip_limit=f.get("ip_limit", 0))
        S.log("client", f"created {name} limit={fmt_bytes(row['total_limit_bytes'])}")
        self.state.on_change()
        return 201, {"ok": True, "client": client_view(self.state, S.client(name), int(time.time()))}

    def edit_client(self, c, body):
        S = self.S
        name = c["name"]
        f = self._parse_common(body)
        if body.get("add_volume_value") not in (None, ""):
            cur = f.get("total_limit_bytes", c["total_limit_bytes"])
            f["total_limit_bytes"] = max(0, cur + _to_bytes(body["add_volume_value"], body.get("add_volume_unit", "GB")))
        if body.get("add_days") not in (None, ""):
            f["expire_seconds"] = max(3600, f.get("expire_seconds", c["expire_seconds"]) + int(float(body["add_days"])) * 86400)
        if body.get("set_used_value") not in (None, ""):
            used = _to_bytes(body["set_used_value"], body.get("set_used_unit", "GB"))
            f.update({"used_bytes": used, "down_bytes": used, "up_bytes": 0})
        if _flag(body.get("reset_usage")):
            f.update({"used_bytes": 0, "up_bytes": 0, "down_bytes": 0})
        if _flag(body.get("reset_time")):
            f["created_at"] = int(time.time())
        if _flag(body.get("regen_uuid")):
            import uuid as _u
            f["uuid"] = str(_u.uuid4())
        total = f.get("total_limit_bytes", c["total_limit_bytes"])
        used = f.get("used_bytes", c["used_bytes"])
        exp_at = f.get("created_at", c["created_at"]) + f.get("expire_seconds", c["expire_seconds"])
        if not c["active"] and c["status"] == "EXPIRED" and (total == 0 or used < total) and exp_at > time.time():
            f["active"] = 1
            f["status"] = "OFFLINE"
        if f:
            S.update_client(name, **f)
        new_name = str(body.get("new_name") or "").strip()
        if new_name and new_name != name:
            if not NAME_RE.match(new_name):
                return 400, {"error": "نام جدید نامعتبر است"}
            if S.client(new_name):
                return 409, {"error": "نام جدید تکراری است"}
            S.rename_client(name, new_name)
            name = new_name
        S.log("client", f"edited {c['name']}" + (f" -> {name}" if name != c["name"] else "") + f" fields={list(f)}")
        self.state.on_change()
        return 200, {"ok": True, "client": client_view(self.state, S.client(name), int(time.time()))}

    def toggle_client(self, c, now):
        S = self.S
        new_active = 0 if c["active"] else 1
        fields = {"active": new_active}
        if new_active:
            fields["status"] = "OFFLINE"
            if c["created_at"] + c["expire_seconds"] <= now:
                fields["created_at"] = now
            if c["total_limit_bytes"] and c["used_bytes"] >= c["total_limit_bytes"]:
                fields.update({"used_bytes": 0, "up_bytes": 0, "down_bytes": 0})
        S.update_client(c["name"], **fields)
        S.log("client", f"{'enabled' if new_active else 'disabled'} {c['name']}")
        self.state.on_change()
        return {"ok": True, "active": bool(new_active)}

    def noads(self, method, body):
        S, state = self.S, self.state
        if method == "PUT":
            if "level" in body:
                S.set_setting("noads_level", body["level"] if body["level"] in ("off", "balanced", "aggressive", "strict") else "balanced")
            if "custom_block" in body:
                S.set_setting("noads_custom_block", _domains(body["custom_block"]))
            if "whitelist" in body:
                S.set_setting("noads_whitelist", _domains(body["whitelist"]))
            if "block_iran_ads" in body:
                S.set_setting("noads_block_iran_ads", _flag(body["block_iran_ads"]))
            if not body.get("test"):
                S.log("noads", f"settings updated level={S.get_setting('noads_level')}")
                state.on_change()
        state.xray.reload_engines()
        out = state.xray.noads.summary()
        out["top_blocked"] = S.top_blocked(20)
        out["blocked_24h"] = S.blocked_stats(int(time.time()) - 86400)
        if method == "PUT" and body.get("test"):
            out["test_result"] = {h: state.xray.noads.is_blocked(h) for h in _domains(body["test"])}
        return out

    def bypass(self, method, body):
        S, state = self.S, self.state
        if method == "PUT":
            if "iran_mode" in body:
                S.set_setting("bypass_iran_mode", "direct" if body["iran_mode"] == "direct" else "proxy")
            if "custom_direct" in body:
                S.set_setting("bypass_custom_direct", _domains(body["custom_direct"]))
            if "custom_proxy" in body:
                S.set_setting("bypass_custom_proxy", _domains(body["custom_proxy"]))
            if not body.get("test"):
                S.log("bypass", "settings updated")
                state.on_change()
        state.xray.reload_engines()
        out = state.xray.bypass.summary()
        if method == "PUT" and body.get("test"):
            out["test_result"] = {h: state.xray.bypass.is_direct(h) for h in _domains(body["test"])}
        return out

    def settings_(self, method, body):
        S, state = self.S, self.state
        if method == "PUT":
            if "clean_pool" in body:
                S.set_setting("clean_pool", _domains(body["clean_pool"])[:12])
            S.log("settings", "updated")
            state.on_change()
        return {"clean_pool": S.get_setting("clean_pool", settings.DEFAULT_CLEAN_POOL), "tunnel_host": state.tunnel_host,
                "repo": settings.REPO_FULL_NAME, "vault_key_id": settings.VAULT_KEY_ID, "panel_user": settings.PANEL_USER,
                "login_max_attempts": settings.LOGIN_MAX_ATTEMPTS, "lock_seconds": settings.LOGIN_LOCK_SECONDS,
                "generated_password": state.generated_password, "run_duration": settings.RUN_DURATION}

    def history(self, name):
        S = self.S
        return {"ips": S.client_ips(name), "summary": S.visit_summary(name), "live_ips": self.state.xray.online_ips(name)}

    def export_history(self, name):
        S = self.S
        if not settings.VAULT_KEY_MATERIAL:
            raise ValueError("no encryption key configured")
        dump = {"client": name, "exported_at": int(time.time()), "ips": S.client_ips(name),
                "visits": S.visits(name, limit=100000), "traffic": S.traffic_series(name, 0)}
        return crypto.encrypt_json(dump, settings.VAULT_KEY_MATERIAL)


# ---------------------------------------------------------------- HTTP transport
def make_handler(state: PanelState):
    P = settings.PANEL_PREFIX
    S = state.store
    api = Api(state)

    class Handler(BaseHTTPRequestHandler):
        server_version = "nginx"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            return

        def client_ip(self):
            return (self.headers.get("CF-Connecting-IP") or self.headers.get("X-Real-IP")
                    or (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or self.client_address[0])

        def send(self, code, body=b"", ctype="text/plain; charset=utf-8", headers=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def js(self, obj, code=200, headers=None):
            self.send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", headers)

        def body_json(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > 512 * 1024:
                return {}
            raw = self.rfile.read(n)
            try:
                return json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                try:
                    return {k: v[0] for k, v in parse_qs(raw.decode("utf-8")).items()}
                except Exception:
                    return {}

        def token(self):
            m = re.search(r"(?:^|;\s*)kpv2=([A-Za-z0-9_\-]+)", self.headers.get("Cookie", ""))
            return m.group(1) if m else None

        def authed(self):
            t = self.token()
            return bool(t and state.valid(t))

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            u = urlparse(self.path)
            path, q = u.path, parse_qs(u.query)
            try:
                if path in ("", "/"):
                    return self.send(200, "service is active")
                if path.startswith("/sub/"):
                    return self.handle_sub(path[5:])
                if path == P or path == P + "/":
                    return self.serve_static("index.html")
                if path.startswith(P + "/static/"):
                    return self.serve_static(path[len(P) + 8:])
                if path.startswith(P + "/api/"):
                    return self.route("GET", path[len(P) + 5:], q, {})
                self.send(404, "not found")
            except Exception as e:
                S.log("panel", f"GET {path} error: {e}", "error")
                self.js({"error": str(e)}, 500)

        def do_POST(self):
            self._mut("POST")

        def do_PUT(self):
            self._mut("PUT")

        def do_DELETE(self):
            self._mut("DELETE")

        def _mut(self, method):
            u = urlparse(self.path)
            try:
                if u.path.startswith(P + "/api/"):
                    return self.route(method, u.path[len(P) + 5:], parse_qs(u.query), self.body_json())
                self.send(404, "not found")
            except ValueError as e:
                self.js({"error": str(e)}, 400)
            except Exception as e:
                S.log("panel", f"{method} {u.path} error: {e}", "error")
                self.js({"error": str(e)}, 500)

        def serve_static(self, name):
            name = os.path.basename(name)
            p = os.path.join(settings.WEB_DIR, name)
            if not os.path.isfile(p):
                return self.send(404, "not found")
            ctype = {"html": "text/html; charset=utf-8", "js": "application/javascript; charset=utf-8",
                     "css": "text/css; charset=utf-8", "svg": "image/svg+xml"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
            with open(p, "rb") as f:
                body = f.read()
            if name == "index.html":
                body = body.replace(b"__PREFIX__", P.encode())
            self.send(200, body, ctype, {"Cache-Control": "no-cache"})

        def handle_sub(self, rest):
            rest = unquote(rest)
            kind = ""
            if rest.endswith(".sb.json"):
                name, kind = rest[:-8], "singbox"
            elif rest.endswith(".json"):
                name, kind = rest[:-5], "json"
            else:
                name = rest
            c = S.client(name) if NAME_RE.match(name or "") else None
            if not c:
                return self.send(404, "not found")
            hdr = state.subs.headers(c)
            if kind == "json":
                return self.send(200, json.dumps(state.subs.xray_json(c), ensure_ascii=False), "application/json; charset=utf-8", hdr)
            if kind == "singbox":
                return self.send(200, json.dumps(state.subs.singbox_json(c), ensure_ascii=False), "application/json; charset=utf-8", hdr)
            self.send(200, state.subs.classic_b64(c), "text/plain; charset=utf-8", hdr)

        def route(self, method, route, q, body):
            parts = [unquote(p) for p in route.split("/") if p]
            if not parts:
                return self.js({"error": "bad route"}, 404)
            head = parts[0]
            if head == "login" and method == "POST":
                code, obj, tok = api.login(self.client_ip(), body)
                hdr = {}
                if tok:
                    hdr["Set-Cookie"] = f"kpv2={tok}; Path={P}; Max-Age={settings.SESSION_TTL_SECONDS}; HttpOnly; SameSite=Strict"
                if code == 429:
                    hdr["Retry-After"] = str(obj["retry_after"])
                return self.js(obj, code, hdr)
            if head == "logout" and method == "POST":
                t = self.token()
                if t:
                    state.sessions.pop(t, None)
                return self.js({"ok": True}, headers={"Set-Cookie": f"kpv2=; Path={P}; Max-Age=0; HttpOnly; SameSite=Strict"})
            if head == "ping":
                return self.js({"authed": self.authed(), "prefix": P})
            if not self.authed():
                return self.js({"error": "unauthorized"}, 401)

            now = int(time.time())
            if head == "overview":
                return self.js(api.overview(now))
            if head == "clients":
                rest = parts[1:]
                if not rest:
                    if method == "GET":
                        return self.js({"clients": [client_view(state, c, now) for c in S.clients()]})
                    if method == "POST":
                        code, obj = api.create_client(body)
                        return self.js(obj, code)
                    return self.js({"error": "method"}, 405)
                c = S.client(rest[0])
                if not c:
                    return self.js({"error": "no such client"}, 404)
                if len(rest) == 1:
                    if method == "PUT":
                        code, obj = api.edit_client(c, body)
                        return self.js(obj, code)
                    if method == "DELETE":
                        S.delete_client(c["name"], purge_history=_flag(body.get("purge_history")))
                        S.log("client", f"deleted {c['name']}")
                        state.on_change()
                        return self.js({"ok": True})
                    return self.js({"client": client_view(state, c, now)})
                if rest[1] == "toggle" and method == "POST":
                    return self.js(api.toggle_client(c, now))
                if rest[1] == "links":
                    return self.js(api.links(c))
                return self.js({"error": "not found"}, 404)
            if head == "history" and len(parts) >= 2:
                name = parts[1]
                if len(parts) == 2:
                    return self.js(api.history(name))
                if parts[2] == "visits":
                    ip = (q.get("ip") or [None])[0]
                    qq = (q.get("q") or [None])[0]
                    limit = max(10, min(2000, int((q.get("limit") or ["500"])[0])))
                    return self.js({"visits": S.visits(name, ip=ip, q=qq, limit=limit)})
                if parts[2] == "export":
                    blob = api.export_history(name)
                    return self.send(200, blob, "application/octet-stream",
                                     {"Content-Disposition": f'attachment; filename="{name}_history.kpv2"'})
            if head == "traffic" and len(parts) == 2:
                hours = max(1, min(24 * 30, int((q.get("hours") or ["24"])[0])))
                return self.js({"series": S.traffic_series(parts[1], now - hours * 3600)})
            if head == "noads":
                return self.js(api.noads(method, body))
            if head == "bypass":
                return self.js(api.bypass(method, body))
            if head == "settings":
                return self.js(api.settings_(method, body))
            if head == "logs":
                limit = max(10, min(1000, int((q.get("limit") or ["200"])[0])))
                kind = (q.get("kind") or [None])[0]
                return self.js({"events": S.events(limit, kind), "recent_visits": S.recent_visits(60)})
            if head == "apply" and method == "POST":
                state.on_change()
                return self.js({"ok": True, "xray_running": state.xray.is_running()})
            self.js({"error": "not found"}, 404)

    return Handler


def serve(state, port=settings.PANEL_PORT, bind=settings.PANEL_BIND):
    httpd = ThreadingHTTPServer((bind, port), make_handler(state))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
