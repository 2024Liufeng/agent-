"""购物助手在工具之间传递的稳定数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProductQuote:
    title: str
    platform: str
    url: str
    price: float | None = None
    brand: str | None = None
    model: str | None = None
    specification: str | None = None
    seller: str | None = None
    conditions: list[str] = field(default_factory=list)
    source: str = ""
    collected_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchCandidate:
    title: str
    url: str
    snippet: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)
