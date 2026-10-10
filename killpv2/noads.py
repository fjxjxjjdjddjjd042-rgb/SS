"""NoAds engine — smart ad / tracker blocking for Xray (server AND client side).

Layers (all become Xray routing rules):
  1. Curated domain lists (YouTube/Google ads, global ad-tech, mobile SDKs,
     trackers, Iranian ad networks) - explicit entries beat everything.
  2. Protected list (media delivery / APIs / games) -> never hit by fuzzy rules.
  3. Xray built-in `geosite:category-ads-all` (thousands of domains).
  4. Heuristic regex on sub-labels (ads., adserver., pagead2., rtb., ...).

Levels: off | balanced (default) | aggressive (+analytics/telemetry/pixels) | strict (+remote blocklists:
        OISD small, HaGeZi Pro, AdGuard DNS filter -> ~150k domains, refreshed every 12h, cached on disk)

Remote lists are fetched in a background thread (never blocks Xray start); until they arrive the curated
lists + geosite + heuristics apply. Hosts in PROTECTED are never blocked by remote/heuristic layers.
"""
import os
import re
import time
import json
import threading
import urllib.request

YOUTUBE_ADS = [
    "doubleclick.net", "googlesyndication.com", "googleadservices.com", "googletagservices.com",
    "2mdn.net", "adservice.google.com", "mobileads.google.com", "ads.youtube.com", "ad.youtube.com",
    "youtube.cleverads.vn", "pagead.l.doubleclick.net", "pagead2.googlesyndication.com",
    "googleads.g.doubleclick.net", "static.doubleclick.net", "stats.g.doubleclick.net",
    "cm.g.doubleclick.net", "pubads.g.doubleclick.net", "securepubads.g.doubleclick.net",
    "video-ad-stats.googlesyndication.com", "tpc.googlesyndication.com", "afs.googlesyndication.com",
    "s.youtube.com", "ad.doubleclick.net", "bid.g.doubleclick.net", "fls.doubleclick.net", "m.doubleclick.net",
    "googleadapis.l.google.com", "pagead-googlehosted.l.google.com", "partnerad.l.doubleclick.net", "www.googleadservices.com",
    "ade.googlesyndication.com", "ads.youtube.l.google.com", "ssl.google-analytics.com", "www.google-analytics.com",
    "ad.mail.google.com", "adwords.google.com", "admob.google.com", "ads.g.doubleclick.net",
    "admob.com", "ads.google.com", "adsense.google.com", "adx.g.doubleclick.net",
    "ad.mo.doubleclick.net", "ad-g.doubleclick.net", "adclick.g.doubleclick.net",
    "surveys.g.doubleclick.net", "googlesyndication-cn.com", "adservice.google.com.hk",
    "adservice.google.de", "adservice.google.co.uk", "adservice.google.fr", "adservice.google.ca",
    "adservice.google.com.au", "adservice.google.co.in", "doubleclickbygoogle.com",
    "google-analytics.com", "analytics.google.com", "app-measurement.com",
    "firebase-settings.crashlytics.com", "s0.2mdn.net", "innovid.com", "serving-sys.com",
    "imasdk.googleapis.com",
]

