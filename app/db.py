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
                scan_start TEXT DEFAULT '',
                scan_end TEXT DEFAULT '',
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
        # 迁移：旧表补 scan_start/scan_end 列
        cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
        if "scan_start" not in cols:
            c.execute("ALTER TABLE tasks ADD COLUMN scan_start TEXT DEFAULT ''")
        if "scan_end" not in cols:
            c.execute("ALTER TABLE tasks ADD COLUMN scan_end TEXT DEFAULT ''")


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


def create_task(name, anchor_home, platform="douyin", anchor_name="", cron="*/10 * * * *", scan_start="", scan_end=""):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO tasks(name,platform,anchor_home,anchor_name,cron,enabled,scan_start,scan_end) "
            "VALUES(?,?,?,?,?,1,?,?)",
            (name, platform, anchor_home, anchor_name, cron, scan_start, scan_end),
        )
        return cur.lastrowid


def update_task(task_id, **fields):
    allowed = {"name", "platform", "anchor_home", "anchor_name", "cron", "enabled", "scan_start", "scan_end"}
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


def get_recording(rec_id):
    with _conn() as c:
        r = c.execute("SELECT * FROM recordings WHERE id=?", (rec_id,)).fetchone()
    return dict(r) if r else None


def delete_recording(rec_id):
    with _conn() as c:
        c.execute("DELETE FROM recordings WHERE id=?", (rec_id,))


def delete_recordings_by_task(task_id):
    with _conn() as c:
        c.execute("DELETE FROM recordings WHERE task_id=?", (task_id,))


def dashboard_stats():
    """看板统计：任务概览 + 产物概览 + 今日数据 + 最近产物。"""
    today = datetime.now().strftime("%Y-%m-%d")
    with _conn() as c:
        task_total = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        task_enabled = c.execute("SELECT COUNT(*) FROM tasks WHERE enabled=1").fetchone()[0]
        rec_total = c.execute("SELECT COUNT(*) FROM recordings").fetchone()[0]
        rec_completed = c.execute("SELECT COUNT(*) FROM recordings WHERE status='completed'").fetchone()[0]
        rec_failed = c.execute("SELECT COUNT(*) FROM recordings WHERE status='failed'").fetchone()[0]
        total_duration = c.execute("SELECT COALESCE(SUM(duration),0) FROM recordings").fetchone()[0]
        total_size = c.execute("SELECT COALESCE(SUM(file_size),0) FROM recordings").fetchone()[0]
        today_count = c.execute(
            "SELECT COUNT(*) FROM recordings WHERE start_time LIKE ?", (today + "%",)
        ).fetchone()[0]
        today_duration = c.execute(
            "SELECT COALESCE(SUM(duration),0) FROM recordings WHERE start_time LIKE ?", (today + "%",)
        ).fetchone()[0]
        today_size = c.execute(
            "SELECT COALESCE(SUM(file_size),0) FROM recordings WHERE start_time LIKE ?", (today + "%",)
        ).fetchone()[0]
    recent = list_recordings()[:10]
    return {
        "task_total": task_total,
        "task_enabled": task_enabled,
        "rec_total": rec_total,
        "rec_completed": rec_completed,
        "rec_failed": rec_failed,
        "total_duration": total_duration,
        "total_size": total_size,
        "today_count": today_count,
        "today_duration": today_duration,
        "today_size": today_size,
        "recent": recent,
    }
