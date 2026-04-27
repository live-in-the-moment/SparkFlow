from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CadEntity:
    entity_id: str
    kind: str
    props: dict[str, Any] = field(default_factory=dict)

    def get_float(self, key: str) -> float | None:
        v = self.props.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def get_str(self, key: str) -> str | None:
        v = self.props.get(key)
        if v is None:
            return None
        return str(v)


@dataclass(frozen=True)
class ParsedCad:
    parser_id: str
    entities: tuple[CadEntity, ...]
    meta: dict[str, Any] = field(default_factory=dict)