GLOBAL_ADS = [
    "adnxs.com", "adsrvr.org", "rubiconproject.com", "pubmatic.com", "openx.net", "criteo.com",
    "criteo.net", "taboola.com", "outbrain.com", "mgid.com", "revcontent.com", "adform.net",
    "smartadserver.com", "casalemedia.com", "indexww.com", "33across.com", "sharethrough.com",
    "triplelift.com", "amazon-adsystem.com", "moatads.com", "scorecardresearch.com", "quantserve.com",
    "bluekai.com", "demdex.net", "everesttech.net", "adsafeprotected.com", "doubleverify.com",
    "sizmek.com", "yieldmo.com", "media.net", "bidswitch.net", "lijit.com", "sovrn.com", "teads.tv",
    "undertone.com", "zedo.com", "advertising.com", "adtech.de", "adtechus.com", "exoclick.com",
    "exosrv.com", "juicyads.com", "trafficjunky.net", "trafficjunky.com", "popads.net", "popcash.net",
    "propellerads.com", "propellerclick.com", "onclickads.net", "onclkds.com", "adcash.com",
    "hilltopads.net", "clickadu.com", "adsterra.com", "a-ads.com", "bidvertiser.com", "ad-maven.com",
    "yllix.com", "adskeeper.co.uk", "adskeeper.com", "rtbhouse.com", "creativecdn.com", "yieldlab.net",
    "improvedigital.com", "smaato.net", "smaato.com", "inmobi.com", "mopub.com", "adcolony.com",
    "applovin.com", "applvn.com", "unityads.unity3d.com", "vungle.com", "chartboost.com", "ironsrc.com",
    "supersonicads.com", "ironsrc.mobi", "startapp.com", "startappservice.com", "appsflyer.com",
    "adjust.com", "adjust.io", "kochava.com", "tapjoy.com", "fyber.com", "mintegral.com", "pangle.io",
    "pangleglobal.com", "bytedance-ads.com", "liftoff.io", "moloco.com", "adikteev.com", "appnext.com",
    "appnexus.com", "mediavine.com", "ezoic.net", "ezodn.com", "carbonads.com", "carbonads.net",
    "buysellads.com", "buysellads.net", "adroll.com", "perfectaudience.com", "ligatus.com", "plista.com",
    "nativeads.com", "contentad.net", "adblade.com", "zemanta.com", "spotxchange.com", "spotx.tv",
    "springserve.com", "freewheel.tv", "fwmrm.net", "tremorhub.com", "telaria.com", "beachfront.com",
    "adotmob.com", "adtelligent.com", "vidoomy.com", "vlitag.com", "a-mo.net", "adnium.com",
    "ero-advertising.com", "plugrush.com", "tsyndicate.com", "realsrv.com", "mc.yandex.ru",
    "an.yandex.ru", "yandexadexchange.net", "adfox.ru", "adriver.ru", "betweendigital.com",
    "ad-score.com", "adsco.re", "pixfuture.com", "sortable.com", "yieldbird.com", "connatix.com",
    "primis.tech", "sekindo.com", "vidazoo.com", "aniview.com", "adpushup.com", "adthrive.com",
    "raptive.com", "cafemedia.com", "bttrack.com", "bidtellect.com", "gumgum.com", "kargo.com",
    "nativo.com", "onetag-sys.com", "richaudience.com", "seedtag.com", "sonobi.com", "unrulymedia.com",
    "vdo.ai", "adgrx.com", "adhigh.net", "adkernel.com", "admixer.net", "adspirit.de", "adsymptotic.com",
    "adtarget.me", "adtrue.com", "atdmt.com", "ads.linkedin.com", "ads.pinterest.com", "ads.tiktok.com",
    "ads-api.tiktok.com", "analytics.tiktok.com", "ads.twitter.com", "ads-twitter.com", "ads.yahoo.com",
    "adtechjp.com", "adsmoloco.com", "cloudflareinsights.com", "ads.reddit.com", "events.reddit.com",
    "pixel.reddit.com", "ads.instagram.com", "an.facebook.com", "ads.facebook.com",
    # --- more ad-tech / popunder / push networks
    "ad-delivery.net", "adspyglass.com", "adtng.com", "adxpansion.com", "clickaine.com", "clicksgear.com", "cpmstar.com",
    "exdynsrv.com", "galaksion.com", "hilltopads.com", "monetag.com", "notix.io", "pushame.com", "pushnative.com",
    "richpush.co", "evadav.com", "adsterratech.com", "adbison.com", "trafficstars.com", "adxcore.com", "adoperator.com",
    "popmyads.com", "popunder.net", "poptm.com", "zeropark.com", "rtmark.net", "magsrv.com", "aralego.com",
    "adsrvmedia.com", "adsrvmedia.net", "mobiads.net", "adbuddiz.com", "adincube.com", "adfalcon.com", "adiquity.com",
    "admarvel.com", "admaxim.com", "admedo.com", "adperium.com", "adsmogo.com", "adtilt.com", "airpush.com", "amobee.com",
    "avazutracking.net", "greystripe.com", "inner-active.mobi", "jumptap.com", "leadbolt.com", "leadboltads.net",
    "leadboltapps.net", "madvertise.com", "millennialmedia.com", "mobclix.com", "mobfox.com", "mobpartner.com", "mojiva.com",
    "nexage.com", "pubnative.net", "smartyads.com", "tapit.com", "vdopia.com", "velti.com", "widespace.com", "xad.com",
    "youmi.net", "zumobi.com", "adhese.com", "bidr.io", "contextweb.com", "pulsepoint.com", "districtm.io", "emxdgt.com",
    "gothamads.com", "inmobi.net", "loopme.com", "loopme.me", "mathtag.com", "mediamath.com", "mfadsrvr.com", "ml314.com",
    "nexac.com", "openx.com", "owneriq.net", "pubmine.com", "quantcount.com", "rfihub.com", "rhythmone.com", "rlcdn.com",
    "servenobid.com", "simpli.fi", "smartclip.net", "stickyadstv.com", "tapad.com", "turn.com", "w55c.net",
    "yieldmanager.com", "yieldoptimizer.com", "zqtk.net", "1rx.io", "3lift.com", "flashtalking.com", "eyeota.net",
    "exelator.com", "krxd.net", "liadm.com", "agkn.com", "business-api.tiktok.com", "ads-sg.tiktok.com",
    "log.byteoversea.com", "mon.byteoversea.com", "ads.snapchat.com", "adsapi.snapchat.com", "analytics.yahoo.com",
    "ads.microsoft.com", "bat.bing.com", "ads.bing.com", "flex.msn.com", "rad.msn.com", "a.ads1.msn.com",
    "ads.mopub.com", "ads.inmobi.com", "ads.flurry.com", "adserver.unityads.unity3d.com", "ads.ironsrc.com", "ads.vungle.com",
    "ads.chartboost.com", "ads.adcolony.com", "ads.tapjoy.com", "ads.fyber.com", "ads.mintegral.com", "ads.pangle.io",
    "ads.liftoff.io", "ads.moloco.com", "ads.appnext.com", "ads.startapp.com",
]

