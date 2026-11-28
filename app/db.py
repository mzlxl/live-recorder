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
    conn.execute("PRAGMA foreign_keys=ON")
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
                interval_minutes INTEGER,
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
            CREATE TABLE IF NOT EXISTS transcripts (
                recording_id INTEGER PRIMARY KEY REFERENCES recordings(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'queued',
                paragraphs TEXT,
                processed REAL NOT NULL DEFAULT 0,
                error TEXT DEFAULT ''
            );
            """
        )
        # 迁移：旧表补 scan_start/scan_end/interval_minutes 列
        cols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
        if "scan_start" not in cols:
            c.execute("ALTER TABLE tasks ADD COLUMN scan_start TEXT DEFAULT ''")
        if "scan_end" not in cols:
            c.execute("ALTER TABLE tasks ADD COLUMN scan_end TEXT DEFAULT ''")
        if "interval_minutes" not in cols:
            c.execute("ALTER TABLE tasks ADD COLUMN interval_minutes INTEGER")

        if "processed" not in {r[1] for r in c.execute("PRAGMA table_info(transcripts)")}:
            c.execute("ALTER TABLE transcripts ADD COLUMN processed REAL NOT NULL DEFAULT 0")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- 任务 CRUD ----------
def list_tasks(with_counts=False):
    with _conn() as c:
        if with_counts:
            rows = c.execute("""SELECT t.*, COALESCE(r.n,0) AS recording_count FROM tasks t
                                LEFT JOIN (SELECT task_id, COUNT(*) AS n FROM recordings GROUP BY task_id) r
                                ON r.task_id=t.id ORDER BY t.id DESC""").fetchall()
        else:
            rows = c.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def get_task(task_id):
    with _conn() as c:
        r = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return dict(r) if r else None


def create_task(name, anchor_home, platform="douyin", anchor_name="", cron="*/10 * * * *",
                scan_start="", scan_end="", interval_minutes=None):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO tasks(name,platform,anchor_home,anchor_name,cron,interval_minutes,enabled,scan_start,scan_end) "
            "VALUES(?,?,?,?,?,?,1,?,?)",
            (name, platform, anchor_home, anchor_name, cron, interval_minutes, scan_start, scan_end),
        )
        return cur.lastrowid


def update_task(task_id, **fields):
    allowed = {"name", "platform", "anchor_home", "anchor_name", "cron", "interval_minutes",
               "enabled", "scan_start", "scan_end"}
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
def list_recordings(task_id=None, limit=None):
    query = """SELECT r.*, t.name AS task_name, x.status AS transcript_status
               FROM recordings r LEFT JOIN tasks t ON t.id=r.task_id
               LEFT JOIN transcripts x ON x.recording_id=r.id"""
    with _conn() as c:
        where, args = (" WHERE r.task_id=?", (task_id,)) if task_id is not None else ("", ())
        query += where + " ORDER BY r.id DESC"
        if limit is not None:
            query += " LIMIT ?"
            args += (limit,)
        rows = c.execute(query, args).fetchall()
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

        if status == "completed" and file_size > 0:
            c.execute("INSERT OR IGNORE INTO transcripts(recording_id) VALUES(?)", (rec_id,))


def claim_transcript():
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("""SELECT recording_id, file_path, processed, paragraphs FROM transcripts
                           JOIN recordings ON id=recording_id WHERE transcripts.status='queued'
                           ORDER BY recording_id LIMIT 1""").fetchone()
        if row:
            c.execute("UPDATE transcripts SET status='running' WHERE recording_id=?", (row[0],))
            return dict(row)


def checkpoint(rec_id, processed, paragraphs):
    with _conn() as c:
        return c.execute("""UPDATE transcripts SET processed=?, paragraphs=?
                            WHERE recording_id=? AND status='running'""",
                         (processed, paragraphs, rec_id)).rowcount == 1


def set_transcript_result(rec_id, status, paragraphs=None, error=""):
    with _conn() as c:
        c.execute("""UPDATE transcripts SET status=?, paragraphs=COALESCE(?,paragraphs), error=?
                     WHERE recording_id=? AND status='running'""", (status, paragraphs, error, rec_id))


def recover_transcripts():
    with _conn() as c:
        c.execute("UPDATE transcripts SET status='queued' WHERE status='running'")
        c.execute("""UPDATE recordings SET status='failed', error='服务中断，录音未正常结束',
                     end_time=? WHERE status='recording'""", (now_str(),))


def request_transcript(rec_id):
    with _conn() as c:
        c.execute("""INSERT INTO transcripts(recording_id) VALUES(?)
                     ON CONFLICT(recording_id) DO UPDATE SET status='queued', error='', paragraphs=NULL, processed=0
                     WHERE status='failed'""", (rec_id,))


def get_transcript(rec_id):
    with _conn() as c:
        row = c.execute("SELECT status, paragraphs, processed, error FROM transcripts WHERE recording_id=?",
                        (rec_id,)).fetchone()
        return dict(row) if row else {"status": "unavailable", "paragraphs": None, "error": ""}


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
    recent = list_recordings(limit=10)
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
