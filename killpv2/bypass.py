"""Bypass (split-tunnel) rules.

  * CLIENT side: Iranian sites / user-defined domains go `direct` from the phone,
    never through the VPN -> bank apps, Snapp, Digikala... work while connected.
    Embedded into the smart JSON subscriptions (Xray JSON / sing-box).
  * SERVER side: private/LAN ranges and BitTorrent are blackholed for safety.
"""

IRAN_CORE_DIRECT = [
    "digikala.com", "snapp.ir", "snapp.taxi", "tapsi.ir", "tap30.ir", "divar.ir", "sheypoor.com",
    "torob.com", "basalam.com", "aparat.com", "filimo.com", "namava.ir", "telewebion.com",
    "shaparak.ir", "sep.ir", "bpm.ir", "bmi.ir", "bankmellat.ir", "sb24.ir", "pasargad.com",
    "bpi.ir", "tejaratbank.ir", "banksepah.ir", "zarinpal.com", "idpay.ir", "payping.ir", "nextpay.ir",
    "irancell.ir", "mci.ir", "rightel.ir", "shatel.ir", "tci.ir", "mytci.ir", "hamrahcard.ir",
    "rubika.ir", "eitaa.com", "bale.ai", "igap.net", "soroush-app.ir", "gap.im", "splus.ir", "shad.ir",
    "cafebazaar.ir", "myket.ir", "sibapp.com", "balad.ir", "neshan.org", "alibaba.ir", "snapptrip.com",
    "flytoday.ir", "mrbilit.com", "safar724.com", "irib.ir", "iribnews.ir", "isna.ir", "irna.ir",
    "tasnimnews.com", "farsnews.ir", "mehrnews.com", "khabaronline.ir", "varzesh3.com", "tgju.org",
    "bonbast.com", "nobitex.ir", "wallex.ir", "ramzinex.com", "bitpin.ir", "tabdeal.org", "exir.io",
    "ok-ex.io", "sahamyab.com", "rahavard365.com", "tsetmc.com", "codal.ir", "arvancloud.ir",
    "arvancloud.com", "r1c.ir", "iranserver.com", "parspack.com", "hamravesh.com", "liara.ir",
    "gov.ir", "my.gov.ir", "sana.ir", "ssaa.ir", "tamin.ir", "sabteahval.ir", "epolice.ir",
    "rahvar120.ir", "police.ir", "post.ir", "tipax.ir", "chapar.ir", "okala.com", "snappfood.ir",
    "zoodfood.com", "delino.com", "reyhoon.com", "tapsifood.com",
]

PRIVATE_CIDRS = ["geoip:private", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
                 "169.254.0.0/16", "fc00::/7", "fe80::/10"]


def _norm(d):
    return (d or "").strip().lower().lstrip("*.").rstrip(".")


class BypassEngine:
    def __init__(self, iran_mode="direct", custom_direct=None, custom_proxy=None, block_private=True):
        self.iran_mode = iran_mode if iran_mode in ("direct", "proxy") else "direct"
        self.custom_direct = [_norm(x) for x in (custom_direct or []) if _norm(x)]
        self.custom_proxy = [_norm(x) for x in (custom_proxy or []) if _norm(x)]
        self.block_private = block_private

    def direct_domains(self):
        out = (IRAN_CORE_DIRECT if self.iran_mode == "direct" else []) + self.custom_direct
        seen, uniq = set(), []
        for d in out:
            if d and d not in seen and d not in self.custom_proxy:
                seen.add(d)
                uniq.append(d)
        return uniq

    def is_direct(self, host):
        host = _norm(host)
        if any(host == p or host.endswith("." + p) for p in self.custom_proxy):
            return False
        if self.iran_mode == "direct" and (host.endswith(".ir") or host == "ir"):
            return True
        return any(host == p or host.endswith("." + p) for p in self.direct_domains())

    def xray_client_rules(self, direct="direct", proxy="proxy"):
        rules = []
        if self.custom_proxy:
            rules.append({"type": "field", "domain": ["domain:" + d for d in self.custom_proxy], "outboundTag": proxy,
                          "ruleTag": "bypass-force-proxy"})
        if self.block_private:
            rules.append({"type": "field", "ip": list(PRIVATE_CIDRS), "outboundTag": direct, "ruleTag": "lan-direct"})
        dom = []
        if self.iran_mode == "direct":
            dom += ["geosite:category-ir", "regexp:\\.ir$"]
        dom += ["domain:" + d for d in self.direct_domains()]
        if dom:
            rules.append({"type": "field", "domain": dom, "outboundTag": direct, "ruleTag": "bypass-direct"})
        if self.iran_mode == "direct":
            rules.append({"type": "field", "ip": ["geoip:ir"], "outboundTag": direct, "ruleTag": "bypass-ir-ip"})
        return rules

    def singbox_client_rules(self, direct="direct", proxy="proxy"):
        rules = []
        if self.custom_proxy:
            rules.append({"domain_suffix": self.custom_proxy, "outbound": proxy})
        rules.append({"ip_is_private": True, "outbound": direct})
        if self.iran_mode == "direct":
            rules.append({"rule_set": ["geosite-ir", "geoip-ir"], "outbound": direct})
            rules.append({"domain_suffix": [".ir"] + self.direct_domains(), "outbound": direct})
        elif self.direct_domains():
            rules.append({"domain_suffix": self.direct_domains(), "outbound": direct})
        return rules

    def xray_server_rules(self, block="block"):
        return [
            {"type": "field", "ip": list(PRIVATE_CIDRS), "outboundTag": block, "ruleTag": "block-private"},
            {"type": "field", "protocol": ["bittorrent"], "outboundTag": block, "ruleTag": "block-torrent"},
        ]

    def summary(self):
        return {"iran_mode": self.iran_mode, "custom_direct": self.custom_direct, "custom_proxy": self.custom_proxy,
                "core_iran_domains": len(IRAN_CORE_DIRECT), "block_private": self.block_private}
