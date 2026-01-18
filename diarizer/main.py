"""
Speaker Diarizer Worker - 獨立的說話者分離服務
從 Redis 佇列取得任務並處理
只負責說話者分離，結果存檔案，由 API 協調合併
"""
import os
import sys
import time
import signal
import json
from pathlib import Path

# 設定路徑以便引用 shared 模組
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 結果檔案儲存目錄
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = DATA_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

from dotenv import load_dotenv
load_dotenv()

from shared.queue import get_redis_client, save_worker_result

# 佇列名稱
DIARIZE_QUEUE = "meetbrief:diarize"

# 全域變數
running = True
diarizer = None


def signal_handler(signum, frame):
    """處理終止信號"""
    global running
    print("\n收到終止信號，正在關閉 Diarizer Worker...")
    running = False


def dequeue_diarize_task(timeout: int = 0):
    """
    從說話者分離佇列取出任務

    Args:
        timeout: 等待超時秒數 (0 = 阻塞等待)

    Returns:
        任務資料或 None
    """
    client = get_redis_client()
    result = client.blpop(DIARIZE_QUEUE, timeout=timeout)
    if result:
        _, task_json = result
        return json.loads(task_json)
    return None


def process_task(task: dict):
    """
    處理單一任務

    Args:
        task: 任務資料
    """
    global diarizer

    meeting_id = task.get("meeting_id")
    filepath = task.get("filepath")
    num_speakers = task.get("num_speakers")

    print(f"處理說話者分離任務: 會議 ID {meeting_id}, 說話者數量: {num_speakers or '自動偵測'}")

    try:
        # 確保 diarizer 已初始化
        if diarizer is None:
            print("正在載入 NeMo Diarizer 模型...")
            from diarizer.nemo_diarizer import NemoDiarizer
            diarizer = NemoDiarizer()
            print("NeMo Diarizer 模型載入完成")

        # 執行說話者分離
        speaker_segments = diarizer.diarize(filepath, num_speakers=num_speakers)

        # 儲存結果到檔案
        result_filepath = RESULTS_DIR / f"{meeting_id}_diarize.json"
        result_data = {
            "meeting_id": meeting_id,
            "speaker_segments": speaker_segments
        }

        with open(result_filepath, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        print(f"說話者分離結果已存檔: {result_filepath}")

        # 更新 Redis 狀態
        save_worker_result(
            meeting_id,
            "diarize",
            "completed",
            filepath=str(result_filepath)
        )

        print(f"會議 {meeting_id} 說話者分離完成，共 {len(speaker_segments)} 個區段")

    except Exception as e:
        print(f"說話者分離失敗: {e}")
        import traceback
        traceback.print_exc()
        save_worker_result(meeting_id, "diarize", "error", error=str(e))


def main():
    """Worker 主迴圈"""
    global running

    # 註冊信號處理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 50)
    print("MeetBrief Speaker Diarizer Worker 啟動")
    print("使用 NeMo Toolkit + PyTorch 2.5")
    print("=" * 50)
    print("等待任務中...")

    while running:
        try:
            # 從佇列取得任務（阻塞等待 5 秒）
            task = dequeue_diarize_task(timeout=5)

            if task:
                process_task(task)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Worker 錯誤: {e}")
            time.sleep(1)

    print("Diarizer Worker 已關閉")


if __name__ == "__main__":
    main()
