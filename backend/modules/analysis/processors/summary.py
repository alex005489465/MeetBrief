"""
會議摘要處理器 - 整合所有分析切面生成最終摘要
"""
from typing import Dict, Any, List, Optional
from ..base import BaseProcessor
from backend.common.llm import get_llm_client


SUMMARY_PROMPT = """你是一位專業的會議記錄助手。請根據以下資訊生成一份完整的會議摘要報告。

## 會議逐字稿（部分）
{transcript_excerpt}

## 已分析的資訊

### 說話者分析
{speakers_info}

### 行動項目
{actions_info}

### 決議事項
{decisions_info}

---

請根據以上資訊，生成一份結構完整的會議摘要。格式如下：

## 會議主題
（一句話概括，最多 15 字，例如：「產品上線時程討論」「Q1 業績檢討」）

## 參與者
（根據說話者分析列出參與者及其角色）

## 重點摘要
（列出 3-5 個最重要的討論要點，每點 1-2 句話）

## 行動項目
（整理行動項目，格式：「- [ ] 任務內容 @負責人 (截止時間)」）

## 決議事項
（整理已達成共識的事項）

## 互動模式
（簡述會議中的互動情況）

請使用繁體中文，保持專業且簡潔的風格。"""


class SummaryProcessor(BaseProcessor):
    """會議摘要處理器 - 整合所有分析結果"""

    @property
    def name(self) -> str:
        return "summary"

    def process(
        self,
        transcript: str,
        segments: List[Dict] = None,
        previous_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """生成會議摘要，整合前面處理器的結果"""
        client = get_llm_client()
        previous_results = previous_results or {}

        # 準備各切面資訊
        speakers_info = self._format_speakers(previous_results.get("speakers", {}))
        actions_info = self._format_actions(previous_results.get("actions", {}))
        decisions_info = self._format_decisions(previous_results.get("decisions", {}))

        # 取逐字稿摘錄（用於補充上下文）
        transcript_excerpt = self._get_transcript_excerpt(transcript)

        prompt = SUMMARY_PROMPT.format(
            transcript_excerpt=transcript_excerpt,
            speakers_info=speakers_info,
            actions_info=actions_info,
            decisions_info=decisions_info
        )

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一位專業的會議記錄助手，擅長整合分析資訊並生成結構化摘要。請直接輸出 Markdown 格式的摘要。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=3000
        )

        return {
            "content": response.choices[0].message.content,
            "integrated_from": list(previous_results.keys()),
            "transcript_length": len(transcript)
        }

    def _get_transcript_excerpt(self, transcript: str, max_chars: int = 6000) -> str:
        """取得逐字稿摘錄（前段 + 後段）"""
        if len(transcript) <= max_chars:
            return transcript

        # 取前 4000 字 + 後 2000 字
        front = transcript[:4000]
        back = transcript[-2000:]
        return f"{front}\n\n[... 中間內容省略 ...]\n\n{back}"

    def _format_speakers(self, speakers_result: Dict) -> str:
        """格式化說話者資訊"""
        if not speakers_result or "error" in speakers_result:
            return "（無說話者資訊）"

        lines = []

        # 統計資訊
        stats = speakers_result.get("stats", {})
        if stats:
            lines.append("**發言統計：**")
            for speaker, data in stats.items():
                duration = data.get("duration_mins", 0)
                percentage = data.get("percentage", 0)
                count = data.get("segment_count", 0)
                lines.append(f"- {speaker}: {duration} 分鐘 ({percentage}%), {count} 段發言")

        # 分析結果
        analysis = speakers_result.get("analysis", {})
        if analysis and "speakers" in analysis:
            lines.append("\n**角色分析：**")
            for speaker, info in analysis.get("speakers", {}).items():
                role = info.get("role", "未知")
                stance = info.get("stance", "")
                main_points = info.get("main_points", [])
                lines.append(f"- {speaker}：{role}")
                if stance:
                    lines.append(f"  - 立場：{stance}")
                if main_points:
                    for point in main_points[:3]:
                        lines.append(f"  - {point}")

        if analysis and "interaction_pattern" in analysis:
            lines.append(f"\n**互動模式：** {analysis['interaction_pattern']}")

        return "\n".join(lines) if lines else "（無說話者資訊）"

    def _format_actions(self, actions_result: Dict) -> str:
        """格式化行動項目"""
        if not actions_result or "error" in actions_result:
            return "（無行動項目）"

        items = actions_result.get("items", [])
        if not items:
            return "（無行動項目）"

        lines = []
        for item in items:
            task = item.get("task", "")
            assignee = item.get("assignee")
            deadline = item.get("deadline")
            priority = item.get("priority", "medium")
            context = item.get("context", "")

            line = f"- {task}"
            if assignee:
                line += f" @{assignee}"
            if deadline:
                line += f" (截止: {deadline})"
            line += f" [優先級: {priority}]"
            lines.append(line)
            if context:
                lines.append(f"  背景: {context}")

        return "\n".join(lines)

    def _format_decisions(self, decisions_result: Dict) -> str:
        """格式化決議事項"""
        if not decisions_result or "error" in decisions_result:
            return "（無決議事項）"

        items = decisions_result.get("items", [])
        if not items:
            return "（無決議事項）"

        lines = []
        for item in items:
            decision = item.get("decision", "")
            background = item.get("background", "")
            confidence = item.get("confidence", "medium")

            line = f"- {decision}"
            if confidence != "high":
                line += f" [確信度: {confidence}]"
            lines.append(line)
            if background:
                lines.append(f"  背景: {background}")

        return "\n".join(lines)
