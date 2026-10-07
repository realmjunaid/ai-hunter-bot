"""Seen-tweet store (sqlite, WAL mode)."""
import sqlite3
import time

SCHEMA = "CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, ts INTEGER)"


def connect(path: str):
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(SCHEMA)
    return db


def is_seen(db, tweet_id: str) -> bool:
    row = db.execute("SELECT 1 FROM seen WHERE id=?", (str(tweet_id),)).fetchone()
    return row is not None


def mark_seen(db, tweet_id: str):
    db.execute("INSERT OR IGNORE INTO seen VALUES (?, ?)", (str(tweet_id), int(time.time())))
    db.commit()


def prune(db, days: int = 30):
    db.execute("DELETE FROM seen WHERE ts < ?", (int(time.time()) - days * 86400,))
    db.commit()
