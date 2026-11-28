"""本地 Whisper 单工作线程。SQLite 保存队列及结果，服务重启后重新处理未完成项。"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import config
from app import db, executor
from app.recorder import detect_ffmpeg


def paragraphs(segments):
    """按词时间戳和句末标点断句，无标点时保留 Whisper 的分段边界。"""
    result = []
    group = []
    length = 0
    for segment in segments:
        words = segment.get("words") or [
            {"word": segment["text"], "start": segment["start"], "end": segment["end"]}
        ]
        sentence = ""
        for index, word in enumerate(words):
            if not sentence:
                start = word["start"]
            sentence += word["word"]
            if index + 1 < len(words) and not re.search(r"[。！？.!?][”’\"]?$", sentence.rstrip()):
                continue
            text = sentence.strip()
            sentence = ""
            if not text:
                continue
            if group and (start - group[-1]["end"] >= 2 or length + len(text) > 160 or len(group) >= 5):
                result.append(group)
                group, length = [], 0
            group.append({"start": start, "end": word["end"], "text": text})
            length += len(text)
    if group:
        result.append(group)
    return result


def recognize(path, stopping):
    path = Path(path or "")
    if not path.is_file():
        raise ValueError("录音文件缺失，请还原文件后重试")
    command = os.environ.get("RECORDER_WHISPER") or "whisper"
    path_env = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    whisper = shutil.which(command, path=path_env)
    if not whisper:
        raise ValueError("未找到 Whisper。请安装 openai-whisper 或配置 RECORDER_WHISPER 后重试")
    with tempfile.TemporaryDirectory(prefix="recorder-asr-") as directory:
        command = [whisper, str(path.resolve()), "--output_dir", directory, "--output_format", "json",
                   "--model", os.environ.get("RECORDER_WHISPER_MODEL") or "small",
                   "--language", "zh", "--word_timestamps", "True", "--verbose", "False",
                   "--fp16", "False", "--threads", "2"]
        env = os.environ.copy()
        ffmpeg = detect_ffmpeg()
        if ffmpeg:
            env["PATH"] = str(Path(ffmpeg).parent) + os.pathsep + env.get("PATH", "")
        with tempfile.TemporaryFile() as log, subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=log, env=env
        ) as proc:
            while proc.poll() is None:
                if stopping.wait(0.5):
                    proc.kill()
                    proc.wait()
                    raise InterruptedError
            if proc.returncode:
                log.seek(max(0, log.tell() - 600))
                raise ValueError("Whisper 执行失败：" + log.read().decode("utf-8", "replace").strip())
        output = Path(directory, path.stem + ".json")
        if not output.is_file():
            raise ValueError("Whisper 未生成文稿，请检查录音能否播放、模型是否完整后重试")
        return paragraphs(json.loads(output.read_text(encoding="utf-8"))["segments"])


def process(job, model_file, stopping):
    rec_id = job["recording_id"]
    try:
        if model_file:
            # 原生推理异常（例如 SIGSEGV）只结束子进程；SQLite 事务保留最后一个完整块。
            command = [sys.executable, "-m", "app.whisper_cpp", db.DB_PATH, str(rec_id), model_file]
            with subprocess.Popen(command, cwd=config.BASE_DIR) as proc:
                while proc.poll() is None:
                    if stopping.wait(0.25) or executor.recording_requested.is_set():
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        raise InterruptedError
                if proc.returncode:
                    raise RuntimeError(f"量化转写进程异常退出（{proc.returncode}），请检查内存和模型后重试")
        else:
            result = recognize(job["file_path"], stopping)
            db.set_transcript_result(rec_id, "completed", json.dumps(result, ensure_ascii=False))
    except InterruptedError:
        db.set_transcript_result(rec_id, "queued")
    except Exception as exc:
        logging.exception("录音 %s 转写失败", rec_id)
        db.set_transcript_result(rec_id, "failed", error=str(exc))


def run(stopping):
    model_file = config.whisper_cpp_model()
    while not stopping.is_set():
        job = None
        if model_file:
            if executor.low_memory_slot.acquire(timeout=0.5):
                try:
                    if not executor.recording_requested.is_set():
                        job = db.claim_transcript()
                        if job:
                            process(job, model_file, stopping)
                finally:
                    executor.low_memory_slot.release()
        else:
            job = db.claim_transcript()
            if job:
                process(job, model_file, stopping)
        if not job:
            stopping.wait(1)


def start():
    db.recover_transcripts()
    stopping = threading.Event()
    thread = threading.Thread(target=run, args=(stopping,), name="whisper", daemon=True)
    thread.start()
    return stopping, thread
