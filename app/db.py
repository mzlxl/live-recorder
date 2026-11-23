# -*- coding: utf-8 -*-
"""SQLite 数据层：任务表 + 产物表"""
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "storage", "recorder.db")
STORAGE_DIR = os.path.join(BASE_DIR, "storage", "recordings")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'douyin',
                anchor_home TEXT NOT NULL,
                anchor_name TEXT DEFAULT '',
                cron TEXT NOT NULL DEFAULT '*/10 * * * *',
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                start_time TEXT,
                end_time TEXT,
                duration INTEGER DEFAULT 0,
                file_path TEXT,
                file_size INTEGER DEFAULT 0,
                status TEXT DEFAULT 'recording',
                error TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );
            """
        )


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- 任务 CRUD ----------
def list_tasks():
    with _conn() as c:
        rows = c.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def get_task(task_id):
    with _conn() as c:
        r = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return dict(r) if r else None


def create_task(name, anchor_home, platform="douyin", anchor_name="", cron="*/10 * * * *"):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO tasks(name,platform,anchor_home,anchor_name,cron,enabled) "
            "VALUES(?,?,?,?,?,1)",
            (name, platform, anchor_home, anchor_name, cron),
        )
        return cur.lastrowid


def update_task(task_id, **fields):
    allowed = {"name", "platform", "anchor_home", "anchor_name", "cron", "enabled"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    sets.append("updated_at=?")
    vals.append(now_str())
    vals.append(task_id)
    with _conn() as c:
        c.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", vals)


def delete_task(task_id):
    with _conn() as c:
        c.execute("DELETE FROM tasks WHERE id=?", (task_id,))


# ---------- 产物 CRUD ----------
def list_recordings(task_id=None):
    with _conn() as c:
        if task_id:
            rows = c.execute(
                "SELECT * FROM recordings WHERE task_id=? ORDER BY id DESC", (task_id,)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM recordings ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def create_recording(task_id):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO recordings(task_id,start_time,status) VALUES(?,?, 'recording')",
            (task_id, now_str()),
        )
        return cur.lastrowid


def finish_recording(rec_id, file_path, duration, file_size, status="completed", error=""):
    with _conn() as c:
        c.execute(
            "UPDATE recordings SET end_time=?, duration=?, file_path=?, file_size=?, status=?, error=? "
            "WHERE id=?",
            (now_str(), duration, file_path, file_size, status, error, rec_id),
        )
