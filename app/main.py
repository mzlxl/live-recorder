# -*- coding: utf-8 -*-
"""FastAPI 入口：REST API + 前端静态页 + 产物静态服务。"""
import os
import re
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

ALLOWED_INTERVALS = (5, 10, 15, 20, 30, 45, 60, 90, 120)


def validate_hhmm(value):
    if value is None or value == "":
        return value
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("时间格式必须为 HH:MM")
    return value


def validate_interval(value):
    if value is not None and value not in ALLOWED_INTERVALS:
        raise ValueError("检查频率必须是 5/10/15/20/30/45/60/90/120 分钟之一")
    return value

import config
from app import db, executor, fsutils
from app.scheduler import scheduler, reload_jobs
from app.platforms import list_platforms
from app.recorder import current_recorder, detect_ffmpeg
from app.recorder.loopback import LoopbackCapture


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    reload_jobs()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="直播录制系统", lifespan=lifespan)


# ---------- 模型 ----------
class TaskIn(BaseModel):
    name: str
    platform: str = "douyin"
    anchor_home: str
    anchor_name: str = ""
    cron: str = "*/10 * * * *"
    interval_minutes: Optional[int] = None
    scan_start: str = ""
    scan_end: str = ""

    @field_validator("interval_minutes")
    @classmethod
    def check_interval(cls, v):
        return validate_interval(v)

    @field_validator("scan_start", "scan_end")
    @classmethod
    def check_time(cls, v):
        return validate_hhmm(v)


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    anchor_home: Optional[str] = None
    anchor_name: Optional[str] = None
    cron: Optional[str] = None
    interval_minutes: Optional[int] = None
    enabled: Optional[bool] = None
    scan_start: Optional[str] = None
    scan_end: Optional[str] = None

    @field_validator("interval_minutes")
    @classmethod
    def check_interval(cls, v):
        return validate_interval(v)

    @field_validator("scan_start", "scan_end")
    @classmethod
    def check_time(cls, v):
        return validate_hhmm(v)


# ---------- 元信息 ----------
@app.get("/api/platforms")
def api_platforms():
    return list_platforms()


@app.get("/api/status")
def api_status():
    rec = current_recorder()
    ffmpeg_bin = detect_ffmpeg()
    system_ready = bool(ffmpeg_bin and rec.device_ready())
    loopback_ready = bool(ffmpeg_bin and LoopbackCapture.SUPPORTED
                           and LoopbackCapture("", "").available())
    browser_ready = bool(ffmpeg_bin and config.browser_available())
    mode = "system" if system_ready else ("loopback" if loopback_ready else "browser")
    hints = {
        "system": rec.device_hint,
        "loopback": "未检测到虚拟声卡，已自动启用 Windows WASAPI 回环录系统输出（无需额外驱动）",
        "browser": "未检测到虚拟声卡，已自动启用浏览器内音频采集（macOS/Linux 无需额外驱动）",
    }
    return {
        "ffmpeg": ffmpeg_bin,
        "browser": config.BROWSER_EXECUTABLE,
        "recorder_device_ready": system_ready or loopback_ready or browser_ready,
        "system_audio_ready": system_ready,
        "capture_mode": mode,
        "device_hint": hints[mode],
        "running": list(executor._running),
    }


# ---------- 任务 ----------
@app.get("/api/tasks")
def api_tasks():
    tasks = db.list_tasks()
    for t in tasks:
        t["running"] = executor.is_running(t["id"])
        t["paused"] = executor.is_paused(t["id"])
        t["recording_count"] = len(db.list_recordings(t["id"]))
    return tasks


@app.post("/api/tasks")
def api_create(task: TaskIn):
    tid = db.create_task(task.name, task.anchor_home, task.platform, task.anchor_name,
                         task.cron, task.scan_start, task.scan_end, task.interval_minutes)
    reload_jobs()
    return {"id": tid}


@app.put("/api/tasks/{task_id}")
def api_update(task_id: int, task: TaskUpdate):
    fields = {k: v for k, v in task.model_dump().items() if v is not None}
    if not fields:
        return {"ok": True}
    db.update_task(task_id, **fields)
    reload_jobs()
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
def api_delete(task_id: int, delete_files: bool = False):
    if delete_files:
        for r in db.list_recordings(task_id):
            fp = r.get("file_path")
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                except OSError:
                    pass
    db.delete_recordings_by_task(task_id)
    db.delete_task(task_id)
    reload_jobs()
    return {"ok": True}


@app.post("/api/tasks/{task_id}/run")
def api_run(task_id: int):
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if executor.is_running(task_id):
        return {"ok": False, "msg": "该任务正在录制中"}
    threading.Thread(target=executor.run_recording, args=(task,), daemon=True).start()
    return {"ok": True, "msg": "已触发，稍后查看产物"}


@app.post("/api/tasks/{task_id}/pause")
def api_pause(task_id: int):
    if not executor.is_running(task_id):
        raise HTTPException(400, "该任务未在录制中")
    return {"ok": executor.pause_task(task_id)}


@app.post("/api/tasks/{task_id}/resume")
def api_resume(task_id: int):
    if not executor.is_running(task_id):
        raise HTTPException(400, "该任务未在录制中")
    return {"ok": executor.resume_task(task_id)}


@app.post("/api/tasks/{task_id}/stop")
def api_stop(task_id: int):
    if not executor.is_running(task_id):
        raise HTTPException(400, "该任务未在录制中")
    return {"ok": executor.stop_task(task_id)}


# ---------- 产物 ----------
def with_file_info(rec):
    fp = rec.get("file_path")
    exists = bool(fp and os.path.isfile(fp) and os.path.getsize(fp) > 0)
    rec["file_exists"] = exists
    rec["file_url"] = "/recordings/" + os.path.basename(fp) if fp and exists else None
    return rec


@app.get("/api/recordings")
def api_recordings(task_id: Optional[int] = None):
    return [with_file_info(r) for r in db.list_recordings(task_id)]


@app.get("/api/dashboard")
def api_dashboard():
    stats = db.dashboard_stats()
    running = [db.get_task(tid) for tid in executor._running]
    running = [t for t in running if t]
    for t in running:
        t["paused"] = executor.is_paused(t["id"])
    stats["running_tasks"] = running
    stats["recent"] = [with_file_info(r) for r in stats["recent"]]
    return stats


@app.delete("/api/recordings/{rec_id}")
def api_delete_recording(rec_id: int):
    rec = db.get_recording(rec_id)
    if not rec:
        raise HTTPException(404, "产物不存在")
    fp = rec.get("file_path")
    if fp and os.path.exists(fp):
        try:
            os.remove(fp)
        except OSError:
            pass
    db.delete_recording(rec_id)
    return {"ok": True}


@app.post("/api/recordings/{rec_id}/open")
def api_open_recording(rec_id: int):
    rec = db.get_recording(rec_id)
    if not rec:
        raise HTTPException(404, "产物不存在")
    try:
        return {"ok": fsutils.open_file(rec.get("file_path"))}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/recordings/{rec_id}/reveal")
def api_reveal_recording(rec_id: int):
    rec = db.get_recording(rec_id)
    if not rec:
        raise HTTPException(404, "产物不存在")
    try:
        return {"ok": fsutils.reveal_file(rec.get("file_path"))}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/recordings/folder")
def api_open_folder():
    try:
        return {"ok": fsutils.open_dir(config.STORAGE_DIR)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------- 静态 ----------
app.mount("/recordings", StaticFiles(directory=config.STORAGE_DIR), name="recordings")
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
