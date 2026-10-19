"""运行配置。

配置全部通过环境变量提供，避免把 API 密钥、登录会话路径写入代码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - .env loading is optional
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    """第一版运行配置。"""

    user_id: str = "default-user"
    memory_db: Path = PROJECT_ROOT / "data" / "shopping_memory.sqlite3"
    memory_vector_path: Path = PROJECT_ROOT / "data" / "memory_vectors"
    memory_vector_enabled: bool = False
    memory_embedding_api_key: str | None = None
    memory_embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    memory_embedding_model: str = "text-embedding-v3"
    memory_embedding_dimension: int = 1024
    rag_db: Path = PROJECT_ROOT / "data" / "product_knowledge.sqlite3"
    rag_knowledge_dir: Path = PROJECT_ROOT / "data" / "knowledge"
    playwright_profile: Path = PROJECT_ROOT / ".playwright-profile"
    drission_profile: Path = PROJECT_ROOT / ".drission-edge-profile"
    edge_path: Path = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    drission_port: int = 9232
    drission_headless: bool = False
    drission_wait_ms: int = 8000
    playwright_proxy: str | None = None
    playwright_cdp_endpoint: str | None = None
    playwright_headless: bool = True
    playwright_wait_ms: int = 8000
    playwright_block_cooldown_seconds: int = 90
    max_platform_results: int = 10
    llm_model_id: str = "gpt-6-luna"
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    search_provider: str = "tavily"
    tavily_api_key: str | None = None
    tavily_endpoint: str = "https://api.tavily.com/search"

    @classmethod
    def from_env(cls, user_id: str | None = None) -> "AppConfig":
        return cls(
            user_id=user_id or os.getenv("SHOPPING_USER_ID", "default-user"),
            memory_db=Path(
                os.getenv(
                    "SHOPPING_MEMORY_DB",
                    str(PROJECT_ROOT / "data" / "shopping_memory.sqlite3"),
                )
            ),
            memory_vector_path=Path(
                os.getenv(
                    "MEMORY_VECTOR_PATH",
                    str(PROJECT_ROOT / "data" / "memory_vectors"),
                )
            ),
            memory_vector_enabled=_bool_env("MEMORY_VECTOR_ENABLED", False),
            memory_embedding_api_key=os.getenv("DASHSCOPE_API_KEY") or None,
            memory_embedding_base_url=os.getenv(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            memory_embedding_model=os.getenv(
                "MEMORY_EMBEDDING_MODEL", "text-embedding-v3"
            ),
            memory_embedding_dimension=int(
                os.getenv("MEMORY_EMBEDDING_DIMENSION", "1024")
            ),
            rag_db=Path(
                os.getenv(
                    "SHOPPING_RAG_DB",
                    str(PROJECT_ROOT / "data" / "product_knowledge.sqlite3"),
                )
            ),
            rag_knowledge_dir=Path(
                os.getenv(
                    "SHOPPING_RAG_KNOWLEDGE_DIR",
                    str(PROJECT_ROOT / "data" / "knowledge"),
                )
            ),
            playwright_profile=Path(
                os.getenv(
                    "PLAYWRIGHT_PROFILE_DIR", str(PROJECT_ROOT / ".playwright-profile")
                )
            ),
            drission_profile=Path(
                os.getenv(
                    "DRISSION_PROFILE_DIR", str(PROJECT_ROOT / ".drission-edge-profile")
                )
            ),
            edge_path=Path(
                os.getenv(
                    "EDGE_PATH",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                )
            ),
            drission_port=int(os.getenv("DRISSION_PORT", "9232")),
            drission_headless=_bool_env("DRISSION_HEADLESS", False),
            drission_wait_ms=int(
                os.getenv("DRISSION_WAIT_MS", os.getenv("PLAYWRIGHT_WAIT_MS", "8000"))
            ),
            playwright_proxy=os.getenv("PLAYWRIGHT_PROXY") or None,
            playwright_cdp_endpoint=os.getenv("PLAYWRIGHT_CDP_ENDPOINT") or None,
            playwright_headless=_bool_env("PLAYWRIGHT_HEADLESS", True),
            playwright_wait_ms=int(os.getenv("PLAYWRIGHT_WAIT_MS", "8000")),
            playwright_block_cooldown_seconds=int(
                os.getenv("PLAYWRIGHT_BLOCK_COOLDOWN_SECONDS", "90")
            ),
            max_platform_results=int(os.getenv("MAX_PLATFORM_RESULTS", "10")),
            llm_model_id=os.getenv(
                "LLM_MODEL_ID", os.getenv("CODEX_MODEL", "gpt-6-luna")
            ),
            llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
            llm_base_url=os.getenv(
                "LLM_BASE_URL",
                os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            ),
            search_provider=os.getenv("PRODUCT_SEARCH_PROVIDER", "tavily"),
            tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
            tavily_endpoint=os.getenv(
                "TAVILY_ENDPOINT", "https://api.tavily.com/search"
            ),
        )
