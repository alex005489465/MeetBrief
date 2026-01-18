"""
轉錄與說話者資訊合併邏輯
"""
from typing import List, Dict
from collections import defaultdict


def merge_transcription_with_speakers(
    transcript_segments: List[Dict],
    speaker_segments: List[Dict]
) -> List[Dict]:
    """
    合併轉錄結果與說話者資訊

    使用重疊時間比例算法：計算每個說話者與轉錄段落的重疊時間，
    選擇重疊時間最長的說話者。這樣可以正確處理一個轉錄段落
    包含多個說話者的情況。

    Args:
        transcript_segments: 轉錄段落 [{"start", "end", "text"}, ...]
        speaker_segments: 說話者段落 [{"start", "end", "speaker"}, ...]

    Returns:
        合併後的段落 [{"start", "end", "text", "speaker"}, ...]
    """
    result = []
    last_known_speaker = None

    for t_seg in transcript_segments:
        t_start = t_seg["start"]
        t_end = t_seg["end"]

        # 計算每個說話者與此轉錄段落的重疊時間
        speaker_overlap = defaultdict(float)

        for s_seg in speaker_segments:
            s_start = s_seg["start"]
            s_end = s_seg["end"]

            # 計算重疊區間
            overlap_start = max(t_start, s_start)
            overlap_end = min(t_end, s_end)

            if overlap_start < overlap_end:
                overlap_duration = overlap_end - overlap_start
                speaker_overlap[s_seg["speaker"]] += overlap_duration

        # 選擇重疊時間最長的說話者
        speaker = None
        if speaker_overlap:
            speaker = max(speaker_overlap.keys(), key=lambda s: speaker_overlap[s])

        # Fallback: 找最近的說話者區段
        if speaker is None:
            t_mid = (t_start + t_end) / 2
            min_distance = float('inf')
            for s_seg in speaker_segments:
                if t_mid < s_seg["start"]:
                    distance = s_seg["start"] - t_mid
                elif t_mid > s_seg["end"]:
                    distance = t_mid - s_seg["end"]
                else:
                    distance = 0

                if distance < min_distance:
                    min_distance = distance
                    speaker = s_seg["speaker"]

        # 最後 fallback: 使用上一個已知的說話者
        if speaker is None:
            speaker = last_known_speaker or "Speaker 1"

        last_known_speaker = speaker

        result.append({
            "start": t_start,
            "end": t_end,
            "text": t_seg["text"],
            "speaker": speaker
        })

    return result
