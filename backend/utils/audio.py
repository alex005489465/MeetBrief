import os
import subprocess
from pathlib import Path
from pydub import AudioSegment

from backend.config import ALLOWED_VIDEO_EXTENSIONS


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


def is_video_format(filename: str) -> bool:
    """
    判斷是否為影片格式

    Args:
        filename: 檔案名稱

    Returns:
        是否為影片格式
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext in ALLOWED_VIDEO_EXTENSIONS


def extract_audio_from_video(video_path: str, output_path: str = None) -> str:
    """
    使用 FFmpeg 從影片提取音軌

    Args:
        video_path: 影片檔案路徑
        output_path: 輸出音檔路徑（若未指定，使用相同路徑但副檔名改為 .mp3）

    Returns:
        提取後的音檔路徑

    Raises:
        RuntimeError: FFmpeg 執行失敗
    """
    video_path = Path(video_path)

    if output_path is None:
        output_path = video_path.with_suffix(".mp3")
    else:
        output_path = Path(output_path)

    # FFmpeg 指令：提取音軌並轉換為 16kHz 單聲道 MP3
    cmd = [
        "ffmpeg",
        "-y",               # 覆蓋輸出檔案
        "-i", str(video_path),  # 輸入檔案
        "-vn",              # 不要影像
        "-acodec", "libmp3lame",  # 輸出為 MP3
        "-ar", "16000",     # 16kHz（Whisper 偏好）
        "-ac", "1",         # 單聲道
        str(output_path)
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"[FFmpeg] 成功從 {video_path.name} 提取音軌")
        return str(output_path)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        raise RuntimeError(f"FFmpeg 提取音軌失敗: {error_msg}")
    except FileNotFoundError:
        raise RuntimeError("找不到 FFmpeg，請確認已安裝 FFmpeg 並加入系統 PATH")