TRACKERS = [
    "hotjar.com", "hotjar.io", "mixpanel.com", "segment.io", "segment.com", "amplitude.com",
    "fullstory.com", "mouseflow.com", "crazyegg.com", "luckyorange.com", "clarity.ms", "heapanalytics.com",
    "kissmetrics.com", "chartbeat.com", "chartbeat.net", "parsely.com", "newrelic.com", "nr-data.net",
    "bugsnag.com", "branch.io", "singular.net", "tenjin.io", "onesignal.com", "pushwoosh.com",
    "pushengage.com", "optimizely.com", "connect.facebook.net", "pixel.facebook.com",
    "snap.licdn.com", "px.ads.linkedin.com", "analytics.twitter.com", "sc-static.net", "tr.snapchat.com",
    "cdn.mxpnl.com", "api.mixpanel.com", "stats.wp.com", "pixel.wp.com", "matomo.cloud", "piwik.pro",
    "plausible.io", "statcounter.com", "histats.com", "liveinternet.ru", "top.mail.ru", "mc.webvisor.org",
    "track.hubspot.com", "mktoresp.com", "pardot.com", "demandbase.com", "6sc.co", "bizible.com",
    "samsungads.com", "samsungacr.com", "ad.xiaomi.com", "api.ad.xiaomi.com", "data.mistat.xiaomi.com",
    "tracking.miui.com", "adsfs.oppomobile.com", "ads.oppomobile.com", "adx.vivoglobal.com",
    "ads.vivo.com.cn", "ads.huawei.com", "metrics.data.hicloud.com", "logservice.hicloud.com",
    "iadsdk.apple.com", "ads.apple.com", "metrics.apple.com", "securemetrics.apple.com",
    "vortex.data.microsoft.com", "watson.telemetry.microsoft.com", "telemetry.microsoft.com",
    "settings-win.data.microsoft.com", "browser.events.data.msn.com", "events.data.microsoft.com",
    "mobile.events.data.microsoft.com",
]

