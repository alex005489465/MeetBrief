"""
決議事項處理器 - 從會議中提取達成的共識和決定
"""
from typing import Dict, Any, List
from ..base import BaseProcessor
from backend.common.llm import get_llm_client


DECISIONS_PROMPT = """你是一位專業的會議記錄助手。請從以下會議逐字稿中提取所有決議事項。

會議逐字稿：
{transcript}

請提取會議中：
1. 達成共識的事項
2. 做出的決定
3. 確認的方向或策略
4. 同意採用的方案

對於每個決議，請識別：
- 決議內容
- 相關討論背景（為什麼做這個決定）
- 影響範圍（這個決定會影響什麼）

請使用以下 JSON 格式回覆，不要有其他文字：
```json
{{
  "items": [
    {{
      "decision": "決議內容",
      "background": "討論背景（簡述）",
      "impact": "影響範圍（若無明確則為 null）",
      "confidence": "high/medium/low（根據討論的明確程度）"
    }}
  ]
}}
```

注意：
- 只提取明確達成共識的事項，不要包含仍在討論中的議題
- 如果沒有找到任何決議，請回覆 {{"items": []}}"""


class DecisionsProcessor(BaseProcessor):
    """決議事項處理器"""

    @property
    def name(self) -> str:
        return "decisions"

    def process(self, transcript: str, segments: List[Dict] = None, previous_results: Dict = None) -> Dict[str, Any]:
        """提取決議事項"""
        client = get_llm_client()

        # 截斷過長的文字
        max_chars = 15000
        if len(transcript) > max_chars:
            transcript = transcript[:max_chars]

        prompt = DECISIONS_PROMPT.format(transcript=transcript)

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一位專業的會議記錄助手，擅長識別會議中達成的共識和決議。請只回覆 JSON 格式。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,
            max_tokens=2000
        )

        content = response.choices[0].message.content
        items = self._parse_response(content)

        return {
            "items": items,
            "count": len(items)
        }

    def _parse_response(self, content: str) -> List[Dict]:
        """解析 LLM 回應"""
        import json
        import re

        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        content = content.strip()

        try:
            data = json.loads(content)
            return data.get("items", [])
        except json.JSONDecodeError:
            print(f"[DecisionsProcessor] JSON 解析失敗: {content[:200]}")
            return []
