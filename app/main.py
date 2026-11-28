# -*- coding: utf-8 -*-
"""FastAPI 入口：REST API + 前端静态页 + 产物静态服务。"""
import json
import os
import re
from urllib.parse import urlsplit, quote
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
from app import db, executor, fsutils, transcription
from app.scheduler import scheduler, reload_jobs
from app.platforms import list_platforms
from app.recorder import current_recorder, detect_ffmpeg
from app.recorder.loopback import LoopbackCapture


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    reload_jobs()
    scheduler.start()
    stopping, worker = transcription.start()
    try:
        yield
    finally:
        stopping.set()
        worker.join()
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
        "desktop_files": fsutils.desktop_available(),
        "running": list(executor._running),
    }


# ---------- 任务 ----------
@app.get("/api/tasks")
def api_tasks():
    tasks = db.list_tasks(with_counts=True)
    for t in tasks:
        t["running"] = executor.is_running(t["id"])
        t["paused"] = executor.is_paused(t["id"])
        t["capturing"] = executor.is_capturing(t["id"])
        t["last_result"] = executor.last_result.get(t["id"], "")
    return tasks


def validate_task(fields):
    if "name" in fields and not fields["name"].strip():
        raise HTTPException(422, "请填写任务名称")
    if fields.get("platform", "douyin") != "douyin":
        raise HTTPException(422, "请选择已支持的直播平台")
    if "anchor_home" in fields:
        try:
            url = urlsplit(fields["anchor_home"])
            valid = url.scheme in ("http", "https") and url.hostname in ("douyin.com", "www.douyin.com")
            valid = valid and re.fullmatch(r"/user/[\w-]+/?", url.path)
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(422, "请填写有效的抖音主播主页")


@app.post("/api/tasks")
def api_create(task: TaskIn):
    validate_task(task.model_dump())
    tid = db.create_task(task.name, task.anchor_home, task.platform, task.anchor_name,
                         task.cron, task.scan_start, task.scan_end, task.interval_minutes)
    reload_jobs()
    return {"id": tid}


@app.put("/api/tasks/{task_id}")
def api_update(task_id: int, task: TaskUpdate):
    if not db.get_task(task_id):
        raise HTTPException(404, "任务不存在")
    fields = {k: v for k, v in task.model_dump().items() if v is not None}
    if not fields:
        return {"ok": True}
    validate_task(fields)
    db.update_task(task_id, **fields)
    reload_jobs()
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
def api_delete(task_id: int, delete_files: bool = False):
    if executor.is_running(task_id):
        raise HTTPException(409, "请先结束录制或等待检查完成")
    if not db.get_task(task_id):
        raise HTTPException(404, "任务不存在")
    if delete_files:
        for r in db.list_recordings(task_id):
            fp = r.get("file_path")
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                except OSError as exc:
                    raise HTTPException(409, "无法删除音频，请关闭占用文件的程序后重试") from exc
    db.delete_recordings_by_task(task_id)
    db.delete_task(task_id)
    reload_jobs()
    return {"ok": True}


@app.post("/api/tasks/{task_id}/run")
def api_run(task_id: int):
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    reason = executor.start_recording(task)
    if reason:
        raise HTTPException(409, reason)
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
    rec["file_url"] = "/recordings/" + quote(os.path.basename(fp)) if fp and exists else None
    return rec


@app.get("/api/recordings")
def api_recordings(task_id: Optional[int] = None):
    return [with_file_info(r) for r in db.list_recordings(task_id)]


@app.get("/api/recordings/{rec_id}/transcript")
def api_transcript(rec_id: int):
    if not db.get_recording(rec_id):
        raise HTTPException(404, "录音不存在")
    result = db.get_transcript(rec_id)
    result["paragraphs"] = json.loads(result["paragraphs"] or "[]")
    return result


@app.post("/api/recordings/{rec_id}/transcript")
def api_request_transcript(rec_id: int):
    rec = db.get_recording(rec_id)
    if not rec:
        raise HTTPException(404, "录音不存在")
    if rec["status"] != "completed" or not with_file_info(rec)["file_exists"]:
        raise HTTPException(409, "需要已完成且文件可用的录音")
    db.request_transcript(rec_id)
    return {"ok": True}


@app.get("/api/dashboard")
def api_dashboard():
    stats = db.dashboard_stats()
    running = [db.get_task(tid) for tid in executor._running]
    running = [t for t in running if t]
    for t in running:
        t["paused"] = executor.is_paused(t["id"])
        t["capturing"] = executor.is_capturing(t["id"])
        t["last_result"] = executor.last_result.get(t["id"], "")
    stats["running_tasks"] = running
    stats["recent"] = [with_file_info(r) for r in stats["recent"]]
    return stats


@app.delete("/api/recordings/{rec_id}")
def api_delete_recording(rec_id: int):
    rec = db.get_recording(rec_id)
    if not rec:
        raise HTTPException(404, "产物不存在")
    if rec["status"] == "recording":
        raise HTTPException(409, "请先结束录制")
    fp = rec.get("file_path")
    if fp and os.path.exists(fp):
        try:
            os.remove(fp)
        except OSError as exc:
            raise HTTPException(409, "无法删除音频，请关闭占用文件的程序后重试") from exc
    db.delete_recording(rec_id)
    return {"ok": True}


@app.post("/api/recordings/{rec_id}/open")
def api_open_recording(rec_id: int):
    rec = db.get_recording(rec_id)
    if not rec:
        raise HTTPException(404, "产物不存在")
    if not fsutils.desktop_available():
        raise HTTPException(409, "服务器没有图形桌面，请使用浏览器试听或下载")
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
    if not fsutils.desktop_available():
        raise HTTPException(409, "服务器没有图形桌面，请使用浏览器试听或下载")
    try:
        return {"ok": fsutils.reveal_file(rec.get("file_path"))}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/recordings/folder")
def api_open_folder():
    if not fsutils.desktop_available():
        raise HTTPException(409, "服务器没有图形桌面，请使用浏览器试听或下载")
    try:
        return {"ok": fsutils.open_dir(config.STORAGE_DIR)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------- 静态 ----------
app.mount("/recordings", StaticFiles(directory=config.STORAGE_DIR), name="recordings")
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
