"""
說話者分析處理器 - 分析每位說話者的觀點和貢獻
"""
from typing import Dict, Any, List
from collections import defaultdict
from ..base import BaseProcessor
from backend.common.llm import get_llm_client


SPEAKERS_PROMPT = """你是一位專業的會議分析師。請根據以下會議內容，分析每位說話者的觀點和角色。

{speakers_content}

請分析：
1. 每位說話者在會議中的角色（如：主導者、提問者、報告者等）
2. 每位說話者的主要觀點或立場
3. 說話者之間的互動模式（如：誰在回應誰的問題）

請使用以下 JSON 格式回覆：
```json
{{
  "speakers": {{
    "speaker_0": {{
      "role": "角色描述",
      "main_points": ["觀點1", "觀點2"],
      "stance": "整體立場或態度（簡述）"
    }},
    "speaker_1": {{
      "role": "角色描述",
      "main_points": ["觀點1", "觀點2"],
      "stance": "整體立場或態度（簡述）"
    }}
  }},
  "interaction_pattern": "互動模式描述"
}}
```"""


class SpeakersProcessor(BaseProcessor):
    """說話者分析處理器"""

    @property
    def name(self) -> str:
        return "speakers"

    def process(self, transcript: str, segments: List[Dict] = None, previous_results: Dict = None) -> Dict[str, Any]:
        """分析說話者"""
        # 先統計說話者資訊
        stats = self._calculate_stats(segments) if segments else {}

        if not stats:
            return {
                "stats": {},
                "analysis": None,
                "error": "無說話者資訊"
            }

        # 準備每位說話者的發言內容
        speakers_content = self._prepare_speakers_content(segments)

        # 呼叫 LLM 分析
        analysis = self._analyze_speakers(speakers_content)

        return {
            "stats": stats,
            "analysis": analysis
        }

    def _calculate_stats(self, segments: List[Dict]) -> Dict[str, Any]:
        """計算說話者統計資料"""
        if not segments:
            return {}

        speaker_time = defaultdict(float)
        speaker_count = defaultdict(int)

        for seg in segments:
            speaker = seg.get("speaker")
            if speaker:
                duration = seg.get("end", 0) - seg.get("start", 0)
                speaker_time[speaker] += duration
                speaker_count[speaker] += 1

        total_time = sum(speaker_time.values())

        stats = {}
        for speaker in sorted(speaker_time.keys()):
            time_mins = speaker_time[speaker] / 60
            percentage = (speaker_time[speaker] / total_time * 100) if total_time > 0 else 0
            stats[speaker] = {
                "duration_mins": round(time_mins, 1),
                "percentage": round(percentage, 1),
                "segment_count": speaker_count[speaker]
            }

        return stats

    def _prepare_speakers_content(self, segments: List[Dict]) -> str:
        """準備每位說話者的發言內容（用於 LLM 分析）"""
        speaker_texts = defaultdict(list)

        for seg in segments:
            speaker = seg.get("speaker")
            text = seg.get("text", "")
            if speaker and text:
                speaker_texts[speaker].append(text)

        # 組合成文字
        lines = []
        for speaker in sorted(speaker_texts.keys()):
            texts = speaker_texts[speaker]
            # 只取前 20 段，避免太長
            sample_texts = texts[:20]
            content = "\n".join(f"  - {t}" for t in sample_texts)
            if len(texts) > 20:
                content += f"\n  ... (共 {len(texts)} 段發言)"
            lines.append(f"### {speaker} 的發言：\n{content}")

        return "\n\n".join(lines)

    def _analyze_speakers(self, speakers_content: str) -> Dict[str, Any]:
        """使用 LLM 分析說話者"""
        client = get_llm_client()

        # 截斷過長內容
        max_chars = 12000
        if len(speakers_content) > max_chars:
            speakers_content = speakers_content[:max_chars] + "\n\n[內容過長，已截斷...]"

        prompt = SPEAKERS_PROMPT.format(speakers_content=speakers_content)

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一位專業的會議分析師，擅長分析會議參與者的角色和觀點。請只回覆 JSON 格式。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=2000
        )

        content = response.choices[0].message.content
        return self._parse_response(content)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """解析 LLM 回應"""
        import json
        import re

        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            print(f"[SpeakersProcessor] JSON 解析失敗: {content[:200]}")
            return {"error": "解析失敗", "raw": content[:500]}
