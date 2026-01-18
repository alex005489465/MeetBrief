"""
Whisper Worker - 語音轉錄服務
從 Redis 佇列取得任務，執行轉錄，結果存檔案
"""
import os
import sys
import time
import json
import signal
from pathlib import Path

# 設定路徑以便引用 shared 模組
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 結果檔案儲存目錄
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = DATA_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

from dotenv import load_dotenv
load_dotenv()

from shared.queue import dequeue_task, update_task_status, save_worker_result
from worker.transcriber import WhisperTranscriber
from worker.db import get_meeting

# 全域變數
running = True
transcriber = None


def signal_handler(signum, frame):
    """處理終止信號"""
    global running
    print("\n收到終止信號，正在關閉 Worker...")
    running = False


def process_task(task: dict):
    """處理單一任務"""
    task_type = task.get("type")
    meeting_id = task.get("meeting_id")

    print(f"處理任務: {task_type} (會議 ID: {meeting_id})")

    if task_type != "transcribe":
        print(f"[Worker] 忽略非轉錄任務: {task_type}")
        return

    try:
        meeting = get_meeting(meeting_id)
        if not meeting:
            print(f"找不到會議 ID: {meeting_id}")
            return

        process_transcribe(meeting)

    except Exception as e:
        print(f"任務處理失敗: {e}")
        import traceback
        traceback.print_exc()
        update_task_status(meeting_id, "error", str(e))
        save_worker_result(meeting_id, "transcribe", "error", error=str(e))


def process_transcribe(meeting: dict):
    """
    處理轉錄任務

    Args:
        meeting: 會議資料
    """
    global transcriber

    meeting_id = meeting["id"]
    filepath = meeting["filepath"]

    # 更新狀態
    update_task_status(meeting_id, "transcribing", "正在轉錄...")

    # 確保轉錄器已初始化
    if transcriber is None:
        print("正在載入 Whisper 模型...")
        transcriber = WhisperTranscriber()
        print("Whisper 模型載入完成")

    # 先轉換音檔格式
    wav_path = transcriber._convert_to_wav(filepath)
    use_converted = wav_path != filepath

    try:
        # 執行轉錄
        transcript, language, segments = _transcribe(wav_path)

        # 儲存結果到檔案
        result_filepath = RESULTS_DIR / f"{meeting_id}_transcribe.json"
        result_data = {
            "meeting_id": meeting_id,
            "transcript": transcript,
            "language": language,
            "segments": segments
        }

        with open(result_filepath, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        print(f"轉錄結果已存檔: {result_filepath}")

        # 更新 Redis 狀態
        save_worker_result(
            meeting_id,
            "transcribe",
            "completed",
            filepath=str(result_filepath)
        )

        update_task_status(meeting_id, "transcribe_done", "轉錄完成，等待處理")
        print(f"會議 {meeting_id} 轉錄完成")

    except Exception as e:
        print(f"轉錄失敗: {e}")
        save_worker_result(meeting_id, "transcribe", "error", error=str(e))
        raise

    finally:
        # 清理臨時檔案
        if use_converted and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
                print(f"已清理臨時檔案: {wav_path}")
            except Exception as e:
                print(f"清理臨時檔案失敗: {e}")


def _transcribe(wav_path: str):
    """
    執行轉錄

    Args:
        wav_path: WAV 檔案路徑

    Returns:
        (transcript, language, segments)
    """
    global transcriber

    segments_iter, info = transcriber.model.transcribe(
        wav_path,
        beam_size=5,
        language=None,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    transcript_parts = []
    segments = []

    for segment in segments_iter:
        text = segment.text.strip()
        if text:
            transcript_parts.append(text)
            segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": text
            })

    # VAD fallback
    if len(segments) == 0:
        print("VAD 過濾無結果，關閉 VAD 重試...")
        segments_iter, info = transcriber.model.transcribe(
            wav_path,
            beam_size=5,
            language=None,
            vad_filter=False,
        )

        for segment in segments_iter:
            text = segment.text.strip()
            if text:
                transcript_parts.append(text)
                segments.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": text
                })

    transcript = "\n".join(transcript_parts)
    language = info.language
    print(f"轉錄完成，語言: {language}，段落數: {len(segments)}")

    return transcript, language, segments


def main():
    """Worker 主迴圈"""
    global running

    # 註冊信號處理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 50)
    print("MeetBrief Whisper Worker 啟動")
    print("=" * 50)
    print("等待轉錄任務...")

    while running:
        try:
            # 從佇列取得任務（阻塞等待 5 秒）
            task = dequeue_task(timeout=5)

            if task:
                process_task(task)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Worker 錯誤: {e}")
            time.sleep(1)

    print("Worker 已關閉")


if __name__ == "__main__":
    main()
