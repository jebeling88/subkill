import os, sqlite3, threading
from contextlib import contextmanager

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
  pw_hash TEXT NOT NULL, salt TEXT NOT NULL,
  members TEXT NOT NULL DEFAULT '["Me"]',
  gmail_tokens TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS subscriptions(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
  merchant TEXT NOT NULL, merchant_key TEXT NOT NULL, plan TEXT,
  amount_cents INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'USD',
  cycle TEXT NOT NULL DEFAULT 'monthly', monthly_cents INTEGER NOT NULL DEFAULT 0,
  category TEXT DEFAULT 'Other', owner TEXT DEFAULT 'Me',
  status TEXT NOT NULL DEFAULT 'active',   -- active|trial|cancelling|cancelled
  started_at TEXT, last_charged_at TEXT, last_used_at TEXT, next_renewal TEXT,
  use_count INTEGER NOT NULL DEFAULT 0,
  cancel_url TEXT, cancel_plan TEXT, notes TEXT, source TEXT,
  cancel_requested_at TEXT, cancelled_at TEXT,
  still_charging INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, merchant_key, owner));
CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id, status);
"""

def path():
    return os.environ.get("SUBKILL_DB", "subkill.db")

def conn():
    p = path()
    c = getattr(_local, "c", None)
    if c is None or getattr(_local, "p", None) != p:
        c = sqlite3.connect(p, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        _local.c, _local.p = c, p
    return c

@contextmanager
def tx():
    c = conn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
