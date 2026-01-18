"""
任務協調器 - 輪詢 worker 結果，合併、分析並儲存
"""
import os
import json
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

# 結果檔案目錄
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
RESULTS_DIR = DATA_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

from shared.queue import get_worker_result, clear_worker_result, update_task_status
from .merger import merge_transcription_with_speakers


class TaskCoordinator:
    """任務協調器"""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.pending_tasks = {}

    def add_task(self, meeting_id: int, mode: str, enable_diarization: bool):
        """新增待協調的任務"""
        self.pending_tasks[meeting_id] = {
            "mode": mode,
            "enable_diarization": enable_diarization,
            "started_at": datetime.now()
        }
        print(f"[Coordinator] 新增任務: 會議 {meeting_id}, 模式: {mode}, 說話者分離: {enable_diarization}")

    async def check_and_process(self, meeting_id: int) -> bool:
        """檢查任務狀態並處理"""
        if meeting_id not in self.pending_tasks:
            return False

        task_info = self.pending_tasks[meeting_id]
        enable_diarization = task_info["enable_diarization"]

        # 檢查轉錄結果
        transcribe_result = get_worker_result(meeting_id, "transcribe")
        if transcribe_result is None:
            return False

        if transcribe_result.get("status") == "error":
            await self._handle_error(meeting_id, "transcribe", transcribe_result.get("error"))
            return True

        # 如果需要說話者分離，檢查 diarize 結果
        if enable_diarization:
            diarize_result = get_worker_result(meeting_id, "diarize")
            if diarize_result is None:
                return False

            if diarize_result.get("status") == "error":
                print(f"[Coordinator] 會議 {meeting_id} 說話者分離失敗，使用純轉錄結果")
                await self._process_transcribe_only(meeting_id, transcribe_result, task_info)
            else:
                await self._process_with_diarization(meeting_id, transcribe_result, diarize_result, task_info)
        else:
            await self._process_transcribe_only(meeting_id, transcribe_result, task_info)

        return True

    async def _process_transcribe_only(self, meeting_id: int, transcribe_result: dict, task_info: dict):
        """處理純轉錄結果"""
        try:
            filepath = transcribe_result.get("filepath")
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            segments = data.get("segments", [])
            language = data.get("language")
            formatted_transcript = self._format_transcript(segments, include_speaker=False)
            await self._save_and_analyze(meeting_id, formatted_transcript, segments, language, task_info["mode"])
            self._cleanup(meeting_id)
        except Exception as e:
            print(f"[Coordinator] 處理轉錄結果失敗: {e}")
            import traceback
            traceback.print_exc()
            await self._handle_error(meeting_id, "coordinator", str(e))

    async def _process_with_diarization(self, meeting_id: int, transcribe_result: dict, diarize_result: dict, task_info: dict):
        """處理轉錄+說話者分離結果"""
        try:
            with open(transcribe_result.get("filepath"), "r", encoding="utf-8") as f:
                transcribe_data = json.load(f)
            with open(diarize_result.get("filepath"), "r", encoding="utf-8") as f:
                diarize_data = json.load(f)

            segments = transcribe_data.get("segments", [])
            language = transcribe_data.get("language")
            speaker_segments = diarize_data.get("speaker_segments", [])

            if speaker_segments:
                segments = merge_transcription_with_speakers(segments, speaker_segments)

            # 保存合併結果
            merged_data = {
                "meeting_id": meeting_id,
                "language": language,
                "segments": segments,
                "speaker_count": len(set(s.get("speaker", "") for s in segments if s.get("speaker")))
            }
            merged_path = RESULTS_DIR / f"{meeting_id}_merged.json"
            with open(merged_path, "w", encoding="utf-8") as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)
            print(f"[Coordinator] 合併結果已儲存: {merged_path}")

            formatted_transcript = self._format_transcript(segments, include_speaker=bool(speaker_segments))
            await self._save_and_analyze(meeting_id, formatted_transcript, segments, language, task_info["mode"])
            self._cleanup(meeting_id)
        except Exception as e:
            print(f"[Coordinator] 處理合併結果失敗: {e}")
            import traceback
            traceback.print_exc()
            await self._handle_error(meeting_id, "coordinator", str(e))

    def _format_transcript(self, segments: list, include_speaker: bool = False) -> str:
        """格式化轉錄文字"""
        lines = []
        for seg in segments:
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            text = seg.get("text", "")
            start_str = self._format_time(start)
            end_str = self._format_time(end)

            if include_speaker and "speaker" in seg:
                speaker = seg["speaker"]
                lines.append(f"[{start_str} --> {end_str}] [{speaker}] {text}")
            else:
                lines.append(f"[{start_str} --> {end_str}] {text}")

        return "\n".join(lines)

    def _format_time(self, seconds: float) -> str:
        """格式化時間"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    async def _save_and_analyze(self, meeting_id: int, transcript: str, segments: list, language: str, mode: str):
        """儲存到資料庫並執行分析"""
        from backend.models import Meeting

        db = self.db_session_factory()
        try:
            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
            if meeting:
                meeting.transcript = transcript
                meeting.language = language

                if mode == "transcribe_only":
                    meeting.status = "completed"
                    update_task_status(meeting_id, "completed", "轉錄完成")
                else:
                    meeting.status = "summarizing"
                    update_task_status(meeting_id, "summarizing", "正在分析會議內容...")

                db.commit()
                print(f"[Coordinator] 會議 {meeting_id} 已儲存到資料庫")
                self._save_to_file(meeting)

                # 如果需要摘要，在背景執行分析
                if mode != "transcribe_only":
                    asyncio.create_task(self._run_analysis(meeting_id, transcript, segments))
        finally:
            db.close()

        if meeting_id in self.pending_tasks:
            del self.pending_tasks[meeting_id]

    async def _run_analysis(self, meeting_id: int, transcript: str, segments: list):
        """執行分析管線（在背景執行）"""
        from backend.models import Meeting

        print(f"[Coordinator] 會議 {meeting_id} 開始分析...")

        try:
            # 從帶時間戳的轉錄中提取純文字
            plain_text = self._extract_plain_text(transcript)

            # 在執行緒池中執行同步的分析管線
            results = await asyncio.to_thread(self._execute_pipeline, plain_text, segments)

            # 取得摘要內容
            summary_result = results.get("summary", {})
            summary = summary_result.get("content", "")

            if not summary:
                raise ValueError("摘要生成失敗：無內容")

            # 更新資料庫
            db = self.db_session_factory()
            try:
                meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
                if meeting:
                    meeting.summary = summary
                    meeting.status = "completed"
                    meeting.error_message = None
                    db.commit()
            finally:
                db.close()

            update_task_status(meeting_id, "completed", "分析完成")

            # 保存結果到檔案
            self._save_analysis_results(meeting_id, results)

            print(f"[Coordinator] 會議 {meeting_id} 分析完成")

        except Exception as e:
            print(f"[Coordinator] 會議 {meeting_id} 分析失敗: {e}")
            import traceback
            traceback.print_exc()

            # 更新錯誤狀態
            db = self.db_session_factory()
            try:
                meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
                if meeting:
                    meeting.status = "completed"
                    meeting.error_message = f"摘要生成失敗: {str(e)}"
                    db.commit()
            finally:
                db.close()

            update_task_status(meeting_id, "completed", f"摘要生成失敗: {str(e)}")

    def _execute_pipeline(self, transcript: str, segments: list) -> dict:
        """執行分析管線（同步）"""
        from backend.modules.analysis import create_full_pipeline

        pipeline = create_full_pipeline()
        return pipeline.run(transcript, segments)

    def _extract_plain_text(self, transcript: str) -> str:
        """從帶時間戳的轉錄中提取純文字"""
        lines = transcript.split("\n")
        plain_parts = []
        for line in lines:
            if "]" in line:
                # 處理 [時間] [說話者] 文字 或 [時間] 文字
                parts = line.split("]")
                text = parts[-1].strip() if parts else ""
                if text:
                    plain_parts.append(text)
        return "\n".join(plain_parts)

    def _save_analysis_results(self, meeting_id: int, results: dict):
        """儲存完整分析結果"""
        # 儲存完整分析結果 JSON
        analysis_path = RESULTS_DIR / f"{meeting_id}_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[Coordinator] 完整分析結果已儲存: {analysis_path}")

        # 儲存摘要 Markdown
        summary_content = results.get("summary", {}).get("content", "")
        if summary_content:
            summary_path = RESULTS_DIR / f"{meeting_id}_summary.md"
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary_content)
            print(f"[Coordinator] 摘要已儲存: {summary_path}")

    def _save_to_file(self, meeting):
        """儲存轉錄到檔案"""
        title = meeting.title or f"meeting_{meeting.id}"
        meeting_id = meeting.id

        transcript = meeting.transcript
        if transcript:
            transcript_file = RESULTS_DIR / f"{meeting_id}_transcript.txt"
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(f"會議 ID: {meeting_id}\n")
                f.write(f"標題: {title}\n")
                f.write(f"語言: {meeting.language or '未知'}\n")
                f.write(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
                f.write(transcript)
            print(f"[Coordinator] 轉錄已儲存: {transcript_file}")

    async def _handle_error(self, meeting_id: int, source: str, error: str):
        """處理錯誤"""
        from backend.models import Meeting

        db = self.db_session_factory()
        try:
            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
            if meeting:
                meeting.status = "error"
                meeting.error_message = f"{source}: {error}"
                db.commit()
        finally:
            db.close()

        update_task_status(meeting_id, "error", error)
        self._cleanup(meeting_id)

        if meeting_id in self.pending_tasks:
            del self.pending_tasks[meeting_id]

    def _cleanup(self, meeting_id: int):
        """清理 Redis 狀態（保留檔案）"""
        clear_worker_result(meeting_id, "transcribe")
        clear_worker_result(meeting_id, "diarize")
        print(f"[Coordinator] 已清理 Redis 狀態: 會議 {meeting_id}")


# 全域協調器實例
coordinator: Optional[TaskCoordinator] = None


def get_coordinator() -> TaskCoordinator:
    """取得協調器實例"""
    global coordinator
    if coordinator is None:
        from backend.database import SessionLocal
        coordinator = TaskCoordinator(SessionLocal)
    return coordinator


async def coordinator_loop():
    """協調器主迴圈"""
    print("[Coordinator] 協調器啟動")
    coord = get_coordinator()

    while True:
        try:
            for meeting_id in list(coord.pending_tasks.keys()):
                await coord.check_and_process(meeting_id)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"[Coordinator] 錯誤: {e}")
            await asyncio.sleep(5)
