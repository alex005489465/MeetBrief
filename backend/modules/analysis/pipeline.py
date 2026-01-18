"""
分析管線 - 組合多個處理器
"""
from typing import List, Dict, Any
from .base import BaseProcessor


class AnalysisPipeline:
    """分析管線"""

    def __init__(self):
        self.processors: List[BaseProcessor] = []

    def add_processor(self, processor: BaseProcessor):
        """新增處理器"""
        self.processors.append(processor)
        return self

    def run(self, transcript: str, segments: List[Dict] = None) -> Dict[str, Any]:
        """
        執行所有處理器

        Args:
            transcript: 格式化的轉錄文字
            segments: 結構化的段落資料

        Returns:
            所有處理結果的合併字典
        """
        results = {}
        for processor in self.processors:
            try:
                # 傳遞前面所有處理器的結果
                result = processor.process(transcript, segments, previous_results=results)
                results[processor.name] = result
            except Exception as e:
                results[processor.name] = {"error": str(e)}
                import traceback
                traceback.print_exc()
        return results
