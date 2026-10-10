"""kill_pv2 orchestrator: boots store, Xray, panel, background loops, git sync."""
import os
import sys
import time
import subprocess
import threading

from . import settings
from .store import Store
from .xray import XrayManager
from .server import PanelState, serve
from .cloud import CloudSync
from . import chain


class App:
    def __init__(self):
        self.store = Store()
        self.source = self.store.load_vault()
        self.cloud = CloudSync(self.store, log=self.store.log)
        self.cloud_source = self._boot_cloud_restore()
        self.xray = XrayManager(self.store)
        self.bot = None
        self._last_cloud = 0
        self._chained = False
        self.state = PanelState(self.store, self.xray, settings.TUNNEL_HOST)
        self.state.on_change = self.on_change
        self.stop = threading.Event()
        self._speed_prev = {}
        self._last_git = 0
        self._git_lock = threading.Lock()

    def _boot_cloud_restore(self):
        """If the cloud snapshot is newer than the local vault (or local is empty), restore it."""
        if not self.cloud.enabled:
            return "cloud disabled"
        local_ts = 0
        try:
            if os.path.exists(settings.VAULT_PATH) and self.store.clients() or self.store.tg_user_count():
                local_ts = int(os.path.getmtime(settings.VAULT_PATH)) if os.path.exists(settings.VAULT_PATH) else 0
        except Exception:
            local_ts = 0
        try:
            return self.cloud.restore_if_newer(local_ts)
        except Exception as e:
            return f"cloud restore error: {e}"

    # ------------------------------------------------------------- change hook
    def on_change(self):
        """Called by the panel after any mutation: restart xray with new config, publish subs."""
        try:
            self.xray.apply_changes()
        except Exception as e:
            self.store.log("xray", f"apply failed: {e}", "error")
        self.publish(force=True)

    # ------------------------------------------------------------- log tail
    def _on_access(self, m, raw):
        email = m.get("email")
        if not email:
            return
        c = self.store.client(email)
        if not c:
            return
        src = (m.get("src") or "").strip("[]")
        host = m.get("host") or ""
        port = int(m.get("port") or 0)
        blocked = (m.get("out") or "").strip() == "block"
        now = int(time.time())
        # skip pure IP destinations with no sniffed domain for the visit list? keep them: they are still "sites"
        if src and src not in ("127.0.0.1", "::1"):
            self.store.touch_ip(email, src, now)
            if c["ip_limit"] and self.store.active_ip_count(email, 120) > c["ip_limit"]:
                self.store.log("security", f"{email} exceeded ip_limit={c['ip_limit']} ({src})", "warn")
        self.store.touch_visit(email, src or "unknown", host, port, blocked=blocked, ts=now)
        self.store.update_client(email, last_active_time=now, status="ONLINE")

    # ------------------------------------------------------------- loops
    def stats_loop(self):
        """Every 2s: pull exact byte deltas from Xray, compute live speeds, enforce limits."""
        last = time.time()
        while not self.stop.is_set():
            time.sleep(2)
            now = time.time()
            dt = max(0.5, now - last)
            last = now
            try:
                per = self.xray.poll_stats()
            except Exception as e:
                per = {}
                self.store.log("xray", f"poll error: {e}", "error")
            speeds = {}
            for name, v in per.items():
                speeds[name] = (int(v["up"] / dt), int(v["down"] / dt))
            self.state.live_speed = speeds
            self.enforce_limits()
            if self.bot:
                try:
                    self.bot.usage_alerts()
                except Exception as e:
                    self.store.log("bot", f"alerts error: {e}", "warn")

    def enforce_limits(self):
        now = int(time.time())
        changed = False
        for c in self.store.clients():
            if not c["active"]:
                continue
            over = c["total_limit_bytes"] > 0 and c["used_bytes"] >= c["total_limit_bytes"]
            expired = now >= c["created_at"] + c["expire_seconds"]
            if over or expired:
                self.store.update_client(c["name"], active=0, status="EXPIRED")
                self.store.log("client", f"{c['name']} expired ({'volume' if over else 'time'})", "warn")
                changed = True
            elif c["status"] == "ONLINE" and now - c["last_active_time"] > 45:
                self.store.update_client(c["name"], status="OFFLINE")
        if changed:
            self.on_change()

    def maintenance_loop(self):
        while not self.stop.is_set():
            time.sleep(settings.GIT_SYNC_INTERVAL)
            try:
                self.store.prune()
                self.publish()
            except Exception as e:
                self.store.log("sync", f"maintenance error: {e}", "error")
            try:
                if self.cloud.enabled and time.time() - self._last_cloud >= settings.CLOUD_SYNC_INTERVAL:
                    self._last_cloud = time.time()
                    ok, msg = self.cloud.push()
                    if not ok and self.bot:
                        self.bot.notify_owner("system", f"☁️ ذخیره در کلود ناموفق: <code>{msg[:200]}</code>")
            except Exception as e:
                self.store.log("cloud", f"sync error: {e}", "error")

    def owner(self, kind, text, force=False):
        if self.bot:
            self.bot.notify_owner(kind, text, force=force)

    # ------------------------------------------------------------- publish
    def publish(self, force=False):
        """Write sub files + encrypted vault, commit & push (rate-limited)."""
        with self._git_lock:
            try:
                self.state.subs.write_static_files()
                self.store.save_vault()
            except Exception as e:
                self.store.log("sync", f"write failed: {e}", "error")
                return
            if not settings.GIT_ENABLED:
                return
            if not force and time.time() - self._last_git < settings.GIT_SYNC_INTERVAL - 5:
                return
            self._last_git = time.time()
            cmds = [
                "git config --local user.email 'action@github.com'",
                "git config --local user.name 'kill_pv2 bot'",
                "git add -A sub_links data/vault.enc",
                "git rm -q --cached panel_db.json 2>/dev/null; true",
                "git commit -q -m '🔐 sync subs + encrypted vault [skip ci]' || true",
                "git pull -q --rebase -X ours || true",
                "git push -q || true",
            ]
            r = subprocess.run(" && ".join(cmds), shell=True, cwd=settings.ROOT_DIR, capture_output=True, text=True)
            if r.returncode == 0:
                print("🔗 [sync] subs + vault pushed", flush=True)
            else:
                self.store.log("sync", f"git failed: {(r.stderr or r.stdout)[-300:]}", "warn")

    # ------------------------------------------------------------- run
    def banner(self):
        host = settings.TUNNEL_HOST
        print("\n" + "=" * 64, flush=True)
        print("🛡️  kill_pv2 v2 — PANEL ACCESS", flush=True)
        print(f"🔗 PANEL URL : https://{host}{settings.PANEL_PREFIX}", flush=True)
        print(f"👤 USERNAME  : {settings.PANEL_USER}", flush=True)
        if self.state.generated_password:
            print(f"🔑 PASSWORD  : {self.state.password}   (⚠️ set PANEL_PASS secret to make it permanent)", flush=True)
        else:
            print("🔑 PASSWORD  : (from PANEL_PASS secret)", flush=True)
        print(f"🗄️  DB source : {self.source} | vault key: {settings.VAULT_KEY_ID}", flush=True)
        print(f"👥 clients   : {len(self.store.clients())} | tg users: {self.store.tg_user_count()}", flush=True)
        print(f"☁️  cloud     : {self.cloud_source}", flush=True)
        print(f"🤖 bot       : {'enabled' if settings.BOT_ENABLED else 'disabled (set BOT_TOKEN + OWNER_ID)'}", flush=True)
        print("=" * 64 + "\n", flush=True)

    def run(self):
        self.store.log("boot", f"starting; db={self.source}; tunnel={settings.TUNNEL_HOST}")
        if not self.xray.start():
            print("❌ xray failed to start, see events", flush=True)
        serve(self.state)
        threading.Thread(target=self.xray.tail_access_log, args=(self.stop, self._on_access), daemon=True).start()
        threading.Thread(target=self.stats_loop, daemon=True).start()
        threading.Thread(target=self.maintenance_loop, daemon=True).start()
        self.publish(force=True)
        if settings.BOT_ENABLED:
            try:
                from .bot.core import Bot
                self.bot = Bot(self)
                if self.bot.start():
                    self.owner("system", f"🟢 <b>ران جدید شروع شد</b>\n🌐 <code>{settings.TUNNEL_HOST}</code>\n"
                                         f"🗄 db: {self.source} | ☁️ {self.cloud_source}\n👥 {len(self.store.clients())} سرویس | "
                                         f"🔗 پنل: https://{settings.TUNNEL_HOST}{settings.PANEL_PREFIX}")
            except Exception as e:
                self.store.log("bot", f"failed to start: {e!r}", "error")
        self.banner()
        started = time.time()
        try:
            while time.time() - started < settings.RUN_DURATION and not self.stop.is_set():
                time.sleep(5)
                if not self.xray.is_running():
                    self.store.log("xray", "process died; restarting", "warn")
                    self.xray.start()
                remaining = settings.RUN_DURATION - (time.time() - started)
                # ~3 minutes before the end: snapshot, then dispatch the next run (owner-only notification)
                if remaining < 180 and not self._chained:
                    self._chained = True
                    self.xray.poll_stats()
                    self.publish(force=True)
                    if self.cloud.enabled:
                        self.cloud.push(force=True)
                    ok, msg = chain.trigger_next_run(log=self.store.log)
                    self.owner("system", f"{'🔁' if ok else '⚠️'} ران فعلی تا ۳ دقیقه دیگر تمام می‌شود — ران بعدی: {msg}", force=not ok)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop.set()
            self.xray.poll_stats()
            self.publish(force=True)
            if self.cloud.enabled:
                ok, msg = self.cloud.push(force=True)
                self.store.log("cloud", f"final push: {msg}")
            if self.bot:
                self.owner("system", "🔴 ران تمام شد؛ داده‌ها ذخیره شدند. آدرس سرور بعد از ران بعدی عوض می‌شود (ساب‌ها خودکار آپدیت می‌شوند).")
                self.bot.stop.set()
            self.store.log("boot", "shutdown complete")


def main():
    App().run()


if __name__ == "__main__":
    main()
