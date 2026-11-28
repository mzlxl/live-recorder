"""以临时 SQLite 库验证录音完成、转写队列和时间戳。"""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db, transcription


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.addCleanup(setattr, db, "DB_PATH", db.DB_PATH)
        db.DB_PATH = str(Path(directory.name) / "recorder.db")
        db.init_db()
        self.task = db.create_task("测试", "https://www.douyin.com/user/example")
        self.rec = db.create_recording(self.task)

    def test_finalize_and_resume(self):
        db.finish_recording(self.rec, "sample.m4a", 10, 40)
        db.finish_recording(self.rec, "sample.m4a", 10, 40)
        self.assertEqual(self.rec, db.claim_transcript()["recording_id"])
        self.assertIsNone(db.claim_transcript())
        self.assertTrue(db.checkpoint(self.rec, 5, "[[]]"))
        db.init_db()
        db.recover_transcripts()
        resumed = db.claim_transcript()
        self.assertEqual((resumed["processed"], resumed["paragraphs"]), (5, "[[]]"))
        db.set_transcript_result(self.rec, "completed", "[]")
        db.request_transcript(self.rec)
        self.assertIsNone(db.claim_transcript())

    def test_failed_retry_and_delete(self):
        db.finish_recording(self.rec, "", 0, 0, "failed", "设备缺失")
        self.assertIsNone(db.claim_transcript())
        db.finish_recording(self.rec, "missing.m4a", 1, 2)
        stopping = threading.Event()
        job = db.claim_transcript()
        with patch.dict("os.environ", {"RECORDER_WHISPER_CPP_MODEL": ""}), \
             patch.object(db, "claim_transcript", side_effect=[job, None]), \
             patch.object(stopping, "wait", side_effect=lambda _: stopping.set()), \
             self.assertLogs(level="ERROR"):
            transcription.run(stopping)
        self.assertEqual(db.get_transcript(self.rec)["status"], "failed")
        self.assertIn("缺失", db.get_transcript(self.rec)["error"])
        db.request_transcript(self.rec)
        self.assertEqual(self.rec, db.claim_transcript()["recording_id"])
        db.delete_recording(self.rec)
        self.assertFalse(db.checkpoint(self.rec, 1, "[]"))
        self.assertEqual(db.get_transcript(self.rec)["status"], "unavailable")

    def test_old_recording_and_empty_result(self):
        with db._conn() as c:
            c.execute("UPDATE recordings SET status='completed',file_size=4 WHERE id=?", (self.rec,))
        db.init_db()
        db.request_transcript(self.rec)
        self.assertEqual(db.claim_transcript()["recording_id"], self.rec)
        db.set_transcript_result(self.rec, "completed", "[]")
        self.assertEqual(db.get_transcript(self.rec)["paragraphs"], "[]")

    def test_sentence_times_and_paragraphs(self):
        parts = transcription.paragraphs([{"words":[
            {"word":"开始。","start":0,"end":1}, {"word":"继续","start":1,"end":2},
            {"word":"。","start":2,"end":2.1}, {"word":"下一段","start":6,"end":8}]}])
        self.assertEqual([len(group) for group in parts], [2, 1])
        self.assertEqual(parts[1][0], {"start":6, "end":8, "text":"下一段"})


if __name__ == "__main__":
    unittest.main()
