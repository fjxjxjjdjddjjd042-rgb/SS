"""Central settings for kill_pv2. All values are env-overridable."""
import os
import hashlib

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
os.makedirs(DATA_DIR, exist_ok=True)

# --- Panel ---------------------------------------------------------------
# Panel is ONLY reachable under this prefix; "/" prints a bland message.
PANEL_PREFIX = os.environ.get("PANEL_PREFIX", "/KILLPV2").rstrip("/") or "/KILLPV2"
PANEL_USER = os.environ.get("PANEL_USER", "admin").strip() or "admin"
PANEL_PASS = os.environ.get("PANEL_PASS", "").strip()
PANEL_PORT = int(os.environ.get("PANEL_PORT", "8086"))
PANEL_BIND = os.environ.get("PANEL_BIND", "127.0.0.1")

LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCK_SECONDS = int(os.environ.get("LOGIN_LOCK_SECONDS", "900"))
LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "600"))
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", str(12 * 3600)))

# --- Encryption ----------------------------------------------------------
# DB_ENCRYPTION_KEY secret -> AES-256-GCM vault. Falls back to a key derived
# from PANEL_PASS so the system still works with only one secret.
_raw_key = os.environ.get("DB_ENCRYPTION_KEY", "").strip()
if not _raw_key and PANEL_PASS:
    _raw_key = "derived:" + PANEL_PASS
VAULT_KEY_MATERIAL = _raw_key
VAULT_KEY_ID = hashlib.sha256(_raw_key.encode()).hexdigest()[:12] if _raw_key else "none"

# --- Xray ----------------------------------------------------------------
XRAY_BIN = os.environ.get("XRAY_BIN", "/usr/local/bin/xray")
XRAY_DIR = os.environ.get("XRAY_DIR", "/usr/local/etc/xray")
XRAY_CONFIG_PATH = os.path.join(XRAY_DIR, "config.json")
XRAY_ACCESS_LOG = os.path.join(XRAY_DIR, "access.log")
XRAY_ERROR_LOG = os.path.join(XRAY_DIR, "error.log")
XRAY_INBOUND_PORT = int(os.environ.get("XRAY_INBOUND_PORT", "8085"))
XRAY_API_PORT = int(os.environ.get("XRAY_API_PORT", "10085"))
XRAY_WS_PATH = os.environ.get("XRAY_WS_PATH", "/killpv2")
XRAY_USE_SUDO = os.environ.get("XRAY_USE_SUDO", "1") == "1"

# --- Database ------------------------------------------------------------
DB_PATH = os.path.join(DATA_DIR, "killpv2.db")
LEGACY_DB_PATH = os.path.join(ROOT_DIR, "panel_db.json")
VAULT_PATH = os.path.join(DATA_DIR, "vault.enc")
HISTORY_RETENTION_DAYS = int(os.environ.get("HISTORY_RETENTION_DAYS", "90"))

# --- Git / publishing ----------------------------------------------------
REPO_FULL_NAME = os.environ.get("GITHUB_REPOSITORY", "")
SUB_DIR = os.path.join(ROOT_DIR, "sub_links")
GIT_SYNC_INTERVAL = int(os.environ.get("GIT_SYNC_INTERVAL", "60"))
RUN_DURATION = int(os.environ.get("RUN_DURATION", "19800"))
GIT_ENABLED = os.environ.get("GIT_SYNC", "1") == "1"


def read_tunnel_host() -> str:
    p = os.path.join(ROOT_DIR, "active_edge_host.txt")
    if os.path.exists(p):
        with open(p) as f:
            h = f.read().strip()
            if h:
                return h
    return os.environ.get("TUNNEL_HOST", "127.0.0.1")


TUNNEL_HOST = read_tunnel_host()
DEFAULT_CLEAN_IP = "speed.cloudflare.com"
DEFAULT_CLEAN_POOL = ["speed.cloudflare.com", "cp.cloudflare.com", "www.visa.com.sg", "zula.ir", "icook.hk", "ip.sb"]

# --- Telegram bot ---------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OWNER_ID = int(os.environ.get("OWNER_ID", "0") or 0)          # full access, receives system notifications
BOT_ENABLED = bool(BOT_TOKEN and OWNER_ID)
TG_API_BASE = os.environ.get("TG_API_BASE", "https://api.telegram.org").rstrip("/")
SUPPORTED_LANGS = ("fa", "en", "ru", "ar", "tr")
DEFAULT_LANG = "fa"
AI_SESSION_IDLE = int(os.environ.get("AI_SESSION_IDLE", "900"))   # 15 min -> session closed & wiped
AI_RATE_LIMIT_WAIT = int(os.environ.get("AI_RATE_LIMIT_WAIT", "10"))
AI_MAX_ITERATIONS = int(os.environ.get("AI_MAX_ITERATIONS", "12"))

# --- Cloud sync (getpantry.cloud) ------------------------------------------
PANTRY_ID = os.environ.get("PANTRY_ID", "").strip()
CLOUD_SYNC_INTERVAL = int(os.environ.get("CLOUD_SYNC_INTERVAL", "300"))  # 5 min
CLOUD_BASKET_PREFIX = os.environ.get("CLOUD_BASKET_PREFIX", "killpv2")
CLOUD_CHUNK_BYTES = 1_000_000  # pantry basket limit ~1.44MB -> keep margin

# --- Run chaining -------------------------------------------------------------
GH_PAT = os.environ.get("GH_PAT", "").strip()
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE", "data-sync.yml")
