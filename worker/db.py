"""
Worker 資料庫存取模組
只讀取會議資訊（取得音檔路徑）
"""
import sqlite3
from typing import Optional, Dict, Any
from pathlib import Path

# 資料庫路徑
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATABASE_PATH = DATA_DIR / "meetbrief.db"


def get_connection():
    """取得資料庫連線"""
    return sqlite3.connect(str(DATABASE_PATH))


def get_meeting(meeting_id: int) -> Optional[Dict[str, Any]]:
    """
    取得會議資料

    Args:
        meeting_id: 會議 ID

    Returns:
        會議資料字典或 None
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, filepath FROM meetings WHERE id = ?",
        (meeting_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None
