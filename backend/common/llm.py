"""
LLM 客戶端 - DeepSeek API
"""
from openai import OpenAI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

_client = None


def get_llm_client() -> OpenAI:
    """
    取得 LLM 客戶端（單例模式）

    Returns:
        OpenAI 客戶端（相容 DeepSeek API）
    """
    global _client
    if _client is None:
        if not DEEPSEEK_API_KEY:
            raise ValueError("未設定 DEEPSEEK_API_KEY")
        _client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL
        )
    return _client
