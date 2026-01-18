"""
Whisper 轉錄模組
"""
import os
import subprocess
import tempfile
from typing import Tuple, List, Dict
from faster_whisper import WhisperModel

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")


class WhisperTranscriber:
    """Whisper 轉錄器"""

    def __init__(self):
        """初始化 Whisper 模型"""
        print(f"載入 Whisper 模型: {WHISPER_MODEL}")
        print(f"  Device: {WHISPER_DEVICE}")
        print(f"  Compute Type: {WHISPER_COMPUTE_TYPE}")

        self.model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE
        )

    def _convert_to_wav(self, filepath: str) -> str:
        """
        將音檔轉換為 WAV 格式（解決某些格式的相容性問題）

        Args:
            filepath: 原始音檔路徑

        Returns:
            轉換後的 WAV 檔案路徑（如果轉換失敗則返回原路徑）
        """
        # 建立臨時 WAV 檔案
        wav_path = filepath + ".converted.wav"

        try:
            print(f"轉換音檔格式: {filepath} -> WAV")
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", filepath,
                    "-ar", "16000",  # Whisper 偏好 16kHz
                    "-ac", "1",      # 單聲道
                    "-c:a", "pcm_s16le",
                    wav_path
                ],
                capture_output=True,
                text=True
            )

            if result.returncode == 0 and os.path.exists(wav_path):
                print("音檔轉換成功")
                return wav_path
            else:
                print(f"音檔轉換失敗: {result.stderr}")
                return filepath
        except Exception as e:
            print(f"音檔轉換例外: {e}")
            return filepath

    def transcribe(self, filepath: str) -> Tuple[str, str, List[Dict]]:
        """
        轉錄音檔

        Args:
            filepath: 音檔路徑

        Returns:
            Tuple[完整轉錄文字, 語言, 帶時間戳的段落]
        """
        print(f"開始轉錄: {filepath}")

        # 先轉換為 WAV 格式，確保相容性
        converted_path = self._convert_to_wav(filepath)
        use_converted = converted_path != filepath

        try:
            # 第一次嘗試：使用 VAD 過濾
            segments, info = self.model.transcribe(
                converted_path,
                beam_size=5,
                language=None,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                ),
            )

            transcript_parts = []
            segments_with_timestamps = []

            for segment in segments:
                text = segment.text.strip()
                if text:
                    transcript_parts.append(text)
                    segments_with_timestamps.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": text
                    })

            # 如果 VAD 過濾後沒有結果，關閉 VAD 重試
            if len(segments_with_timestamps) == 0:
                print("VAD 過濾無結果，關閉 VAD 重試...")
                segments, info = self.model.transcribe(
                    converted_path,
                    beam_size=5,
                    language=None,
                    vad_filter=False,
                )

                for segment in segments:
                    text = segment.text.strip()
                    if text:
                        transcript_parts.append(text)
                        segments_with_timestamps.append({
                            "start": segment.start,
                            "end": segment.end,
                            "text": text
                        })

            full_transcript = "\n".join(transcript_parts)
            language = info.language

            print(f"轉錄完成，語言: {language}，段落數: {len(segments_with_timestamps)}")

            return full_transcript, language, segments_with_timestamps

        finally:
            # 清理轉換後的臨時檔案
            if use_converted and os.path.exists(converted_path):
                try:
                    os.remove(converted_path)
                    print(f"已清理臨時檔案: {converted_path}")
                except Exception as e:
                    print(f"清理臨時檔案失敗: {e}")

    def format_with_timestamps(self, segments: List[Dict], include_speaker: bool = False) -> str:
        """
        格式化帶時間戳的轉錄

        Args:
            segments: 段落列表
            include_speaker: 是否包含說話者資訊

        Returns:
            格式化文字
        """
        lines = []
        for seg in segments:
            start = self._format_time(seg["start"])
            end = self._format_time(seg["end"])
            if include_speaker and "speaker" in seg:
                lines.append(f"[{start} --> {end}] [{seg['speaker']}] {seg['text']}")
            else:
                lines.append(f"[{start} --> {end}] {seg['text']}")
        return "\n".join(lines)

    def _format_time(self, seconds: float) -> str:
        """格式化秒數為時間字串"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
