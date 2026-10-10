"""Xray lifecycle, optimized server config, exact traffic accounting & log tailing."""
import os
import re
import json
import time
import shutil
import subprocess
import threading

from . import settings
from .noads import NoAdsEngine, refresh_remote_lists
from .bypass import BypassEngine

_API = f"127.0.0.1:{settings.XRAY_API_PORT}"

# 2026/10/06 17:42:48 from 5.112.33.44:0 accepted tcp:example.com:443 [vless-in >> direct] email: u1
ACCESS_RE = re.compile(
    r"from\s+(?P<src>\[?[0-9a-fA-F:.]+\]?):\d+\s+accepted\s+(?P<proto>tcp|udp):(?P<host>[^:\s]+):(?P<port>\d+)"
    r"\s+\[(?P<in>[^\s\]]+)\s*(?:->|>>)\s*(?P<out>[^\]]+)\](?:\s+email:\s*(?P<email>\S+))?")


def _sudo(cmd):
    return ("sudo " + cmd) if settings.XRAY_USE_SUDO and shutil.which("sudo") else cmd


def _congestion():
    try:
        with open("/proc/sys/net/ipv4/tcp_available_congestion_control") as f:
            if "bbr" in f.read().split():
                return "bbr"
    except Exception:
        pass
    return None


def _sockopt(**extra):
    so = {"tcpKeepAliveInterval": 15, "tcpKeepAliveIdle": 60, "tcpNoDelay": True}
    cc = _congestion()
    if cc:
        so["tcpcongestion"] = cc
    so.update(extra)
    return so


