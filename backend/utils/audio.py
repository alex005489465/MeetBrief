import os
from pathlib import Path
from pydub import AudioSegment


def get_audio_duration(filepath: str) -> float:
    """
    取得音檔長度（秒）

    Args:
        filepath: 音檔路徑

    Returns:
        音檔長度（秒）
    """
    try:
        audio = AudioSegment.from_file(filepath)
        return len(audio) / 1000.0
    except Exception as e:
        print(f"無法取得音檔長度: {e}")
        return 0.0


def is_valid_audio_format(filename: str, allowed_extensions: list) -> bool:
    """
    檢查檔案格式是否有效

    Args:
        filename: 檔案名稱
        allowed_extensions: 允許的副檔名列表

    Returns:
        是否為有效格式
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext in allowed_extensions


def get_safe_filename(filename: str) -> str:
    """
    取得安全的檔案名稱

    Args:
        filename: 原始檔案名稱

    Returns:
        安全的檔案名稱
    """
    # 移除路徑分隔符號和特殊字元
    safe_name = os.path.basename(filename)
    # 替換空格為底線
    safe_name = safe_name.replace(" ", "_")
    return safe_name
