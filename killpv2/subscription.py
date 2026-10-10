"""Subscription builders: classic base64, smart Xray JSON (balancer+fragment+noads+bypass), sing-box JSON."""
import os
import base64
import json
import time
from urllib.parse import quote

from . import settings
from .noads import NoAdsEngine
from .bypass import BypassEngine


def fmt_bytes(b, zero="نامحدود"):
    b = int(b or 0)
    if b == 0:
        return zero
    for unit, div in (("TB", 1024 ** 4), ("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if b >= div:
            return f"{b / div:.2f} {unit}" if unit in ("TB", "GB") else f"{b / div:.1f} {unit}"
    return f"{b} B"


def fmt_speed(bps):
    kb = (bps or 0) / 1024
    return f"{kb / 1024:.1f} MB/s" if kb >= 1024 else f"{kb:.0f} KB/s"


def remaining(c, now=None):
    now = now or int(time.time())
    total, used = int(c["total_limit_bytes"] or 0), int(c["used_bytes"] or 0)
    rem_bytes = max(0, total - used) if total > 0 else 0
    rem_sec = max(0, int(c["created_at"]) + int(c["expire_seconds"]) - now)
    return rem_bytes, rem_sec


def fmt_duration(sec):
    d, h, m = sec // 86400, (sec % 86400) // 3600, (sec % 3600) // 60
    if d > 0:
        return f"{d} روز و {h} ساعت"
    if h > 0:
        return f"{h} ساعت و {m} دقیقه"
    return f"{m} دقیقه"


def vless_uri(uuid, address, host, tag, path=settings.XRAY_WS_PATH, port=443):
    q = (f"path={quote(path, safe='')}&security=tls&encryption=none&type=ws&host={host}&sni={host}"
         f"&fp=chrome&alpn=http%2F1.1")
    return f"vless://{uuid}@{address}:{port}?{q}#{quote(tag, safe='')}"


class SubscriptionBuilder:
    def __init__(self, store, tunnel_host=None):
        self.store = store
        self.tunnel_host = tunnel_host or settings.TUNNEL_HOST

    def clean_pool(self, client):
        pool = [client["clean_ip"] or settings.DEFAULT_CLEAN_IP]
        for ip in (self.store.get_setting("clean_pool", settings.DEFAULT_CLEAN_POOL) or []):
            if ip and ip not in pool:
                pool.append(ip)
        return pool[:8]

    def engines(self, client):
        s = self.store
        noads = NoAdsEngine(level=s.get_setting("noads_level", "balanced") if client["noads"] else "off",
                            custom_block=s.get_setting("noads_custom_block", []), whitelist=s.get_setting("noads_whitelist", []),
                            block_iran_ads=s.get_setting("noads_block_iran_ads", True))
        bypass = BypassEngine(iran_mode="direct" if client["bypass_iran"] else "proxy",
                              custom_direct=s.get_setting("bypass_custom_direct", []), custom_proxy=s.get_setting("bypass_custom_proxy", []))
        return noads, bypass

    def headers(self, client):
        total = int(client["total_limit_bytes"] or 0)
        expire = int(client["created_at"]) + int(client["expire_seconds"])
        return {
            "Subscription-Userinfo": f"upload={int(client['up_bytes'])}; download={int(client['down_bytes'])}; total={total}; expire={expire}",
            "Profile-Title": "base64:" + base64.b64encode(f"kill_pv2 • {client['name']}".encode()).decode(),
            "Profile-Update-Interval": "1",
        }

    # ---------------------------------------------------------------- base64
    def classic_lines(self, client):
        c, h = client, self.tunnel_host
        if not c["active"]:
            return ["// ACCOUNT EXPIRED OR DISABLED"]
        rem_b, rem_s = remaining(c)
        pool = self.clean_pool(c)
        lines = [vless_uri(c["uuid"], pool[0], h, f"{c['name']} ⚡ Clean"), vless_uri(c["uuid"], h, h, f"{c['name']} 🌐 Direct")]
        for i, ip in enumerate(pool[1:3], 1):
            lines.append(vless_uri(c["uuid"], ip, h, f"{c['name']} 🛰️ Pool-{i}"))
        total = int(c["total_limit_bytes"] or 0)
        lines += [
            vless_uri(c["uuid"], pool[0], h, f"📊 مصرف: {fmt_bytes(c['used_bytes'], zero='0 B')}"),
            vless_uri(c["uuid"], pool[0], h, f"💾 باقی‌مانده: {fmt_bytes(rem_b) if total > 0 else 'نامحدود'}"),
            vless_uri(c["uuid"], pool[0], h, f"⏳ زمان: {fmt_duration(rem_s)}"),
        ]
        return lines

    def classic_b64(self, client):
        return base64.b64encode(("\n".join(self.classic_lines(client)) + "\n").encode("utf-8")).decode()

    # ---------------------------------------------------------------- xray json
    def xray_json(self, client):
        c, h = client, self.tunnel_host
        noads, bypass = self.engines(c)
        pool = self.clean_pool(c)

        def ob(tag, address):
            return {
                "tag": tag, "protocol": "vless",
                "settings": {"vnext": [{"address": address, "port": 443, "users": [{"id": c["uuid"], "encryption": "none", "level": 0}]}]},
                "streamSettings": {
                    "network": "ws", "security": "tls",
                    "tlsSettings": {"serverName": h, "allowInsecure": False, "fingerprint": "chrome", "alpn": ["http/1.1"]},
                    "wsSettings": {"path": settings.XRAY_WS_PATH, "host": h},
                    "sockopt": {"dialerProxy": "fragment", "tcpKeepAliveIdle": 60, "tcpNoDelay": True},
                },
                "mux": {"enabled": False},
            }

        proxies = [ob(f"proxy-{i}", ip) for i, ip in enumerate(pool)] + [ob("proxy-direct", h)]
        proxy_tags = [o["tag"] for o in proxies]
        outbounds = proxies + [
            {"tag": "fragment", "protocol": "freedom",
             "settings": {"fragment": {"packets": "tlshello", "length": "10-30", "interval": "2-5"}},
             "streamSettings": {"sockopt": {"tcpNoDelay": True, "tcpKeepAliveIdle": 60}}},
            {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}},
            {"tag": "block", "protocol": "blackhole", "settings": {"response": {"type": "http"}}},
            {"tag": "dns-out", "protocol": "dns"},
        ]

        def to_balancer(rule_list):
            out = []
            for r in rule_list:
                r = dict(r)
                if r.get("outboundTag") == "__proxy__":
                    r.pop("outboundTag")
                    r["balancerTag"] = "fast"
                out.append(r)
            return out

        rules = [{"type": "field", "inboundTag": ["socks-in", "http-in"], "port": 53, "outboundTag": "dns-out"}]
        rules += to_balancer(noads.xray_rules(outbound_block="block", outbound_direct="__proxy__"))
        rules += to_balancer(bypass.xray_client_rules(direct="direct", proxy="__proxy__"))
        rules.append({"type": "field", "network": "udp", "balancerTag": "fast"})
        rules.append({"type": "field", "network": "tcp,udp", "balancerTag": "fast"})

        return {
            "remarks": f"kill_pv2 • {c['name']} • Smart",
            "log": {"loglevel": "warning"},
            "dns": {"servers": [{"address": "https://1.1.1.1/dns-query"}, {"address": "https://8.8.8.8/dns-query"},
                                {"address": "178.22.122.100", "domains": ["geosite:category-ir", "regexp:\\.ir$"], "skipFallback": True},
                                "localhost"], "queryStrategy": "UseIPv4"},
            "inbounds": [
                {"tag": "socks-in", "listen": "127.0.0.1", "port": 10808, "protocol": "socks", "settings": {"udp": True, "auth": "noauth"},
                 "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]}},
                {"tag": "http-in", "listen": "127.0.0.1", "port": 10809, "protocol": "http"},
            ],
            "outbounds": outbounds,
            "routing": {"domainStrategy": "IPIfNonMatch",
                        "balancers": [{"tag": "fast", "selector": proxy_tags, "strategy": {"type": "leastPing"}, "fallbackTag": "proxy-direct"}],
                        "rules": rules},
            "observatory": {"subjectSelector": proxy_tags, "probeURL": "https://www.gstatic.com/generate_204",
                            "probeInterval": "45s", "enableConcurrency": True},
            "policy": {"levels": {"0": {"handshake": 4, "connIdle": 300, "uplinkOnly": 1, "downlinkOnly": 1, "bufferSize": 4}}},
        }

    # ---------------------------------------------------------------- sing-box
    def singbox_json(self, client):
        c, h = client, self.tunnel_host
        noads, bypass = self.engines(c)
        pool = self.clean_pool(c)

        def ob(tag, address):
            return {"type": "vless", "tag": tag, "server": address, "server_port": 443, "uuid": c["uuid"],
                    "tls": {"enabled": True, "server_name": h, "utls": {"enabled": True, "fingerprint": "chrome"}, "alpn": ["http/1.1"]},
                    "transport": {"type": "ws", "path": settings.XRAY_WS_PATH, "headers": {"Host": h}},
                    "tcp_fast_open": True, "tls_fragment": {"enabled": True, "size": "10-30", "sleep": "2-5"}}

        nodes = [ob(f"proxy-{i}", ip) for i, ip in enumerate(pool)] + [ob("proxy-direct", h)]
        tags = [o["tag"] for o in nodes]
        outbounds = [
            {"type": "selector", "tag": "proxy", "outbounds": ["auto"] + tags, "default": "auto"},
            {"type": "urltest", "tag": "auto", "outbounds": tags, "url": "https://www.gstatic.com/generate_204",
             "interval": "45s", "tolerance": 60, "interrupt_exist_connections": False},
        ] + nodes + [{"type": "direct", "tag": "direct"}, {"type": "block", "tag": "block"}, {"type": "dns", "tag": "dns-out"}]
        rules = [{"protocol": "dns", "outbound": "dns-out"}]
        rules += noads.singbox_rules(outbound_block="block", outbound_direct="proxy")
        rules += bypass.singbox_client_rules(direct="direct", proxy="proxy")
        return {
            "log": {"level": "warn"},
            "dns": {"servers": [{"tag": "dns-remote", "address": "https://1.1.1.1/dns-query", "detour": "proxy"},
                                {"tag": "dns-ir", "address": "178.22.122.100", "detour": "direct"},
                                {"tag": "dns-local", "address": "local", "detour": "direct"}],
                    "rules": [{"rule_set": ["geosite-ir"], "server": "dns-ir"}, {"domain_suffix": [".ir"], "server": "dns-ir"},
                              {"outbound": "any", "server": "dns-local"}],
                    "final": "dns-remote", "strategy": "ipv4_only", "independent_cache": True},
            "inbounds": [
                {"type": "tun", "tag": "tun-in", "address": ["172.19.0.1/30"], "auto_route": True, "strict_route": False,
                 "stack": "mixed", "sniff": True, "sniff_override_destination": True},
                {"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 2080, "sniff": True},
            ],
            "outbounds": outbounds,
            "route": {"rules": rules,
                      "rule_set": [
                          {"tag": "geosite-ir", "type": "remote", "format": "binary",
                           "url": "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geosite-ir.srs", "download_detour": "proxy"},
                          {"tag": "geoip-ir", "type": "remote", "format": "binary",
                           "url": "https://raw.githubusercontent.com/Chocolate4U/Iran-sing-box-rules/rule-set/geoip-ir.srs", "download_detour": "proxy"}],
                      "final": "proxy", "auto_detect_interface": True},
            "experimental": {"cache_file": {"enabled": True}},
        }

    # ---------------------------------------------------------------- publish
    def write_static_files(self):
        os.makedirs(settings.SUB_DIR, exist_ok=True)
        names = {c["name"] for c in self.store.clients()}
        for f in os.listdir(settings.SUB_DIR):
            if f.split(".", 1)[0] not in names:
                try:
                    os.remove(os.path.join(settings.SUB_DIR, f))
                except OSError:
                    pass
        for c in self.store.clients():
            with open(os.path.join(settings.SUB_DIR, c["name"]), "w") as f:
                f.write(self.classic_b64(c))
            for suffix, builder in ((".json", self.xray_json), (".sb.json", self.singbox_json)):
                p = os.path.join(settings.SUB_DIR, c["name"] + suffix)
                if c["active"]:
                    with open(p, "w") as f:
                        json.dump(builder(c), f, ensure_ascii=False, indent=1)
                elif os.path.exists(p):
                    os.remove(p)

    def github_raw(self, name, kind=""):
        if not settings.REPO_FULL_NAME:
            return None
        suffix = {"": "", "json": ".json", "singbox": ".sb.json"}.get(kind, "")
        return f"https://raw.githubusercontent.com/{settings.REPO_FULL_NAME}/main/sub_links/{name}{suffix}"
