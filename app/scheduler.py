# -*- coding: utf-8 -*-
"""APScheduler 定时调度：每个启用任务注册一个 cron job，到点检查开播并录制。"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import db
from app import executor

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def _job(task):
    result = executor.run_recording(task)
    return result


def reload_jobs():
    """重建所有启用任务的定时 job。任务增删改后调用。"""
    try:
        for job in scheduler.get_jobs():
            scheduler.remove_job(job.id)
    except Exception:
        pass
    for task in db.list_tasks():
        if task.get("enabled"):
            try:
                scheduler.add_job(
                    _job,
                    CronTrigger.from_crontab(task["cron"], timezone="Asia/Shanghai"),
                    args=[task],
                    id=f"task_{task['id']}",
                    replace_existing=True,
                    misfire_grace_time=300,
                    coalesce=True,
                )
            except Exception as e:
                print(f"[scheduler] 任务 {task['id']} cron 无效: {e}")


def start():
    scheduler.start()
