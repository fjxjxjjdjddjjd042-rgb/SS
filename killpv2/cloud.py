"""Cloud persistence on getpantry.cloud (free, no auth — only an e-mail to create a pantry).

* Full encrypted snapshot (same AES-256-GCM vault blob as data/vault.enc) is base64'd and split into
  baskets `<prefix>_part0..N`; a manifest basket `<prefix>_manifest` holds count, sha256, timestamp.
* Writes are atomic from the reader's point of view: parts first, manifest last; reader verifies sha256.
* Encryption key = DB_ENCRYPTION_KEY (or derived from PANEL_PASS). The SAME secrets in another fork
  restore the same data — a fork without the key cannot read anything.
* Pantry TTL refreshes on every read/write; we touch it every 5 minutes, so data never expires while running.
* Boot order: local vault -> if cloud manifest is newer (or local missing) -> restore from cloud.
"""
import json
import time
import base64
import hashlib
import threading
import urllib.request
import urllib.error

from . import settings, crypto

import os
API = os.environ.get("PANTRY_API", "https://getpantry.cloud/apiv1/pantry")


class CloudSync:
    def __init__(self, store, log=None):
        self.store = store
        self.pid = settings.PANTRY_ID
        self.prefix = settings.CLOUD_BASKET_PREFIX
        self.enabled = bool(self.pid and settings.VAULT_KEY_MATERIAL)
        self.last_push = 0
        self.last_result = "never"
        self.last_sha = ""
        self._lock = threading.Lock()
        self._log = log or (lambda *a, **k: None)

    # ------------------------------------------------------------ http
    def _req(self, method, path, body=None, timeout=30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{API}/{self.pid}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json", "User-Agent": "kill_pv2"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read().decode("utf-8", "ignore")
                    return json.loads(raw) if raw.strip().startswith(("{", "[")) else raw
            except urllib.error.HTTPError as e:
                if e.code == 400 and method == "GET":
                    return None  # basket not found
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        return None

    def basket_get(self, name):
        return self._req("GET", f"/basket/{name}")

    def basket_put(self, name, obj):
        return self._req("POST", f"/basket/{name}", obj)

    def basket_del(self, name):
        try:
            return self._req("DELETE", f"/basket/{name}")
        except Exception:
            return None

    def info(self):
        return self._req("GET", "")

    # ------------------------------------------------------------ push
    def push(self, force=False):
        if not self.enabled:
            return False, "cloud disabled (PANTRY_ID or encryption key missing)"
        with self._lock:
            try:
                dump = self.store.export_all()
                blob = crypto.encrypt_json(dump, settings.VAULT_KEY_MATERIAL)
                sha = hashlib.sha256(blob).hexdigest()
                if not force and sha == self.last_sha:
                    self.last_result = "unchanged"
                    self._touch()
                    return True, "unchanged"
                b64 = base64.b64encode(blob).decode()
                size = settings.CLOUD_CHUNK_BYTES
                parts = [b64[i:i + size] for i in range(0, len(b64), size)] or [""]
                for i, p in enumerate(parts):
                    self.basket_put(f"{self.prefix}_part{i}", {"i": i, "data": p})
                manifest = {"version": 1, "parts": len(parts), "sha256": sha, "bytes": len(blob), "ts": int(time.time()),
                            "key_id": settings.VAULT_KEY_ID, "exported_at": dump["exported_at"],
                            "clients": len(dump["tables"].get("clients", [])), "users": len(dump["tables"].get("tg_users", []))}
                self.basket_put(f"{self.prefix}_manifest", manifest)
                # delete stale parts from a previous larger snapshot
                old = self._old_part_count()
                for j in range(len(parts), max(old, len(parts)) + 3):
                    self.basket_del(f"{self.prefix}_part{j}")
                self.last_push, self.last_sha = time.time(), sha
                self.last_result = f"ok {len(blob) // 1024}KB in {len(parts)} part(s)"
                self._log("cloud", f"pushed snapshot {sha[:10]} ({len(blob) // 1024}KB, {len(parts)} parts)")
                return True, self.last_result
            except Exception as e:
                self.last_result = f"error: {e}"
                self._log("cloud", f"push failed: {e}", "error")
                return False, str(e)

    def _old_part_count(self):
        try:
            inf = self.info() or {}
            names = [b["name"] for b in inf.get("baskets", []) if b["name"].startswith(f"{self.prefix}_part")]
            return len(names)
        except Exception:
            return 0

    def _touch(self):
        """Refresh TTL of all baskets without rewriting (a GET refreshes TTL)."""
        try:
            m = self.basket_get(f"{self.prefix}_manifest")
            for i in range(int((m or {}).get("parts", 0))):
                self.basket_get(f"{self.prefix}_part{i}")
        except Exception:
            pass

    # ------------------------------------------------------------ pull / restore
    def fetch(self):
        """Returns (dump_dict, manifest) or (None, reason)."""
        if not self.enabled:
            return None, "disabled"
        m = self.basket_get(f"{self.prefix}_manifest")
        if not m or "parts" not in m:
            return None, "no cloud snapshot"
        b64 = ""
        for i in range(int(m["parts"])):
            p = self.basket_get(f"{self.prefix}_part{i}")
            if not p or "data" not in p:
                return None, f"missing part {i}"
            b64 += p["data"]
        blob = base64.b64decode(b64)
        if hashlib.sha256(blob).hexdigest() != m.get("sha256"):
            return None, "checksum mismatch"
        try:
            dump = crypto.decrypt_json(blob, settings.VAULT_KEY_MATERIAL)
        except Exception:
            return None, f"cannot decrypt (key id here {settings.VAULT_KEY_ID}, snapshot {m.get('key_id')})"
        return dump, m

    def restore(self):
        dump, m = self.fetch()
        if not dump:
            return False, m
        with self._lock:
            self.store.import_all(dump)
            self.store.save_vault()
        self.last_sha = m.get("sha256", "")
        self._log("cloud", f"restored snapshot from {time.strftime('%Y-%m-%d %H:%M', time.localtime(m['ts']))} "
                           f"({m.get('clients')} clients, {m.get('users')} users)")
        return True, f"restored snapshot {time.strftime('%Y-%m-%d %H:%M', time.localtime(m['ts']))}: {m.get('clients')} clients, {m.get('users')} users"

    def restore_if_newer(self, local_exported_at):
        """Boot-time: prefer the newer of local vault vs cloud snapshot."""
        if not self.enabled:
            return "cloud disabled"
        try:
            m = self.basket_get(f"{self.prefix}_manifest")
        except Exception as e:
            return f"cloud unreachable: {e}"
        if not m or "exported_at" not in m:
            return "no cloud snapshot"
        if int(m["exported_at"]) <= int(local_exported_at or 0):
            self.last_sha = m.get("sha256", "")
            return f"local vault newer ({int(local_exported_at or 0) - int(m['exported_at'])}s)"
        ok, msg = self.restore()
        return msg

    def status(self):
        if not self.enabled:
            return "کلود غیرفعال (PANTRY_ID یا کلید رمزنگاری تنظیم نشده)"
        ago = f"{int(time.time() - self.last_push) // 60} دقیقه پیش" if self.last_push else "هنوز"
        return f"Pantry {self.pid[:8]}… | آخرین ذخیره: {ago} | نتیجه: {self.last_result}"