IRAN_ADS = [
    "yektanet.com", "mediaad.org", "tapsell.ir", "tapsell.net", "anetwork.ir", "sabavision.com",
    "daartads.com", "clickyab.com", "e-click.ir", "adad.ir", "magnetadservices.com", "adivery.com",
    "pushe.co", "najva.com", "metrix.ir", "deema.agency", "kaprila.com", "adro.ir", "tapligh.com",
    "affilio.ir", "adsmanager.ir", "adsvis.ir", "irdiba.com", "adsdigital.ir", "nasimads.ir",
    "tabanad.ir", "zarinads.ir", "adwiz.ir", "iranads.ir", "adsmile.ir", "mediadad.ir", "adroll.ir",
    "ad-tech.ir", "chabok.io", "chabokpush.com", "webengage.com", "sanjagh.net", "adnegar.com",
    "yektanet.ir", "adivery.ir", "a.yektanet.com", "s.yektanet.com", "r.yektanet.com", "static.yektanet.com",
    "api.yektanet.com", "cdn.yektanet.com", "s1.mediaad.org", "s2.mediaad.org", "static.mediaad.org",
    "api.tapsell.ir", "sdk.tapsell.ir", "static.tapsell.ir", "plus.tapsell.ir", "ads.anetwork.ir", "static.anetwork.ir",
    "cdn.anetwork.ir", "ad.sabavision.com", "static.sabavision.com", "clickyab.ir", "static.clickyab.com", "ck.clickyab.com",
    "s.adad.ir", "static.adad.ir", "api.adad.ir", "s.adro.ir", "cdn.adro.ir", "api.pushe.co", "static.pushe.co", "sdk.pushe.co",
    "app.najva.com", "static.najva.com", "api.najva.com", "analytics.metrix.ir", "api.metrix.ir", "sdk.metrix.ir",
    "tracker.metrix.ir", "ads.deema.agency", "ads.kaprila.com", "api.chabok.io", "sandbox.chabok.io", "ad.tapligh.com",
    "static.tapligh.com", "api.tapligh.com", "ads.affilio.ir", "ads.irdiba.com", "ads.sanjagh.net", "ads.varzesh3.com",
    "ad.varzesh3.com", "ads.digikala.com", "ads.aparat.com", "ad.aparat.com", "ads.filimo.com", "ads.namava.ir",
    "ads.telewebion.com", "ads.divar.ir", "ad.divar.ir", "ads.sheypoor.com", "ads.torob.com", "ads.cafebazaar.ir",
    "ads.myket.ir", "ad.myket.ir", "ads.snapp.ir", "ads.tapsi.ir", "ads.rubika.ir", "ads.eitaa.com",
]

PROTECTED = [
    "googlevideo.com", "youtube.com", "youtu.be", "ytimg.com", "ggpht.com", "youtubei.googleapis.com",
    "googleapis.com", "gstatic.com", "googleusercontent.com", "accounts.google.com", "play.google.com",
    "android.com", "gvt1.com", "gvt2.com", "cloudflare.com", "cloudflare-dns.com", "trycloudflare.com",
    "workers.dev", "telegram.org", "t.me", "cdn-telegram.org", "telesco.pe", "web.telegram.org",
    "whatsapp.net", "whatsapp.com", "fbcdn.net", "cdninstagram.com", "instagram.com", "twimg.com",
    "x.com", "twitter.com", "discord.com", "discordapp.com", "discord.gg", "discord.media",
    "steamstatic.com", "steampowered.com", "steamcommunity.com", "epicgames.com", "riotgames.com",
    "pvp.net", "riotcdn.net", "playstation.net", "xboxlive.com", "ea.com", "origin.com", "blizzard.com",
    "battle.net", "supercell.com", "supercellcdn.com", "clashofclans.com", "pubgmobile.com", "igamecj.com",
    "tencentgames.com", "garena.com", "freefiremobile.com", "spotify.com", "scdn.co", "spotifycdn.com",
    "netflix.com", "nflxvideo.net", "nflximg.net", "apple.com", "icloud.com", "mzstatic.com",
    "microsoft.com", "windowsupdate.com", "live.com", "office.com", "github.com", "githubusercontent.com",
    "cloudfront.net", "akamaihd.net", "akamaized.net", "fastly.net", "twitch.tv", "ttvnw.net", "jtvnw.net",
    "reddit.com", "redd.it", "redditmedia.com", "wikipedia.org", "duckduckgo.com", "bing.com",
    "openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com", "anthropic.com", "claude.ai",
]

