"""Minimal, fast Telegram Bot API client (stdlib only).

* persistent HTTPS connections (keep-alive) per thread
* automatic handling of 429 (retry_after) and transient network errors
* long polling with a dedicated connection
* message splitting for >4096 chars
"""
import json
import time
import http.client
import threading
import urllib.parse
from urllib.parse import urlparse

from .. import settings

MAX_LEN = 4096


class TgError(Exception):
    def __init__(self, code, description, params=None):
        super().__init__(f"{code}: {description}")
        self.code = code
        self.description = description
        self.params = params or {}


class Telegram:
    def __init__(self, token=None, base=None):
        self.token = token or settings.BOT_TOKEN
        u = urlparse(base or settings.TG_API_BASE)
        self.host, self.scheme, self.port = u.hostname, u.scheme, u.port
        self.path_prefix = u.path.rstrip("/")
        self._local = threading.local()
        self.me = None

    # ------------------------------------------------------------ transport
    def _conn(self, timeout):
        c = getattr(self._local, "conn", None)
        if c is None or getattr(self._local, "timeout", None) != timeout:
            if c:
                try:
                    c.close()
                except Exception:
                    pass
            cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
            c = cls(self.host, self.port, timeout=timeout)
            self._local.conn = c
            self._local.timeout = timeout
        return c

    def _drop(self):
        c = getattr(self._local, "conn", None)
        if c:
            try:
                c.close()
            except Exception:
                pass
        self._local.conn = None

    def call(self, method, timeout=20, retries=3, _extra=None, **params):
        if _extra:
            params.update(_extra)
        payload = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                   for k, v in params.items() if v is not None}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        path = f"{self.path_prefix}/bot{self.token}/{method}"
        last = None
        for attempt in range(retries + 1):
            try:
                conn = self._conn(timeout)
                conn.request("POST", path, body=body, headers={"Content-Type": "application/json", "Connection": "keep-alive"})
                resp = conn.getresponse()
                data = json.loads(resp.read().decode("utf-8") or "{}")
            except Exception as e:  # network hiccup -> fresh connection
                last = e
                self._drop()
                time.sleep(min(2.0, 0.3 * (attempt + 1)))
                continue
            if data.get("ok"):
                return data.get("result")
            code = data.get("error_code", 0)
            desc = data.get("description", "")
            prm = data.get("parameters") or {}
            if code == 429:
                time.sleep(min(30, int(prm.get("retry_after", 1)) + 0.2))
                continue
            if code >= 500:
                last = TgError(code, desc, prm)
                time.sleep(0.5 * (attempt + 1))
                continue
            raise TgError(code, desc, prm)
        if last:
            raise last if isinstance(last, TgError) else TgError(0, f"network: {last}")
        raise TgError(0, "unknown")

    # ------------------------------------------------------------ helpers
    def get_me(self):
        self.me = self.call("getMe")
        return self.me

    def get_updates(self, offset=None, timeout=25):
        return self.call("getUpdates", timeout=timeout + 10, retries=1, offset=offset,
                         _extra={"timeout": timeout, "allowed_updates": ["message", "callback_query"]})

    def send(self, chat_id, text, reply_markup=None, parse_mode="HTML", disable_preview=True, reply_to=None):
        """Send text; splits long messages. Returns the last Message."""
        chunks = split_text(text)
        last = None
        for i, ch in enumerate(chunks):
            last = self.call("sendMessage", chat_id=chat_id, text=ch, parse_mode=parse_mode,
                             reply_markup=reply_markup if i == len(chunks) - 1 else None,
                             link_preview_options={"is_disabled": disable_preview},
                             reply_parameters={"message_id": reply_to} if reply_to else None)
        return last

    def edit(self, chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
        try:
            return self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=text[:MAX_LEN], parse_mode=parse_mode,
                             reply_markup=reply_markup, link_preview_options={"is_disabled": True})
        except TgError as e:
            if "message is not modified" in e.description:
                return None
            if "message can't be edited" in e.description or "message to edit not found" in e.description:
                return self.send(chat_id, text, reply_markup, parse_mode)
            raise

    def edit_markup(self, chat_id, message_id, reply_markup=None):
        try:
            return self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
        except TgError as e:
            if "not modified" in e.description:
                return None
            raise

    def edit_caption(self, chat_id, message_id, caption, reply_markup=None, parse_mode="HTML"):
        try:
            return self.call("editMessageCaption", chat_id=chat_id, message_id=message_id, caption=caption[:1024],
                             parse_mode=parse_mode, reply_markup=reply_markup)
        except TgError as e:
            if "not modified" in e.description:
                return None
            raise

    def delete(self, chat_id, message_id):
        try:
            return self.call("deleteMessage", chat_id=chat_id, message_id=message_id)
        except TgError:
            return None

    def answer_cb(self, cb_id, text=None, alert=False):
        try:
            return self.call("answerCallbackQuery", callback_query_id=cb_id, text=text, show_alert=alert)
        except TgError:
            return None

    def typing(self, chat_id, action="typing"):
        try:
            return self.call("sendChatAction", chat_id=chat_id, action=action, timeout=8, retries=0)
        except Exception:
            return None

    def send_photo(self, chat_id, file_id, caption="", reply_markup=None, parse_mode="HTML"):
        return self.call("sendPhoto", chat_id=chat_id, photo=file_id, caption=caption[:1024], parse_mode=parse_mode, reply_markup=reply_markup)

    def send_document(self, chat_id, file_id, caption="", reply_markup=None, parse_mode="HTML"):
        return self.call("sendDocument", chat_id=chat_id, document=file_id, caption=caption[:1024], parse_mode=parse_mode, reply_markup=reply_markup)

    def copy_message(self, chat_id, from_chat_id, message_id, caption=None, reply_markup=None, parse_mode="HTML"):
        return self.call("copyMessage", chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id,
                         caption=caption, parse_mode=parse_mode if caption else None, reply_markup=reply_markup)

    def set_commands(self, commands, scope=None, language_code=None):
        return self.call("setMyCommands", commands=commands, scope=scope, language_code=language_code)

    def delete_commands(self, scope=None, language_code=None):
        return self.call("deleteMyCommands", scope=scope, language_code=language_code)

    def upload_document(self, chat_id, filename, data: bytes, caption="", parse_mode="HTML"):
        """multipart upload (used for vault/backup exports to the owner)."""
        boundary = "----kpv2" + str(int(time.time() * 1000))
        parts = []
        for k, v in (("chat_id", str(chat_id)), ("caption", caption[:1024]), ("parse_mode", parse_mode)):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\n"
                     f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        conn = self._conn(60)
        conn.request("POST", f"{self.path_prefix}/bot{self.token}/sendDocument", body=body,
                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8") or "{}")
        if not data.get("ok"):
            raise TgError(data.get("error_code", 0), data.get("description", ""))
        return data["result"]


def split_text(text, limit=MAX_LEN):
    text = text or ""
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line) if cur else line
    if cur:
        out.append(cur)
    return out


def esc(s):
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ik(rows):
    """inline keyboard from [[(text, data_or_url), ...], ...]; tuples with 'http' are url buttons."""
    kb = []
    for row in rows:
        r = []
        for item in row:
            text, val = item[0], item[1]
            if isinstance(val, str) and val.startswith(("http://", "https://", "tg://")):
                r.append({"text": text, "url": val})
            else:
                r.append({"text": text, "callback_data": str(val)[:64]})
        kb.append(r)
    return {"inline_keyboard": kb}


def rk(rows, placeholder=None):
    """reply keyboard from [[text, ...], ...]"""
    return {"keyboard": [[{"text": t} for t in row] for row in rows], "resize_keyboard": True,
            "is_persistent": True, "input_field_placeholder": placeholder}


def remove_kb():
    return {"remove_keyboard": True}
