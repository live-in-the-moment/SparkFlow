from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .entities import CadEntity, ParsedCad
from .errors import CadParseError


@dataclass(frozen=True)
class _Pair:
    code: str
    value: str


def parse_ascii_dxf(path: Path) -> ParsedCad:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    pairs = list(_iter_pairs(text))
    entities = tuple(_extract_entities(pairs))
    return ParsedCad(parser_id="dxf_ascii_v1", entities=entities)


def _iter_pairs(text: str) -> Iterable[_Pair]:
    lines = [ln.rstrip("\r\n") for ln in text.splitlines()]
    if len(lines) % 2 != 0:
        lines = lines[:-1]
    for i in range(0, len(lines), 2):
        yield _Pair(code=lines[i].strip(), value=lines[i + 1].strip())


def _extract_entities(pairs: list[_Pair]) -> list[CadEntity]:
    entities: list[CadEntity] = []
    in_entities = False
    i = 0
    current_kind: str | None = None
    current: dict[str, str] = {}

    def flush() -> None:
        nonlocal current_kind, current
        if current_kind is None:
            return
        entity_id = str(len(entities) + 1)
        entities.append(CadEntity(entity_id=entity_id, kind=current_kind, props=dict(current)))
        current_kind = None
        current = {}

    while i < len(pairs):
        p = pairs[i]

        if p.code == "0" and p.value == "SECTION":
            if i + 1 < len(pairs) and pairs[i + 1].code == "2":
                in_entities = pairs[i + 1].value.upper() == "ENTITIES"
            i += 1
            continue

        if in_entities:
            if p.code == "0" and p.value == "ENDSEC":
                flush()
                in_entities = False
                i += 1
                continue

            if p.code == "0":
                flush()
                current_kind = p.value.upper()
                i += 1
                continue

            if current_kind is not None:
                current[f"gc_{p.code}"] = p.value

        i += 1

    flush()
    if not entities:
        raise CadParseError("未能从 DXF 中解析到任何实体。")
    return entities
