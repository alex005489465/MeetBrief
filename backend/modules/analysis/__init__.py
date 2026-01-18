"""
資訊統整模組 - 多種切面分析
"""
from .base import BaseProcessor
from .pipeline import AnalysisPipeline
from .processors.summary import SummaryProcessor
from .processors.actions import ActionsProcessor
from .processors.decisions import DecisionsProcessor
from .processors.speakers import SpeakersProcessor


def create_full_pipeline() -> AnalysisPipeline:
    """
    建立完整的分析管線

    處理器順序：
    1. speakers - 說話者分析（使用 segments）
    2. actions - 行動項目提取
    3. decisions - 決議事項提取
    4. summary - 整合摘要（使用前面所有結果）

    Returns:
        設定好的 AnalysisPipeline 實例
    """
    pipeline = AnalysisPipeline()
    pipeline.add_processor(SpeakersProcessor())
    pipeline.add_processor(ActionsProcessor())
    pipeline.add_processor(DecisionsProcessor())
    pipeline.add_processor(SummaryProcessor())  # 最後執行，整合所有結果
    return pipeline


__all__ = [
    "BaseProcessor",
    "AnalysisPipeline",
    "SummaryProcessor",
    "ActionsProcessor",
    "DecisionsProcessor",
    "SpeakersProcessor",
    "create_full_pipeline",
]
