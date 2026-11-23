# -*- coding: utf-8 -*-
"""FastAPI 入口：REST API + 前端静态页 + 产物静态服务。"""
import os
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from app import db, executor
from app.scheduler import scheduler, reload_jobs
from app.platforms import list_platforms
from app.recorder import current_recorder, detect_ffmpeg


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


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    anchor_home: Optional[str] = None
    anchor_name: Optional[str] = None
    cron: Optional[str] = None
    enabled: Optional[bool] = None


# ---------- 元信息 ----------
@app.get("/api/platforms")
def api_platforms():
    return list_platforms()


@app.get("/api/status")
def api_status():
    rec = current_recorder()
    return {
        "ffmpeg": detect_ffmpeg(),
        "recorder_device_ready": rec.device_ready(),
        "device_hint": rec.device_hint,
        "running": list(executor._running),
    }


# ---------- 任务 ----------
@app.get("/api/tasks")
def api_tasks():
    tasks = db.list_tasks()
    for t in tasks:
        t["running"] = executor.is_running(t["id"])
        t["recording_count"] = len(db.list_recordings(t["id"]))
    return tasks


@app.post("/api/tasks")
def api_create(task: TaskIn):
    tid = db.create_task(task.name, task.anchor_home, task.platform, task.anchor_name, task.cron)
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
def api_delete(task_id: int):
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


# ---------- 产物 ----------
@app.get("/api/recordings")
def api_recordings(task_id: Optional[int] = None):
    recs = db.list_recordings(task_id)
    for r in recs:
        if r.get("file_path"):
            r["file_url"] = "/recordings/" + os.path.basename(r["file_path"])
    return recs


# ---------- 静态 ----------
app.mount("/recordings", StaticFiles(directory=config.STORAGE_DIR), name="recordings")
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
