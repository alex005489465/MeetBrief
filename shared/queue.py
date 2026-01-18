"""
Redis 任務佇列模組
用於 API 服務和 Worker 之間的通訊
"""
import json
import os
from typing import Optional, Dict, Any
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# 佇列名稱
TASK_QUEUE = "meetbrief:tasks"
DIARIZE_QUEUE = "meetbrief:diarize"
RESULT_PREFIX = "meetbrief:result:"
STATUS_PREFIX = "meetbrief:status:"


def get_redis_client() -> redis.Redis:
    """取得 Redis 客戶端"""
    return redis.from_url(REDIS_URL, decode_responses=True)


def enqueue_task(
    task_type: str,
    meeting_id: int,
    mode: str = "transcribe_and_summarize",
    diarization: bool = False,
    num_speakers: int = None,
    data: Optional[Dict] = None
) -> str:
    """
    將任務加入佇列

    Args:
        task_type: 任務類型 (transcribe, summarize)
        meeting_id: 會議 ID
        mode: 處理模式 (transcribe_only, transcribe_and_summarize)
        diarization: 是否啟用說話者分離
        num_speakers: 說話者數量（None 為自動偵測）
        data: 額外資料

    Returns:
        任務 ID
    """
    client = get_redis_client()

    task = {
        "type": task_type,
        "meeting_id": meeting_id,
        "mode": mode,
        "diarization": diarization,
        "num_speakers": num_speakers,
        "data": data or {}
    }

    # 推送到佇列
    client.rpush(TASK_QUEUE, json.dumps(task))

    # 設定初始狀態
    status_key = f"{STATUS_PREFIX}{meeting_id}"
    client.hset(status_key, mapping={
        "status": "queued",
        "task_type": task_type
    })

    return f"{task_type}:{meeting_id}"


def dequeue_task(timeout: int = 0) -> Optional[Dict[str, Any]]:
    """
    從佇列取出任務

    Args:
        timeout: 等待超時秒數 (0 = 阻塞等待)

    Returns:
        任務資料或 None
    """
    client = get_redis_client()

    result = client.blpop(TASK_QUEUE, timeout=timeout)
    if result:
        _, task_json = result
        return json.loads(task_json)
    return None


def update_task_status(meeting_id: int, status: str, message: str = ""):
    """
    更新任務狀態

    Args:
        meeting_id: 會議 ID
        status: 狀態
        message: 訊息
    """
    client = get_redis_client()
    status_key = f"{STATUS_PREFIX}{meeting_id}"
    client.hset(status_key, mapping={
        "status": status,
        "message": message
    })
    # 設定過期時間 (1小時)
    client.expire(status_key, 3600)


def get_task_status(meeting_id: int) -> Optional[Dict[str, str]]:
    """
    取得任務狀態

    Args:
        meeting_id: 會議 ID

    Returns:
        狀態資料或 None
    """
    client = get_redis_client()
    status_key = f"{STATUS_PREFIX}{meeting_id}"
    return client.hgetall(status_key) or None


def enqueue_diarize_task(meeting_id: int, filepath: str, num_speakers: int = None) -> str:
    """
    將說話者分離任務加入佇列

    Args:
        meeting_id: 會議 ID
        filepath: 音檔路徑
        num_speakers: 說話者數量（None 為自動偵測）

    Returns:
        任務 ID
    """
    client = get_redis_client()

    task = {
        "meeting_id": meeting_id,
        "filepath": filepath,
        "num_speakers": num_speakers
    }

    # 推送到說話者分離佇列
    client.rpush(DIARIZE_QUEUE, json.dumps(task))

    return f"diarize:{meeting_id}"


def save_worker_result(meeting_id: int, worker_type: str, status: str, filepath: str = None, error: str = None):
    """
    儲存 worker 處理結果狀態到 Redis

    Args:
        meeting_id: 會議 ID
        worker_type: worker 類型 (transcribe, diarize)
        status: 狀態 (completed, error)
        filepath: 結果檔案路徑
        error: 錯誤訊息
    """
    client = get_redis_client()
    result_key = f"{RESULT_PREFIX}{meeting_id}:{worker_type}"

    result = {
        "status": status,
        "filepath": filepath,
        "error": error
    }

    client.set(result_key, json.dumps(result))
    # 設定過期時間 (1小時)
    client.expire(result_key, 3600)


def get_worker_result(meeting_id: int, worker_type: str) -> Optional[Dict]:
    """
    取得 worker 處理結果狀態

    Args:
        meeting_id: 會議 ID
        worker_type: worker 類型 (transcribe, diarize)

    Returns:
        結果狀態或 None
    """
    client = get_redis_client()
    result_key = f"{RESULT_PREFIX}{meeting_id}:{worker_type}"
    result = client.get(result_key)
    if result:
        return json.loads(result)
    return None


def clear_worker_result(meeting_id: int, worker_type: str):
    """
    清除 worker 處理結果

    Args:
        meeting_id: 會議 ID
        worker_type: worker 類型 (transcribe, diarize)
    """
    client = get_redis_client()
    result_key = f"{RESULT_PREFIX}{meeting_id}:{worker_type}"
    client.delete(result_key)
