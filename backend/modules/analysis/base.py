"""
分析處理器基類
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseProcessor(ABC):
    """分析處理器基類"""

    @property
    @abstractmethod
    def name(self) -> str:
        """處理器名稱"""
        pass

    @abstractmethod
    def process(
        self,
        transcript: str,
        segments: List[Dict] = None,
        previous_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        處理轉錄文字

        Args:
            transcript: 格式化的轉錄文字
            segments: 結構化的段落資料（可選）
            previous_results: 前面處理器的結果（可選，用於整合型處理器）

        Returns:
            處理結果字典
        """
        pass
