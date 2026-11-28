"""按块解码音频，单实例双线程 CPU 推理。仅启用轻量模式时加载依赖。"""
import json
import logging
import subprocess
import sys
from pathlib import Path

from app.recorder import detect_ffmpeg

SAMPLE_RATE = 16000
BLOCK_SECONDS = 120


def decode(path, model_file, processed):
    import numpy as np
    from pywhispercpp.model import Model

    if not Path(model_file).is_file():
        raise ValueError("找不到量化模型，请检查 RECORDER_WHISPER_CPP_MODEL")
    if not Path(path or "").is_file():
        raise ValueError("录音文件缺失，请还原文件后重试")
    model = Model(str(Path(model_file).resolve()), n_threads=2, language="zh",
                  initial_prompt="以下是用简体中文记录的直播对话。", token_timestamps=True, max_len=48,
                  context_params={"use_gpu": False}, print_progress=False,
                  print_realtime=False, no_context=True)
    cmd = [detect_ffmpeg() or "ffmpeg", "-v", "error", "-nostdin", "-threads", "1",
           "-ss", str(processed), "-i", path, "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
           "-f", "s16le", "pipe:1"]
    block = SAMPLE_RATE * BLOCK_SECONDS * 2
    carry = b""
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        try:
            while True:
                data = carry + proc.stdout.read(block - len(carry))
                if not data:
                    break
                samples = np.frombuffer(data, dtype="<i2")
                cut = len(samples)
                if len(data) == block:
                    # 在块尾两秒内选择能量最低的 20ms 间隔，尽量在停顿处切分。
                    tail = samples[-2 * SAMPLE_RATE:].astype(np.float32).reshape(-1, 320)
                    cut -= len(tail.ravel()) - int(np.square(tail).mean(axis=1).argmin()) * 320
                carry = data[cut * 2:]
                pcm = samples[:cut].astype(np.float32) / 32768
                duration = cut / SAMPLE_RATE
                segments = []
                if np.max(np.abs(pcm)) > 1 / 32768:
                    for s in model.transcribe(pcm):
                        segments.append({"start": processed + min(s.t0 / 100, duration),
                                         "end": processed + min(s.t1 / 100, duration),
                                         "text": s.text})
                processed = round(processed + duration, 6)
                yield segments, processed
            if proc.wait():
                raise ValueError("音频解码失败，请检查文件是否完整")
        finally:
            if proc.poll() is None:
                proc.kill()

def recognize(db_path, rec_id, model_file):
    from app import db
    from app.transcription import paragraphs

    db.DB_PATH = db_path
    record = db.get_recording(rec_id)
    if not record:
        return
    state = db.get_transcript(rec_id)
    result = json.loads(state["paragraphs"] or "[]")
    try:
        for segments, processed in decode(record["file_path"], model_file, state["processed"]):
            result.extend(paragraphs(segments))
            if not db.checkpoint(rec_id, processed, json.dumps(result, ensure_ascii=False)):
                return
        db.set_transcript_result(rec_id, "completed", json.dumps(result, ensure_ascii=False))
    except ModuleNotFoundError as exc:
        db.set_transcript_result(rec_id, "failed", error=f"轻量转写缺少 {exc.name}，请安装 pywhispercpp 后重试")
    except Exception as exc:
        logging.exception("录音 %s 轻量转写失败", rec_id)
        db.set_transcript_result(rec_id, "failed", error=str(exc))


if __name__ == "__main__":
    recognize(sys.argv[1], int(sys.argv[2]), sys.argv[3])
