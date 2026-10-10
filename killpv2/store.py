"""SQLite store + encrypted vault persistence (data/vault.enc committed to git)."""
import os
import json
import time
import sqlite3
import threading
import uuid as uuidlib

from . import settings
from . import crypto

_lock = threading.RLock()

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS clients (
    name TEXT PRIMARY KEY, uuid TEXT NOT NULL UNIQUE,
    total_limit_bytes INTEGER NOT NULL DEFAULT 0, used_bytes INTEGER NOT NULL DEFAULT 0,
    up_bytes INTEGER NOT NULL DEFAULT 0, down_bytes INTEGER NOT NULL DEFAULT 0,
    clean_ip TEXT NOT NULL DEFAULT 'speed.cloudflare.com', status TEXT NOT NULL DEFAULT 'OFFLINE',
    last_active_time REAL NOT NULL DEFAULT 0, down_speed INTEGER NOT NULL DEFAULT 0, up_speed INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL, expire_seconds INTEGER NOT NULL DEFAULT 2592000, active INTEGER NOT NULL DEFAULT 1,
    note TEXT NOT NULL DEFAULT '', noads INTEGER NOT NULL DEFAULT 1, bypass_iran INTEGER NOT NULL DEFAULT 1,
    ip_limit INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL DEFAULT 0,
    owner_tg INTEGER NOT NULL DEFAULT 0, plan_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS traffic_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client TEXT NOT NULL, ts INTEGER NOT NULL, up INTEGER NOT NULL, down INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_ts_client ON traffic_samples(client, ts);
CREATE TABLE IF NOT EXISTS client_ips (
    client TEXT NOT NULL, ip TEXT NOT NULL, first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (client, ip));
CREATE TABLE IF NOT EXISTS visits (
    client TEXT NOT NULL, ip TEXT NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 443,
    first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL, hits INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (client, ip, host, port));
CREATE INDEX IF NOT EXISTS idx_visits_client_ip ON visits(client, ip, last_seen);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, level TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (ip TEXT NOT NULL, ts INTEGER NOT NULL, ok INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_login_ip ON login_attempts(ip, ts);

-- ===== Telegram bot =====
CREATE TABLE IF NOT EXISTS tg_users (
    tg_id INTEGER PRIMARY KEY, username TEXT NOT NULL DEFAULT '', first_name TEXT NOT NULL DEFAULT '',
    lang TEXT NOT NULL DEFAULT 'fa', wallet INTEGER NOT NULL DEFAULT 0, coins INTEGER NOT NULL DEFAULT 0,
    referred_by INTEGER, referrals INTEGER NOT NULL DEFAULT 0, banned INTEGER NOT NULL DEFAULT 0,
    is_admin INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT '', state_data TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, gb INTEGER NOT NULL DEFAULT 0,
    days INTEGER NOT NULL DEFAULT 30, price INTEGER NOT NULL DEFAULT 0, coin_price INTEGER NOT NULL DEFAULT 0,
    ip_limit INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, kind TEXT NOT NULL, amount INTEGER NOT NULL DEFAULT 0,
    plan_id INTEGER, file_id TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
    admin_id INTEGER, admin_msg TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL, decided_at INTEGER NOT NULL DEFAULT 0,
    result TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_receipts_user ON receipts(tg_id, created_at);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER NOT NULL, plan_id INTEGER, client TEXT NOT NULL,
    method TEXT NOT NULL, amount INTEGER NOT NULL DEFAULT 0, receipt_id TEXT, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(tg_id);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER NOT NULL, kind TEXT NOT NULL, delta INTEGER NOT NULL,
    balance INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '', ref TEXT NOT NULL DEFAULT '', ts INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger(tg_id, ts);
CREATE TABLE IF NOT EXISTS client_alerts (client TEXT NOT NULL, kind TEXT NOT NULL, ts INTEGER NOT NULL, PRIMARY KEY(client, kind));
CREATE TABLE IF NOT EXISTS ai_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT NOT NULL, tg_id INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_ai_memory ON ai_memory(target, tg_id);
CREATE TABLE IF NOT EXISTS ai_sessions (
    id TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, worker INTEGER NOT NULL DEFAULT 0, messages TEXT NOT NULL DEFAULT '[]',
    started_at INTEGER NOT NULL, last_at INTEGER NOT NULL, closed INTEGER NOT NULL DEFAULT 0, turns INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_ai_sessions_user ON ai_sessions(tg_id, last_at);
CREATE TABLE IF NOT EXISTS ai_workers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL DEFAULT '', base_url TEXT NOT NULL, api_key TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, requests INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0, rate_limits INTEGER NOT NULL DEFAULT 0, last_used INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ai_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, tg_id INTEGER NOT NULL, ts INTEGER NOT NULL,
    kind TEXT NOT NULL, content TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_ai_log_session ON ai_log(session_id, id);
"""

# tables that survive restarts via vault + cloud
EXPORT_TABLES_EXTRA = ["tg_users", "plans", "receipts", "orders", "ledger", "client_alerts", "ai_memory", "ai_sessions",
                       "ai_workers", "ai_log"]

EXPORT_TABLES = ["clients", "settings", "traffic_samples", "client_ips", "visits", "events"] + EXPORT_TABLES_EXTRA
CLIENT_FIELDS = ["name", "uuid", "total_limit_bytes", "used_bytes", "up_bytes", "down_bytes", "clean_ip", "status",
                 "last_active_time", "down_speed", "up_speed", "created_at", "expire_seconds", "active", "note",
                 "noads", "bypass_iran", "ip_limit", "updated_at", "owner_tg", "plan_id"]


class Store:
    def __init__(self, path=settings.DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        with _lock:
            self.conn.executescript(SCHEMA)
            self._migrate()
        self.dirty = False

    def _migrate(self):
        """Add columns introduced after v2 to existing databases (idempotent)."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(clients)").fetchall()}
        for col, ddl in (("owner_tg", "INTEGER NOT NULL DEFAULT 0"), ("plan_id", "INTEGER NOT NULL DEFAULT 0")):
            if col not in cols:
                self.conn.execute(f"ALTER TABLE clients ADD COLUMN {col} {ddl}")

    def _exec(self, sql, params=()):
        with _lock:
            return self.conn.execute(sql, params)

    def _rows(self, sql, params=()):
        with _lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def mark_dirty(self):
        self.dirty = True

    # ---- events
    def log(self, kind, message, level="info"):
        self._exec("INSERT INTO events(ts,level,kind,message) VALUES(?,?,?,?)", (int(time.time()), level, kind, str(message)[:2000]))
        print(f"[{kind}] {message}", flush=True)

    def events(self, limit=200, kind=None):
        if kind:
            return self._rows("SELECT * FROM events WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit))
        return self._rows("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

    # ---- settings
    def get_setting(self, key, default=None):
        r = self._rows("SELECT value FROM settings WHERE key=?", (key,))
        if not r:
            return default
        try:
            return json.loads(r[0]["value"])
        except Exception:
            return r[0]["value"]

    def set_setting(self, key, value):
        self._exec("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, json.dumps(value, ensure_ascii=False)))
        self.mark_dirty()

    # ---- clients
    def clients(self):
        return self._rows("SELECT * FROM clients ORDER BY created_at ASC")

    def client(self, name):
        r = self._rows("SELECT * FROM clients WHERE name=?", (name,))
        return r[0] if r else None

    def create_client(self, name, **kw):
        now = int(time.time())
        row = {
            "name": name, "uuid": kw.get("uuid") or str(uuidlib.uuid4()),
            "total_limit_bytes": int(kw.get("total_limit_bytes", 0)), "used_bytes": int(kw.get("used_bytes", 0)),
            "up_bytes": int(kw.get("up_bytes", 0)), "down_bytes": int(kw.get("down_bytes", 0)),
            "clean_ip": kw.get("clean_ip") or settings.DEFAULT_CLEAN_IP, "status": kw.get("status", "OFFLINE"),
            "last_active_time": float(kw.get("last_active_time", 0)), "down_speed": 0, "up_speed": 0,
            "created_at": int(kw.get("created_at", now)), "expire_seconds": int(kw.get("expire_seconds", 2592000)),
            "active": 1 if kw.get("active", True) else 0, "note": kw.get("note", ""),
            "noads": 1 if kw.get("noads", True) else 0, "bypass_iran": 1 if kw.get("bypass_iran", True) else 0,
            "ip_limit": int(kw.get("ip_limit", 0)), "updated_at": now,
            "owner_tg": int(kw.get("owner_tg", 0) or 0), "plan_id": int(kw.get("plan_id", 0) or 0),
        }
        self._exec(f"INSERT INTO clients({','.join(row)}) VALUES({','.join('?' * len(row))})", tuple(row.values()))
        self.mark_dirty()
        return row

    def update_client(self, name, **fields):
        allowed = {k: v for k, v in fields.items() if k in CLIENT_FIELDS and k != "name"}
        if not allowed:
            return False
        allowed["updated_at"] = int(time.time())
        cur = self._exec(f"UPDATE clients SET {','.join(f'{k}=?' for k in allowed)} WHERE name=?", (*allowed.values(), name))
        self.mark_dirty()
        return cur.rowcount > 0

    def rename_client(self, old, new):
        with _lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.execute("UPDATE clients SET name=?, updated_at=? WHERE name=?", (new, int(time.time()), old))
                for t in ("traffic_samples", "client_ips", "visits"):
                    self.conn.execute(f"UPDATE {t} SET client=? WHERE client=?", (new, old))
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        self.mark_dirty()

    def delete_client(self, name, purge_history=False):
        with _lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.execute("DELETE FROM clients WHERE name=?", (name,))
                if purge_history:
                    for t in ("traffic_samples", "client_ips", "visits"):
                        self.conn.execute(f"DELETE FROM {t} WHERE client=?", (name,))
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        self.mark_dirty()

    # ---- traffic (exact byte accounting)
    def add_traffic(self, name, up, down, ts=None):
        if up <= 0 and down <= 0:
            return
        ts = ts or int(time.time())
        with _lock:
            self.conn.execute(
                "UPDATE clients SET used_bytes=used_bytes+?, up_bytes=up_bytes+?, down_bytes=down_bytes+?, "
                "last_active_time=?, status='ONLINE', updated_at=? WHERE name=? AND active=1",
                (up + down, up, down, ts, ts, name))
            minute = ts - ts % 60
            cur = self.conn.execute("UPDATE traffic_samples SET up=up+?, down=down+? WHERE client=? AND ts=?", (up, down, name, minute))
            if cur.rowcount == 0:
                self.conn.execute("INSERT INTO traffic_samples(client,ts,up,down) VALUES(?,?,?,?)", (name, minute, up, down))
        self.mark_dirty()

    def traffic_series(self, name, since):
        return self._rows("SELECT ts, up, down FROM traffic_samples WHERE client=? AND ts>=? ORDER BY ts", (name, since))

    def traffic_totals_since(self, since):
        return self._rows("SELECT client, SUM(up) up, SUM(down) down FROM traffic_samples WHERE ts>=? GROUP BY client", (since,))

    # ---- ips / visits
    def touch_ip(self, name, ip, ts=None):
        ts = ts or int(time.time())
        self._exec("INSERT INTO client_ips(client,ip,first_seen,last_seen,hits) VALUES(?,?,?,?,1) "
                   "ON CONFLICT(client,ip) DO UPDATE SET last_seen=excluded.last_seen, hits=hits+1", (name, ip, ts, ts))
        self.mark_dirty()

    def client_ips(self, name):
        return self._rows("SELECT * FROM client_ips WHERE client=? ORDER BY last_seen DESC", (name,))

    def active_ip_count(self, name, window=120):
        r = self._rows("SELECT COUNT(*) c FROM client_ips WHERE client=? AND last_seen>=?", (name, int(time.time()) - window))
        return r[0]["c"] if r else 0

    def touch_visit(self, name, ip, host, port, blocked=False, ts=None):
        ts = ts or int(time.time())
        self._exec(
            "INSERT INTO visits(client,ip,host,port,first_seen,last_seen,hits,blocked) VALUES(?,?,?,?,?,?,1,?) "
            "ON CONFLICT(client,ip,host,port) DO UPDATE SET last_seen=excluded.last_seen, hits=hits+1, blocked=excluded.blocked",
            (name, ip, host, int(port), ts, ts, 1 if blocked else 0))
        self.mark_dirty()

    def visits(self, name, ip=None, limit=500, q=None):
        sql, p = "SELECT * FROM visits WHERE client=?", [name]
        if ip:
            sql += " AND ip=?"; p.append(ip)
        if q:
            sql += " AND host LIKE ?"; p.append(f"%{q}%")
        sql += " ORDER BY last_seen DESC LIMIT ?"; p.append(limit)
        return self._rows(sql, p)

    def visit_summary(self, name):
        r = self._rows("SELECT COUNT(DISTINCT host) hosts, COALESCE(SUM(hits),0) hits, "
                       "COALESCE(SUM(CASE WHEN blocked=1 THEN hits ELSE 0 END),0) blocked FROM visits WHERE client=?", (name,))
        return r[0] if r else {"hosts": 0, "hits": 0, "blocked": 0}

    def blocked_stats(self, since=0):
        r = self._rows("SELECT COALESCE(SUM(CASE WHEN blocked=1 THEN hits ELSE 0 END),0) blocked, COALESCE(SUM(hits),0) total "
                       "FROM visits WHERE last_seen>=?", (since,))
        return r[0] if r else {"blocked": 0, "total": 0}

    def top_blocked(self, limit=15):
        return self._rows("SELECT host, SUM(hits) hits FROM visits WHERE blocked=1 GROUP BY host ORDER BY hits DESC LIMIT ?", (limit,))

    def recent_visits(self, limit=50):
        return self._rows("SELECT client, ip, host, port, last_seen, blocked FROM visits ORDER BY last_seen DESC LIMIT ?", (limit,))

    # ---- login security
    def record_login(self, ip, ok):
        self._exec("INSERT INTO login_attempts(ip,ts,ok) VALUES(?,?,?)", (ip, int(time.time()), 1 if ok else 0))

    def failed_logins(self, ip, window):
        r = self._rows("SELECT COUNT(*) c, MAX(ts) last FROM login_attempts WHERE ip=? AND ok=0 AND ts>=?", (ip, int(time.time()) - window))
        return (r[0]["c"] or 0, r[0]["last"] or 0) if r else (0, 0)

    def clear_failed(self, ip):
        self._exec("DELETE FROM login_attempts WHERE ip=? AND ok=0", (ip,))

    # =====================================================================
    # Telegram bot: users
    # =====================================================================
    def tg_user(self, tg_id):
        r = self._rows("SELECT * FROM tg_users WHERE tg_id=?", (int(tg_id),))
        if not r:
            return None
        u = r[0]
        try:
            u["state_data"] = json.loads(u["state_data"] or "{}")
        except Exception:
            u["state_data"] = {}
        return u

    def tg_upsert_user(self, tg_id, username="", first_name="", lang=None, referred_by=None):
        now = int(time.time())
        u = self.tg_user(tg_id)
        if u:
            self._exec("UPDATE tg_users SET username=?, first_name=?, last_seen=? WHERE tg_id=?",
                       (username or u["username"], first_name or u["first_name"], now, int(tg_id)))
            self.mark_dirty()
            return self.tg_user(tg_id), False
        self._exec("INSERT INTO tg_users(tg_id,username,first_name,lang,referred_by,created_at,last_seen) VALUES(?,?,?,?,?,?,?)",
                   (int(tg_id), username or "", first_name or "", lang or "fa", referred_by, now, now))
        if referred_by:
            self._exec("UPDATE tg_users SET referrals=referrals+1 WHERE tg_id=?", (int(referred_by),))
        self.mark_dirty()
        return self.tg_user(tg_id), True

    def tg_update_user(self, tg_id, **fields):
        allowed = {k: v for k, v in fields.items() if k in ("username", "first_name", "lang", "banned", "is_admin", "note", "last_seen")}
        if not allowed:
            return
        self._exec(f"UPDATE tg_users SET {','.join(f'{k}=?' for k in allowed)} WHERE tg_id=?", (*allowed.values(), int(tg_id)))
        self.mark_dirty()

    def tg_set_state(self, tg_id, state="", data=None):
        self._exec("UPDATE tg_users SET state=?, state_data=? WHERE tg_id=?",
                   (state or "", json.dumps(data or {}, ensure_ascii=False), int(tg_id)))

    def tg_users(self, limit=50, offset=0, q=None):
        if q:
            like = f"%{q}%"
            return self._rows("SELECT * FROM tg_users WHERE username LIKE ? OR first_name LIKE ? OR CAST(tg_id AS TEXT) LIKE ? "
                              "ORDER BY last_seen DESC LIMIT ? OFFSET ?", (like, like, like, limit, offset))
        return self._rows("SELECT * FROM tg_users ORDER BY last_seen DESC LIMIT ? OFFSET ?", (limit, offset))

    def tg_user_count(self):
        r = self._rows("SELECT COUNT(*) c FROM tg_users")
        return r[0]["c"] if r else 0

    def tg_all_ids(self, exclude_banned=True):
        sql = "SELECT tg_id FROM tg_users" + (" WHERE banned=0" if exclude_banned else "")
        return [r["tg_id"] for r in self._rows(sql)]

    def tg_referrals(self, tg_id, limit=30):
        return self._rows("SELECT tg_id, username, first_name, created_at FROM tg_users WHERE referred_by=? ORDER BY created_at DESC LIMIT ?",
                          (int(tg_id), limit))

    # ---- balances (wallet = toman, coins = referral points). Every change leaves a ledger row.
    def tg_adjust(self, tg_id, kind, delta, reason="", ref=""):
        """kind: 'wallet' | 'coins'. Returns new balance or raises ValueError on insufficient funds."""
        col = "wallet" if kind == "wallet" else "coins"
        with _lock:
            self.conn.execute("BEGIN")
            try:
                row = self.conn.execute(f"SELECT {col} FROM tg_users WHERE tg_id=?", (int(tg_id),)).fetchone()
                if not row:
                    raise ValueError("no such user")
                bal = int(row[0]) + int(delta)
                if bal < 0:
                    raise ValueError("insufficient")
                self.conn.execute(f"UPDATE tg_users SET {col}=? WHERE tg_id=?", (bal, int(tg_id)))
                self.conn.execute("INSERT INTO ledger(tg_id,kind,delta,balance,reason,ref,ts) VALUES(?,?,?,?,?,?,?)",
                                  (int(tg_id), col, int(delta), bal, reason[:200], str(ref)[:64], int(time.time())))
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        self.mark_dirty()
        return bal

    def tg_ledger(self, tg_id, limit=20):
        return self._rows("SELECT * FROM ledger WHERE tg_id=? ORDER BY id DESC LIMIT ?", (int(tg_id), limit))

    # ---- plans
    def plans(self, only_active=True):
        return self._rows("SELECT * FROM plans" + (" WHERE active=1" if only_active else "") + " ORDER BY sort, id")

    def plan(self, pid):
        r = self._rows("SELECT * FROM plans WHERE id=?", (int(pid),))
        return r[0] if r else None

    def add_plan(self, title, gb, days, price, coin_price=0, ip_limit=0, sort=0):
        cur = self._exec("INSERT INTO plans(title,gb,days,price,coin_price,ip_limit,sort) VALUES(?,?,?,?,?,?,?)",
                         (title, int(gb), int(days), int(price), int(coin_price), int(ip_limit), int(sort)))
        self.mark_dirty()
        return cur.lastrowid

    def update_plan(self, pid, **f):
        allowed = {k: v for k, v in f.items() if k in ("title", "gb", "days", "price", "coin_price", "ip_limit", "active", "sort")}
        if allowed:
            self._exec(f"UPDATE plans SET {','.join(f'{k}=?' for k in allowed)} WHERE id=?", (*allowed.values(), int(pid)))
            self.mark_dirty()

    def delete_plan(self, pid):
        self._exec("DELETE FROM plans WHERE id=?", (int(pid),))
        self.mark_dirty()

    # ---- receipts (idempotent approvals)
    def new_receipt_id(self):
        import secrets as _s
        for _ in range(20):
            rid = "R" + _s.token_hex(3).upper()
            if not self._rows("SELECT 1 FROM receipts WHERE id=?", (rid,)):
                return rid
        return "R" + _s.token_hex(5).upper()

    def create_receipt(self, tg_id, kind, amount, plan_id=None, file_id="", text=""):
        rid = self.new_receipt_id()
        self._exec("INSERT INTO receipts(id,tg_id,kind,amount,plan_id,file_id,text,created_at) VALUES(?,?,?,?,?,?,?,?)",
                   (rid, int(tg_id), kind, int(amount), plan_id, file_id or "", (text or "")[:500], int(time.time())))
        self.mark_dirty()
        return self.receipt(rid)

    def receipt(self, rid):
        r = self._rows("SELECT * FROM receipts WHERE id=?", (rid,))
        if not r:
            return None
        x = r[0]
        try:
            x["admin_msg"] = json.loads(x["admin_msg"] or "{}")
        except Exception:
            x["admin_msg"] = {}
        return x

    def set_receipt_admin_msg(self, rid, data):
        self._exec("UPDATE receipts SET admin_msg=? WHERE id=?", (json.dumps(data), rid))

    def decide_receipt(self, rid, status, admin_id, result=""):
        """Atomic transition pending -> approved/rejected. Returns True only for the FIRST decision."""
        with _lock:
            cur = self.conn.execute("UPDATE receipts SET status=?, admin_id=?, decided_at=?, result=? WHERE id=? AND status='pending'",
                                    (status, int(admin_id), int(time.time()), result[:500], rid))
        self.mark_dirty()
        return cur.rowcount == 1

    def receipts(self, status=None, limit=30, tg_id=None):
        sql, p = "SELECT * FROM receipts WHERE 1=1", []
        if status:
            sql += " AND status=?"; p.append(status)
        if tg_id:
            sql += " AND tg_id=?"; p.append(int(tg_id))
        sql += " ORDER BY created_at DESC LIMIT ?"; p.append(limit)
        return self._rows(sql, p)

    def add_order(self, tg_id, plan_id, client, method, amount, receipt_id=None):
        self._exec("INSERT INTO orders(tg_id,plan_id,client,method,amount,receipt_id,created_at) VALUES(?,?,?,?,?,?,?)",
                   (int(tg_id), plan_id, client, method, int(amount), receipt_id, int(time.time())))
        self.mark_dirty()

    def orders(self, tg_id=None, limit=30):
        if tg_id:
            return self._rows("SELECT * FROM orders WHERE tg_id=? ORDER BY id DESC LIMIT ?", (int(tg_id), limit))
        return self._rows("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))

    def sales_stats(self, since=0):
        r = self._rows("SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN method!='coins' THEN amount ELSE 0 END),0) toman "
                       "FROM orders WHERE created_at>=?", (since,))
        return r[0] if r else {"n": 0, "toman": 0}

    def clients_of(self, tg_id):
        return self._rows("SELECT * FROM clients WHERE owner_tg=? ORDER BY created_at DESC", (int(tg_id),))

    # ---- alerts (80% usage etc.) — once per (client, kind) until reset
    def alert_sent(self, client, kind):
        return bool(self._rows("SELECT 1 FROM client_alerts WHERE client=? AND kind=?", (client, kind)))

    def mark_alert(self, client, kind):
        self._exec("INSERT OR REPLACE INTO client_alerts(client,kind,ts) VALUES(?,?,?)", (client, kind, int(time.time())))
        self.mark_dirty()

    def clear_alerts(self, client):
        self._exec("DELETE FROM client_alerts WHERE client=?", (client,))

    # =====================================================================
    # AI support: memory / sessions / workers / log
    # =====================================================================
    def ai_memories(self, target, tg_id=0):
        return self._rows("SELECT * FROM ai_memory WHERE target=? AND tg_id=? ORDER BY id", (target, int(tg_id)))

    def ai_memory_add(self, target, content, tg_id=0):
        now = int(time.time())
        cur = self._exec("INSERT INTO ai_memory(target,tg_id,content,created_at,updated_at) VALUES(?,?,?,?,?)",
                         (target, int(tg_id), content.strip()[:1000], now, now))
        self.mark_dirty()
        return cur.lastrowid

    def ai_memory_replace(self, mid, content):
        self._exec("UPDATE ai_memory SET content=?, updated_at=? WHERE id=?", (content.strip()[:1000], int(time.time()), int(mid)))
        self.mark_dirty()

    def ai_memory_remove(self, mid):
        self._exec("DELETE FROM ai_memory WHERE id=?", (int(mid),))
        self.mark_dirty()

    def ai_memory_all(self, limit=300):
        return self._rows("SELECT * FROM ai_memory ORDER BY target, tg_id, id LIMIT ?", (limit,))

    def ai_session_open(self, tg_id):
        r = self._rows("SELECT * FROM ai_sessions WHERE tg_id=? AND closed=0 ORDER BY last_at DESC LIMIT 1", (int(tg_id),))
        return self._ai_sess(r[0]) if r else None

    def _ai_sess(self, row):
        try:
            row["messages"] = json.loads(row["messages"] or "[]")
        except Exception:
            row["messages"] = []
        return row

    def ai_session_create(self, tg_id, worker):
        import secrets as _s
        sid = "S" + _s.token_hex(4)
        now = int(time.time())
        self._exec("INSERT INTO ai_sessions(id,tg_id,worker,started_at,last_at) VALUES(?,?,?,?,?)", (sid, int(tg_id), int(worker), now, now))
        self.mark_dirty()
        return self._ai_sess(self._rows("SELECT * FROM ai_sessions WHERE id=?", (sid,))[0])

    def ai_session_save(self, sid, messages, turns=None, tool_calls=None):
        self._exec("UPDATE ai_sessions SET messages=?, last_at=?, turns=COALESCE(?,turns), tool_calls=COALESCE(?,tool_calls) WHERE id=?",
                   (json.dumps(messages, ensure_ascii=False), int(time.time()), turns, tool_calls, sid))
        self.mark_dirty()

    def ai_session_close(self, sid, summary=""):
        # messages are wiped (privacy + "session deleted" requirement); the transcript stays in ai_log for the owner.
        self._exec("UPDATE ai_sessions SET closed=1, messages='[]', summary=? WHERE id=?", (summary[:1000], sid))
        self.mark_dirty()

    def ai_sessions_idle(self, idle_seconds):
        return [self._ai_sess(r) for r in self._rows("SELECT * FROM ai_sessions WHERE closed=0 AND last_at<?", (int(time.time()) - idle_seconds,))]

    def ai_sessions_recent(self, limit=20, tg_id=None):
        if tg_id:
            return self._rows("SELECT id,tg_id,worker,started_at,last_at,closed,turns,tool_calls,summary FROM ai_sessions WHERE tg_id=? ORDER BY last_at DESC LIMIT ?", (int(tg_id), limit))
        return self._rows("SELECT id,tg_id,worker,started_at,last_at,closed,turns,tool_calls,summary FROM ai_sessions ORDER BY last_at DESC LIMIT ?", (limit,))

    def ai_log_add(self, sid, tg_id, kind, content):
        self._exec("INSERT INTO ai_log(session_id,tg_id,ts,kind,content) VALUES(?,?,?,?,?)", (sid, int(tg_id), int(time.time()), kind, str(content)[:4000]))

    def ai_log(self, sid, limit=200):
        return self._rows("SELECT * FROM ai_log WHERE session_id=? ORDER BY id LIMIT ?", (sid, limit))

    def ai_workers(self, only_active=False):
        return self._rows("SELECT * FROM ai_workers" + (" WHERE active=1" if only_active else "") + " ORDER BY id")

    def ai_worker(self, wid):
        r = self._rows("SELECT * FROM ai_workers WHERE id=?", (int(wid),))
        return r[0] if r else None

    def ai_worker_add(self, base_url, api_key, model="", name=""):
        cur = self._exec("INSERT INTO ai_workers(name,base_url,api_key,model,created_at) VALUES(?,?,?,?,?)",
                         (name or "", base_url.strip().rstrip("/"), api_key.strip(), model.strip(), int(time.time())))
        self.mark_dirty()
        return cur.lastrowid

    def ai_worker_update(self, wid, **f):
        allowed = {k: v for k, v in f.items() if k in ("name", "base_url", "api_key", "model", "active")}
        if allowed:
            self._exec(f"UPDATE ai_workers SET {','.join(f'{k}=?' for k in allowed)} WHERE id=?", (*allowed.values(), int(wid)))
            self.mark_dirty()

    def ai_worker_delete(self, wid):
        self._exec("DELETE FROM ai_workers WHERE id=?", (int(wid),))
        self.mark_dirty()

    def ai_worker_stat(self, wid, requests=0, errors=0, rate_limits=0):
        self._exec("UPDATE ai_workers SET requests=requests+?, errors=errors+?, rate_limits=rate_limits+?, last_used=? WHERE id=?",
                   (requests, errors, rate_limits, int(time.time()), int(wid)))

    # ---- maintenance
    def prune(self, retention_days=settings.HISTORY_RETENTION_DAYS):
        cutoff = int(time.time()) - retention_days * 86400
        with _lock:
            self.conn.execute("DELETE FROM traffic_samples WHERE ts<?", (cutoff,))
            self.conn.execute("DELETE FROM visits WHERE last_seen<?", (cutoff,))
            self.conn.execute("DELETE FROM events WHERE ts<?", (cutoff,))
            self.conn.execute("DELETE FROM login_attempts WHERE ts<?", (int(time.time()) - 86400,))
            self.conn.execute("DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 3000)")
            self.conn.execute("DELETE FROM ai_log WHERE id NOT IN (SELECT id FROM ai_log ORDER BY id DESC LIMIT 5000)")
            self.conn.execute("DELETE FROM ledger WHERE id NOT IN (SELECT id FROM ledger ORDER BY id DESC LIMIT 20000)")
            self.conn.execute("DELETE FROM ai_sessions WHERE closed=1 AND last_at<?", (cutoff,))

    # ---- vault
    def export_all(self):
        out = {"version": 2, "exported_at": int(time.time()), "tables": {}}
        with _lock:
            for t in EXPORT_TABLES:
                out["tables"][t] = [dict(r) for r in self.conn.execute(f"SELECT * FROM {t}").fetchall()]
        return out

    def import_all(self, dump):
        tables = dump.get("tables", {})
        with _lock:
            self.conn.execute("BEGIN")
            try:
                for t in EXPORT_TABLES:
                    rows = tables.get(t) or []
                    self.conn.execute(f"DELETE FROM {t}")
                    if not rows:
                        continue
                    known = {r[1] for r in self.conn.execute(f"PRAGMA table_info({t})").fetchall()}
                    cols = [c for c in rows[0].keys() if c in known]
                    sql = f"INSERT OR REPLACE INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})"
                    self.conn.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def save_vault(self, path=settings.VAULT_PATH):
        dump = self.export_all()
        if settings.VAULT_KEY_MATERIAL:
            blob = crypto.encrypt_json(dump, settings.VAULT_KEY_MATERIAL)
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(blob)
            os.replace(tmp, path)
            if os.path.exists(settings.LEGACY_DB_PATH):
                try:
                    os.remove(settings.LEGACY_DB_PATH)
                except OSError:
                    pass
        else:
            legacy = {c["name"]: _to_legacy(c) for c in self.clients()}
            with open(settings.LEGACY_DB_PATH, "w") as f:
                json.dump(legacy, f, indent=2)
        self.dirty = False

    def load_vault(self, path=settings.VAULT_PATH):
        if os.path.exists(path) and settings.VAULT_KEY_MATERIAL:
            try:
                with open(path, "rb") as f:
                    self.import_all(crypto.decrypt_json(f.read(), settings.VAULT_KEY_MATERIAL))
                if self.clients() or not os.path.exists(settings.LEGACY_DB_PATH):
                    return "vault"
                print("ℹ️ vault has no clients; importing legacy panel_db.json", flush=True)
            except Exception as e:
                print(f"⚠️ vault decrypt failed ({e}); trying legacy json", flush=True)
        if os.path.exists(settings.LEGACY_DB_PATH):
            try:
                with open(settings.LEGACY_DB_PATH) as f:
                    legacy = json.load(f)
                n = 0
                for name, v in legacy.items():
                    if not self.client(name):
                        self.create_client(name, uuid=v.get("uuid"), total_limit_bytes=v.get("total_limit_bytes", 0),
                                           used_bytes=v.get("used_bytes", 0), down_bytes=v.get("used_bytes", 0),
                                           clean_ip=v.get("clean_ip"), created_at=v.get("created_at", int(time.time())),
                                           expire_seconds=v.get("expire_seconds", 2592000), active=v.get("active", True))
                        n += 1
                return f"legacy({n})"
            except Exception as e:
                print(f"⚠️ legacy import failed: {e}", flush=True)
        return "empty"


def _to_legacy(c):
    d = {k: c[k] for k in ("uuid", "total_limit_bytes", "used_bytes", "clean_ip", "status", "last_active_time",
                            "down_speed", "up_speed", "created_at", "expire_seconds")}
    d["active"] = bool(c["active"])
    return d
