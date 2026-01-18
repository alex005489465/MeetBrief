"""
語音處理模組 - 轉錄協調與合併
"""
from .coordinator import TaskCoordinator, get_coordinator, coordinator_loop
from .merger import merge_transcription_with_speakers

__all__ = [
    "TaskCoordinator",
    "get_coordinator",
    "coordinator_loop",
    "merge_transcription_with_speakers",
]