HEURISTIC_LABELS_BALANCED = [
    r"ads?", r"ads?[0-9]{1,3}", r"adserver[0-9]*", r"adservice[s]?", r"adserv[0-9]*", r"adsrv[0-9]*",
    r"adsys[0-9]*", r"adx", r"advert(ising|isement|s)?", r"adimg[0-9]*", r"adtech", r"adform",
    r"adunit[s]?", r"adtrack(ing|er)?", r"pagead[0-9]*", r"doubleclick", r"banners?", r"bannerads?",
    r"popunder", r"popads", r"pop-?ups?", r"sponsor(ed|s)?", r"affiliat(e|es|ion)", r"preroll",
    r"video-?ads?", r"adsdk", r"ad-?sdk", r"ad-?delivery", r"ad-?manager", r"ad-?stats?", r"adlogs?",
    r"adclicks?", r"adrotat(e|or)", r"ad-?exchange", r"ad-?platform", r"adcdn", r"ad-?cdn", r"adcontent",
    r"adsales", r"adspace", r"admob", r"admeld", r"openx", r"rtb", r"ssp", r"dsp", r"bidder", r"bidding",
    r"prebid",
]
HEURISTIC_LABELS_AGGRESSIVE = HEURISTIC_LABELS_BALANCED + [
    r"track(ing|er|s)?", r"telemetry", r"metrics?", r"analytics?", r"pixels?", r"beacons?", r"stats?[0-9]*",
    r"counter[0-9]*", r"collector[0-9]*", r"insights?", r"measurement", r"mobile-?measurement",
    r"event-?log(ger)?", r"crashlytics", r"appsflyer", r"adjust", r"mixpanel", r"hotjar", r"fullstory",
]
LEVELS = ("off", "balanced", "aggressive", "strict")

# --- remote lists (strict level) -----------------------------------------------------------------
REMOTE_LISTS = {
    "oisd_small": "https://small.oisd.nl/domainswild2",
    "hagezi_pro": "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/pro.txt",
    "adguard_dns": "https://raw.githubusercontent.com/AdguardTeam/AdGuardSDNSFilter/master/Filters/filter.txt",
}
REMOTE_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
REMOTE_REFRESH = 12 * 3600
REMOTE_MAX = 200_000
_remote_lock = threading.Lock()
_remote = {"domains": [], "loaded_at": 0, "sources": {}, "loading": False}
_DOMAIN_RE = re.compile(r"^([a-z0-9][a-z0-9\-\.]{1,250}\.[a-z]{2,24})$")
_rs_cache = {"n": -1, "set": set()}


def _parse_remote(text):
    out = set()
    for raw in text.splitlines():
        line = raw.strip().lower()
        if not line or line.startswith(("#", "!", "@@", "/", "[")):
            continue
        if line.startswith("||"):
            line = line[2:].split("^")[0].split("$")[0]
        elif line.startswith(("0.0.0.0 ", "127.0.0.1 ")):
            line = line.split()[1]
        line = line.lstrip("*.")
        if "/" in line or "*" in line or ":" in line:
            continue
        m = _DOMAIN_RE.match(line)
        if m:
            out.add(m.group(1))
    return out