class XrayManager:
    def __init__(self, store):
        self.store = store
        self.proc = None
        self._lock = threading.Lock()
        self.noads = NoAdsEngine()
        self.bypass = BypassEngine()
        self.reload_engines()

    def reload_engines(self):
        s = self.store
        if s.get_setting("noads_level", "balanced") == "strict":
            refresh_remote_lists(on_done=self._remote_ready)  # background; rebuilds config once lists land
        self.noads = NoAdsEngine(
            level=s.get_setting("noads_level", "balanced"), custom_block=s.get_setting("noads_custom_block", []),
            whitelist=s.get_setting("noads_whitelist", []), block_iran_ads=s.get_setting("noads_block_iran_ads", True))
        self.bypass = BypassEngine(
            iran_mode=s.get_setting("bypass_iran_mode", "direct"), custom_direct=s.get_setting("bypass_custom_direct", []),
            custom_proxy=s.get_setting("bypass_custom_proxy", []))

    def _remote_ready(self, count, sources):
        self.store.log("noads", f"remote blocklists loaded: {count} domains {sources}")
        try:
            self.apply_changes()
        except Exception as e:
            self.store.log("noads", f"apply after remote load failed: {e}", "warn")

    # --------------------------------------------------------------- config
    def build_config(self):
        active = [c for c in self.store.clients() if c["active"]]
        clients = [{"id": c["uuid"], "email": c["name"], "level": 0} for c in active]
        noads_users = [c["name"] for c in active if c["noads"]]

        rules = [{"type": "field", "inboundTag": ["api"], "outboundTag": "api"}]
        rules += self.bypass.xray_server_rules(block="block")
        if noads_users:
            for r in self.noads.xray_rules(outbound_block="block", outbound_direct="direct"):
                r = dict(r)
                r["user"] = noads_users  # per-client ad blocking
                rules.append(r)

        return {
            "log": {"loglevel": "warning", "access": settings.XRAY_ACCESS_LOG, "error": settings.XRAY_ERROR_LOG, "dnsLog": False},
            "api": {"tag": "api", "services": ["HandlerService", "StatsService", "RoutingService"]},
            "stats": {},
            "policy": {
                "levels": {"0": {"handshake": 4, "connIdle": 300, "uplinkOnly": 2, "downlinkOnly": 5, "bufferSize": 4,
                                 "statsUserUplink": True, "statsUserDownlink": True, "statsUserOnline": True}},
                "system": {"statsInboundUplink": True, "statsInboundDownlink": True,
                           "statsOutboundUplink": True, "statsOutboundDownlink": True},
            },
            "dns": {"servers": [{"address": "https://1.1.1.1/dns-query"}, {"address": "https://8.8.8.8/dns-query"},
                                "1.1.1.1", "8.8.8.8", "localhost"], "queryStrategy": "UseIPv4", "tag": "dns-internal"},
            "inbounds": [
                {"tag": "api", "listen": "127.0.0.1", "port": settings.XRAY_API_PORT, "protocol": "dokodemo-door",
                 "settings": {"address": "127.0.0.1"}},
                {"tag": "vless-in", "listen": "127.0.0.1", "port": settings.XRAY_INBOUND_PORT, "protocol": "vless",
                 "settings": {"clients": clients, "decryption": "none"},
                 "streamSettings": {"network": "ws", "wsSettings": {"path": settings.XRAY_WS_PATH}, "sockopt": _sockopt()},
                 "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "metadataOnly": False}},
            ],
            "outbounds": [
                {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"},
                 "streamSettings": {"sockopt": _sockopt(tcpFastOpen=True)}},
                {"tag": "block", "protocol": "blackhole", "settings": {"response": {"type": "http"}}},
            ],
            "routing": {"domainStrategy": "IPIfNonMatch", "rules": rules},
        }

    def write_config(self):
        cfg = self.build_config()
        os.makedirs(settings.XRAY_DIR, exist_ok=True)
        tmp = settings.XRAY_CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=1)
        os.replace(tmp, settings.XRAY_CONFIG_PATH)
        return cfg

    def test_config(self):
        r = subprocess.run([settings.XRAY_BIN, "run", "-test", "-config", settings.XRAY_CONFIG_PATH],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-1500:]

    # --------------------------------------------------------------- process
    def start(self):
        with self._lock:
            self.write_config()
            ok, msg = self.test_config()
            if not ok:
                self.store.log("xray", f"config test failed: {msg}", "error")
                return False
            self._kill()
            for p in (settings.XRAY_ACCESS_LOG, settings.XRAY_ERROR_LOG):
                subprocess.run(_sudo(f"touch {p} && chmod 666 {p}"), shell=True)
            self.proc = subprocess.Popen(_sudo(f"{settings.XRAY_BIN} run -config {settings.XRAY_CONFIG_PATH}"), shell=True,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            time.sleep(0.8)
            alive = self.is_running()
            n = len([c for c in self.store.clients() if c["active"]])
            self.store.log("xray", f"started pid={self.proc.pid} clients={n}" if alive else "failed to start",
                           "info" if alive else "error")
            return alive

    def _kill(self):
        subprocess.run(_sudo("pkill -f 'xray run -config'"), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)

    def is_running(self):
        return subprocess.run("pgrep -f 'xray run -config' >/dev/null", shell=True).returncode == 0

    def apply_changes(self):
        """Persist pending counters, rebuild config and restart (sub-second)."""
        self.poll_stats()
        self.reload_engines()
        return self.start()

    # --------------------------------------------------------------- stats
    def _api(self, *args, timeout=4):
        r = subprocess.run([settings.XRAY_BIN, "api", *args, f"--server={_API}"], capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[:300])
        return r.stdout

    def poll_stats(self):
        """Read exact per-user byte counters (reset after read) and persist deltas. Ground truth for billing."""
        try:
            data = json.loads(self._api("statsquery", "-pattern", "user>>>", "-reset") or "{}")
        except Exception:
            return {}
        per_user = {}
        for st in data.get("stat", []) or []:
            m = re.match(r"user>>>(.+?)>>>traffic>>>(uplink|downlink)", st.get("name", ""))
            val = int(st.get("value", 0) or 0)
            if not m or val <= 0:
                continue
            u = per_user.setdefault(m.group(1), {"up": 0, "down": 0})
            u["up" if m.group(2) == "uplink" else "down"] += val
        now = int(time.time())
        for u, v in per_user.items():
            self.store.add_traffic(u, v["up"], v["down"], ts=now)
        return per_user

    def online_ips(self, email):
        try:
            return json.loads(self._api("statsonlineiplist", "-email", email) or "{}").get("ips", {}) or {}
        except Exception:
            return {}

    def sys_stats(self):
        try:
            return json.loads(self._api("statssys") or "{}")
        except Exception:
            return {}

    # --------------------------------------------------------------- log tail
    def tail_access_log(self, stop_event, on_line):
        path = settings.XRAY_ACCESS_LOG
        while not os.path.exists(path) and not stop_event.is_set():
            time.sleep(0.5)
        f = open(path, "r", errors="ignore")
        f.seek(0, os.SEEK_END)
        inode = os.fstat(f.fileno()).st_ino
        while not stop_event.is_set():
            line = f.readline()
            if not line:
                try:
                    st = os.stat(path)
                    if st.st_ino != inode or st.st_size < f.tell():
                        f.close()
                        f = open(path, "r", errors="ignore")
                        inode = os.fstat(f.fileno()).st_ino
                except FileNotFoundError:
                    pass
                time.sleep(0.15)
                continue
            m = ACCESS_RE.search(line)
            if m:
                try:
                    on_line(m.groupdict(), line)
                except Exception as e:
                    print(f"tail error: {e}", flush=True)

    @staticmethod
    def parse_line(line):
        m = ACCESS_RE.search(line)
        return m.groupdict() if m else None
