"""Local mocks: Telegram Bot API, OpenAI-compatible chat API (tool calls + one 429), Pantry."""
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockTelegram:
    def __init__(self):
        self.calls = []
        self.updates = []
        self.msg_id = 100
        self.lock = threading.Lock()
        self.cv = threading.Condition(self.lock)

    def push_update(self, upd):
        with self.cv:
            self.updates.append(upd)
            self.cv.notify_all()

    def handle(self, method, body):
        with self.lock:
            self.calls.append((method, body))
        if method == "getMe":
            return {"id": 1, "is_bot": True, "username": "kpv2_test_bot", "first_name": "kpv2"}
        if method == "getUpdates":
            with self.cv:
                if not self.updates:
                    self.cv.wait(timeout=1.0)
                out, self.updates = self.updates, []
            return out
        if method in ("sendMessage", "sendPhoto", "sendDocument", "copyMessage"):
            with self.lock:
                self.msg_id += 1
                mid = self.msg_id
            return {"message_id": mid, "chat": {"id": int(body.get("chat_id", 0))}, "date": int(time.time()),
                    "text": body.get("text", body.get("caption", ""))}
        if method in ("editMessageText", "editMessageCaption", "editMessageReplyMarkup"):
            return {"message_id": int(body.get("message_id", 0)), "chat": {"id": int(body.get("chat_id", 0))}, "text": body.get("text", "")}
        return True

    def sent_to(self, chat_id, method="sendMessage"):
        with self.lock:
            return [b for m, b in self.calls if m == method and int(b.get("chat_id", 0)) == int(chat_id)]

    def texts(self, chat_id):
        return [b.get("text", "") for b in self.sent_to(chat_id)]

    def wait_for(self, pred, timeout=10):
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self.lock:
                snap = list(self.calls)
            if pred(snap):
                return True
            time.sleep(0.05)
        return False


class MockOpenAI:
    """first call -> 429 (tests resume); then list_services -> diagnose+memory -> final text."""

    def __init__(self):
        self.requests = []
        self.fail_429_once = True

    def handle(self, body):
        self.requests.append(body)
        if self.fail_429_once:
            self.fail_429_once = False
            return 429, {"error": {"message": "Rate limit reached", "type": "rate_limit"}}, {"Retry-After": "1"}
        msgs = body["messages"]
        tools = body.get("tools") or []
        tool_results = [m for m in msgs if m["role"] == "tool"]
        if tools and not tool_results:
            return 200, {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "list_services", "arguments": "{}"}}]}}]}, {}
        if tools and len(tool_results) == 1:
            try:
                svcs = json.loads(tool_results[0]["content"]).get("services", [])
            except Exception:
                svcs = []
            if svcs:
                return 200, {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "call_2", "type": "function", "function": {"name": "diagnose_service", "arguments": json.dumps({"client": svcs[0]["name"]})}},
                    {"id": "call_3", "type": "function", "function": {"name": "test_core_connectivity", "arguments": "{}"}},
                    {"id": "call_4", "type": "function", "function": {"name": "memory", "arguments": json.dumps(
                        {"action": "add", "target": "user", "content": "uses Android + v2rayNG, ISP MCI"})}}]}}]}, {}
        return 200, {"choices": [{"message": {"role": "assistant",
                                              "content": "سرویس‌ت فعاله و ترافیک داره رد میشه؛ لینک Smart رو ایمپورت کن و ساب رو آپدیت کن."}}],
                     "usage": {"total_tokens": 99}}, {}


class MockPantry:
    def __init__(self):
        self.baskets = {}

    def handle(self, method, path, body):
        parts = path.strip("/").split("/")
        if len(parts) == 3:
            return 200, {"name": "test", "baskets": [{"name": k, "ttl": 100000} for k in self.baskets]}
        name = parts[4]
        if method == "GET":
            if name not in self.baskets:
                return 400, {"error": "not found"}
            return 200, self.baskets[name]
        if method in ("POST", "PUT"):
            self.baskets[name] = body
            return 200, body
        if method == "DELETE":
            self.baskets.pop(name, None)
            return 200, {"ok": True}
        return 404, {}


def start(tg, oa, pantry, port=18080):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            try:
                return json.loads(raw.decode() or "{}")
            except Exception:
                return {"_raw": raw.decode(errors="ignore")}

        def _send(self, code, obj, headers=None):
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self): self._route("POST")
        def do_GET(self): self._route("GET")
        def do_PUT(self): self._route("PUT")
        def do_DELETE(self): self._route("DELETE")

        def _route(self, method):
            path = self.path.split("?")[0]
            body = self._body() if method in ("POST", "PUT") else {}
            if path.startswith("/bot"):
                return self._send(200, {"ok": True, "result": tg.handle(path.split("/")[-1], body)})
            if path.endswith("/chat/completions"):
                code, obj, hdr = oa.handle(body)
                return self._send(code, obj, hdr)
            if path.startswith("/apiv1/pantry"):
                code, obj = pantry.handle(method, path, body)
                return self._send(code, obj)
            self._send(404, {"error": "no route"})

    httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