def _load_cache():
    try:
        with open(os.path.join(REMOTE_CACHE_DIR, "remote_blocklist.json")) as f:
            d = json.load(f)
        if time.time() - d.get("loaded_at", 0) < REMOTE_REFRESH * 4:
            _remote.update({"domains": d["domains"], "loaded_at": d["loaded_at"], "sources": d.get("sources", {})})
            return True
    except Exception:
        pass
    return False


def refresh_remote_lists(on_done=None, force=False):
    """Download & merge remote blocklists in a background thread; on_done(count, sources) when ready."""
    with _remote_lock:
        if _remote["loading"]:
            return False
        if not force and _remote["domains"] and time.time() - _remote["loaded_at"] < REMOTE_REFRESH:
            return False
        _remote["loading"] = True

    def _run():
        merged, sources = set(), {}
        try:
            for name, url in REMOTE_LISTS.items():
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "kill_pv2 noads/2"})
                    with urllib.request.urlopen(req, timeout=40) as r:
                        doms = _parse_remote(r.read().decode("utf-8", "ignore"))
                    sources[name] = len(doms)
                    merged |= doms
                except Exception as e:
                    sources[name] = f"error: {str(e)[:60]}"
            doms = sorted(d for d in merged if not _matches_suffix(d, PROTECTED))[:REMOTE_MAX]
            if doms:
                with _remote_lock:
                    _remote.update({"domains": doms, "loaded_at": int(time.time()), "sources": sources})
                try:
                    os.makedirs(REMOTE_CACHE_DIR, exist_ok=True)
                    with open(os.path.join(REMOTE_CACHE_DIR, "remote_blocklist.json"), "w") as f:
                        json.dump({"domains": doms, "loaded_at": _remote["loaded_at"], "sources": sources}, f)
                except Exception:
                    pass
                if on_done:
                    try:
                        on_done(len(doms), sources)
                    except Exception:
                        pass
        finally:
            with _remote_lock:
                _remote["loading"] = False
    threading.Thread(target=_run, daemon=True, name="noads-remote").start()
    return True


def remote_domains():
    if not _remote["domains"] and not _remote["loaded_at"]:
        _load_cache()
    return _remote["domains"]


def _remote_set():
    rd = remote_domains()
    if _rs_cache["n"] != len(rd):
        _rs_cache["set"], _rs_cache["n"] = set(rd), len(rd)
    return _rs_cache["set"]


def remote_status():
    return {"count": len(_remote["domains"]), "loaded_at": _remote["loaded_at"], "sources": _remote["sources"], "loading": _remote["loading"]}



def _compile(labels):
    return re.compile(r"^(?:" + "|".join(labels) + r")$", re.IGNORECASE)


_RE_BAL = _compile(HEURISTIC_LABELS_BALANCED)
_RE_AGG = _compile(HEURISTIC_LABELS_AGGRESSIVE)


def _norm(d):
    return (d or "").strip().lower().lstrip("*.").rstrip(".")


def _matches_suffix(host, suffixes):
    for s in suffixes:
        s = _norm(s)
        if s and "/" not in s and (host == s or host.endswith("." + s)):
            return True
    return False


