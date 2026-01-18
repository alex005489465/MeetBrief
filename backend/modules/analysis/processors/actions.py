"""
行動項目處理器 - 從會議中提取待辦事項
"""
from typing import Dict, Any, List
from ..base import BaseProcessor
from backend.common.llm import get_llm_client


ACTIONS_PROMPT = """你是一位專業的會議記錄助手。請從以下會議逐字稿中提取所有行動項目（Action Items）。

會議逐字稿：
{transcript}

請提取會議中提到的：
1. 需要執行的任務
2. 需要跟進的事項
3. 需要準備的東西
4. 承諾要做的事情

對於每個行動項目，請盡可能識別：
- 負責人（如果有提到）
- 截止時間（如果有提到）
- 優先級（根據語氣判斷：高/中/低）

請使用以下 JSON 格式回覆，不要有其他文字：
```json
{{
  "items": [
    {{
      "task": "任務描述",
      "assignee": "負責人（若無法識別則為 null）",
      "deadline": "截止時間（若無則為 null）",
      "priority": "high/medium/low",
      "context": "相關上下文（簡短說明為什麼要做這件事）"
    }}
  ]
}}
```

如果沒有找到任何行動項目，請回覆：
```json
{{"items": []}}
```"""


class ActionsProcessor(BaseProcessor):
    """行動項目處理器"""

    @property
    def name(self) -> str:
        return "actions"

    def process(self, transcript: str, segments: List[Dict] = None, previous_results: Dict = None) -> Dict[str, Any]:
        """提取行動項目"""
        client = get_llm_client()

        # 截斷過長的文字
        max_chars = 15000
        if len(transcript) > max_chars:
            transcript = transcript[:max_chars]

        prompt = ACTIONS_PROMPT.format(transcript=transcript)

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一位專業的會議記錄助手，擅長從會議對話中識別和提取行動項目。請只回覆 JSON 格式。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,  # 更低的溫度確保結構化輸出
            max_tokens=2000
        )

        content = response.choices[0].message.content

        # 解析 JSON
        items = self._parse_response(content)

        return {
            "items": items,
            "count": len(items)
        }

    def _parse_response(self, content: str) -> List[Dict]:
        """解析 LLM 回應"""
        import json
        import re

        # 嘗試提取 JSON 區塊
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        # 清理可能的前後空白
        content = content.strip()

        try:
            data = json.loads(content)
            return data.get("items", [])
        except json.JSONDecodeError:
            # 如果解析失敗，返回空列表
            print(f"[ActionsProcessor] JSON 解析失敗: {content[:200]}")
            return []
