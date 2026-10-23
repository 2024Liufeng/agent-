from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
load_dotenv(ENV_FILE)


@dataclass
class Settings:
    """运行期配置。

    不使用 frozen：主 Agent 可以通过文件工具改写 .env，
    随后 reload() 让新的 Tavily Key 立即生效，无需重启后端。
    """

    llm_model: str
    llm_api_key: str
    llm_base_url: str
    tavily_api_key: str | None
    edge_path: Path
    edge_profile: Path

    @classmethod
    def from_env(cls):
        return cls(
            llm_model=os.getenv("LLM_MODEL_ID", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", ""),
            tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
            edge_path=Path(os.getenv(
                "EDGE_PATH",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            )),
            edge_profile=ROOT / ".edge-profile",
        )

    def reload(self) -> None:
        """重新读取 .env，让运行期修改的密钥生效。

        只刷新可能被用户或主 Agent 就地修改的字段；
        Edge 路径与 Profile 目录在进程内保持不变。
        """
        load_dotenv(ENV_FILE, override=True)
        self.tavily_api_key = os.getenv("TAVILY_API_KEY") or None