class NoAdsEngine:
    def __init__(self, level="balanced", custom_block=None, whitelist=None, block_iran_ads=True):
        self.level = level if level in LEVELS else "balanced"
        self.custom_block = [_norm(x) for x in (custom_block or []) if _norm(x)]
        self.whitelist = [_norm(x) for x in (whitelist or []) if _norm(x)]
        self.block_iran_ads = bool(block_iran_ads)

    def block_domains(self):
        out = []
        if self.level != "off":
            out += YOUTUBE_ADS + GLOBAL_ADS
            if self.block_iran_ads:
                out += IRAN_ADS
            if self.level in ("aggressive", "strict"):
                out += TRACKERS
        out += self.custom_block
        seen, uniq = set(), []
        for d in out:
            d = _norm(d)
            if d and "/" not in d and d not in seen and d not in self.whitelist:
                seen.add(d)
                uniq.append(d)
        return uniq

    def remote_block_domains(self):
        if self.level != "strict":
            return []
        wl = self.whitelist
        return [d for d in remote_domains() if not wl or not _matches_suffix(d, wl)]

    def heuristic_regex(self):
        if self.level == "off":
            return None
        labels = HEURISTIC_LABELS_AGGRESSIVE if self.level in ("aggressive", "strict") else HEURISTIC_LABELS_BALANCED
        # label must be a SUB-label: at least two labels follow it (never the apex "ads.com")
        return r"^(?:[^.]+\.)*(?:" + "|".join(labels) + r")\.(?:[^.]+\.)+[^.]+$"

    def is_blocked(self, host):
        """Pure-python decision mirroring the Xray rule order (log classification & tests)."""
        host = _norm(host)
        if not host:
            return False
        if _matches_suffix(host, self.whitelist):
            return False
        if _matches_suffix(host, self.block_domains()):
            return True
        if self.level == "off":
            return False
        if _matches_suffix(host, PROTECTED):
            return False
        if self.level == "strict":
            rs = _remote_set()
            parts = host.split(".")
            for i in range(len(parts) - 1):
                if ".".join(parts[i:]) in rs:
                    return True
        rx = _RE_AGG if self.level in ("aggressive", "strict") else _RE_BAL
        return any(rx.match(lab) for lab in host.split(".")[:-2])

    def xray_rules(self, outbound_block="block", outbound_direct="direct"):
        rules = []
        if self.level == "off" and not self.custom_block:
            return rules
        if self.whitelist:
            rules.append({"type": "field", "domain": ["domain:" + d for d in self.whitelist],
                          "outboundTag": outbound_direct, "ruleTag": "noads-whitelist"})
        blk = ["domain:" + d for d in self.block_domains()]
        if blk:
            rules.append({"type": "field", "domain": blk, "outboundTag": outbound_block, "ruleTag": "noads-block"})
        if self.level == "off":
            return rules
        rules.append({"type": "field", "domain": ["domain:" + d for d in PROTECTED],
                      "outboundTag": outbound_direct, "ruleTag": "noads-protect"})
        remote = self.remote_block_domains()
        for i in range(0, len(remote), 20000):
            rules.append({"type": "field", "domain": ["domain:" + d for d in remote[i:i + 20000]],
                          "outboundTag": outbound_block, "ruleTag": f"noads-remote-{i // 20000}"})
        fuzzy = ["geosite:category-ads-all"]
        rx = self.heuristic_regex()
        if rx:
            fuzzy.append("regexp:" + rx)
        rules.append({"type": "field", "domain": fuzzy, "outboundTag": outbound_block, "ruleTag": "noads-heuristic"})
        return rules

    def singbox_rules(self, outbound_block="block", outbound_direct="direct"):
        if self.level == "off" and not self.custom_block:
            return []
        rules = []
        if self.whitelist:
            rules.append({"domain_suffix": self.whitelist, "outbound": outbound_direct})
        rules.append({"domain_suffix": self.block_domains(), "outbound": outbound_block})
        if self.level == "off":
            return rules
        rules.append({"domain_suffix": list(PROTECTED), "outbound": outbound_direct})
        remote = self.remote_block_domains()
        if remote:
            rules.append({"domain_suffix": remote[:30000], "outbound": outbound_block})  # cap: keep phone import light
        rx = self.heuristic_regex()
        if rx:
            rules.append({"domain_regex": [rx], "outbound": outbound_block})
        return rules

    def summary(self):
        return {
            "level": self.level, "curated_domains": len(self.block_domains()),
            "youtube_domains": len(YOUTUBE_ADS), "global_domains": len(GLOBAL_ADS),
            "tracker_domains": len(TRACKERS), "iran_domains": len(IRAN_ADS),
            "heuristic_patterns": len(HEURISTIC_LABELS_AGGRESSIVE if self.level in ("aggressive", "strict") else HEURISTIC_LABELS_BALANCED),
            "custom_block": self.custom_block, "whitelist": self.whitelist,
            "block_iran_ads": self.block_iran_ads, "protected": len(PROTECTED),
            "remote_domains": len(self.remote_block_domains()), "remote": remote_status(), "levels": list(LEVELS),
        }
