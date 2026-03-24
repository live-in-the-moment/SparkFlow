from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from ..cad.entities import CadEntity
from .types import DrawingSelection


_SUPPORTED_KEYWORDS = ('一次系统图', '主接线', '电气图', '380v')
_GEOMETRY_KEYWORDS = ('平面', '剖面', '布置', '加工图', '安装示意', '杆型', '方案')
_TEXT_ELECTRICAL_HINTS = (
    '母线',
    '主变',
    '断路器',
    '隔离开关',
    '熔断器式隔离开关',
    '负荷开关',
    '开关柜',
    '配电箱',
    '低压柜',
    '分支箱',
    '电气',
    '变压器',
    '电能表',
    '集中器',
    '电流互感器',
    '计量单元',
    '无功补偿单元',
    '出线单元',
    '进线侧',
    '出线侧',
    '浪涌保护器',
    '避雷器',
    '馈线',
    '所用电',
)
_TEXT_GEOMETRY_HINTS = (
    '平面图',
    '断面图',
    '排管',
    '手孔井',
    '盖板',
    '混凝土',
    '回填土',
    '垫层',
    '砖砌',
    '人行道',
    '井壁',
    '剖面',
    '直埋',
    '保护管',
    '压顶',
)
_TEXT_STRONG_GEOMETRY_HINTS = ('平面图', '断面图', '排管', '手孔井', '井壁', '盖板', '砖砌', '压顶')
_TEXT_STRONG_ELECTRICAL_HINTS = ('母线', '主变', '断路器', '隔离开关', '开关柜', '配电箱', '变压器', '计量单元', '无功补偿单元', '出线单元', '进线侧')


def selection_texts_from_entities(entities: tuple[CadEntity, ...]) -> list[str]:
    out: list[str] = []
    for entity in entities:
        if entity.kind.upper() not in {'TEXT', 'MTEXT'}:
            continue
        text = entity.props.get('gc_1')
        if isinstance(text, str) and text.strip():
            out.append(text)
    return out


def classify_drawing(path: Path, texts: Iterable[str] | None = None) -> DrawingSelection:
    base = _classify_from_path(path)
    if base.drawing_class == 'geometry_only':
        return base
    text_signals = _score_text_features(texts or ())
    if base.reason == 'matched_parent_dir:电缆CAD图纸':
        if text_signals['geometry_score'] >= max(3, text_signals['electrical_score'] + 1):
            return DrawingSelection(
                drawing_class='geometry_only',
                reason=f"text_geometry_override:{_format_hits(text_signals['geometry_hits'])}",
                eligible_for_electrical=False,
            )
        if text_signals['electrical_score'] >= 2 and text_signals['strong_electrical_hits']:
            return DrawingSelection(
                drawing_class='supported_electrical',
                reason=f"text_electrical_confirm:{_format_hits(text_signals['electrical_hits'])}",
                eligible_for_electrical=True,
            )
        return base
    if base.reason == 'matched_supported_keyword:380v':
        if text_signals['geometry_score'] >= max(3, text_signals['electrical_score'] + 2):
            return DrawingSelection(
                drawing_class='geometry_only',
                reason=f"text_geometry_override:{_format_hits(text_signals['geometry_hits'])}",
                eligible_for_electrical=False,
            )
        return base
    if base.reason == 'no_supported_keyword_match':
        if text_signals['electrical_score'] >= 3 and text_signals['strong_electrical_hits']:
            return DrawingSelection(
                drawing_class='supported_electrical',
                reason=f"text_electrical_match:{_format_hits(text_signals['electrical_hits'])}",
                eligible_for_electrical=True,
            )
        if text_signals['geometry_score'] >= 3:
            return DrawingSelection(
                drawing_class='geometry_only',
                reason=f"text_geometry_match:{_format_hits(text_signals['geometry_hits'])}",
                eligible_for_electrical=False,
            )
    return base


def resolve_selection(
    path: Path,
    *,
    rel_path: str | None = None,
    mode: str = 'auto',
    texts: Iterable[str] | None = None,
) -> DrawingSelection:
    mode = (mode or 'auto').strip()
    if not mode or mode == 'auto':
        return classify_drawing(path, texts=texts)
    if mode.startswith('list='):
        manifest = Path(mode.split('=', 1)[1]).resolve()
        entries = _load_manifest(manifest)
        rel = (rel_path or path.name).replace('\\', '/')
        if rel in entries:
            return DrawingSelection(
                drawing_class='supported_electrical',
                reason=f'selection_manifest:{manifest.name}',
                eligible_for_electrical=True,
            )
        return DrawingSelection(
            drawing_class='unsupported',
            reason=f'not_in_selection_manifest:{manifest.name}',
            eligible_for_electrical=False,
        )
    return classify_drawing(path, texts=texts)


def _classify_from_path(path: Path) -> DrawingSelection:
    p = path.resolve()
    parts = [part.lower() for part in p.parts]
    name = p.stem.lower()
    rel = '/'.join(parts)

    for kw in _GEOMETRY_KEYWORDS:
        lowered = kw.lower()
        if lowered in name or lowered in rel:
            return DrawingSelection(
                drawing_class='geometry_only',
                reason=f'matched_geometry_keyword:{kw}',
                eligible_for_electrical=False,
            )

    for kw in _SUPPORTED_KEYWORDS:
        lowered = kw.lower()
        if lowered in name:
            return DrawingSelection(
                drawing_class='supported_electrical',
                reason=f'matched_supported_keyword:{kw}',
                eligible_for_electrical=True,
            )

    if '电缆cad图纸' in rel:
        return DrawingSelection(
            drawing_class='supported_electrical',
            reason='matched_parent_dir:电缆CAD图纸',
            eligible_for_electrical=True,
        )

    return DrawingSelection(
        drawing_class='unsupported',
        reason='no_supported_keyword_match',
        eligible_for_electrical=False,
    )


def _score_text_features(texts: Iterable[str]) -> dict[str, object]:
    geometry_hits: list[str] = []
    electrical_hits: list[str] = []
    for raw in texts:
        normalized = _normalize_text(raw)
        if not normalized:
            continue
        lowered = normalized.lower()
        for hint in _TEXT_GEOMETRY_HINTS:
            if hint.lower() in lowered and hint not in geometry_hits:
                geometry_hits.append(hint)
        for hint in _TEXT_ELECTRICAL_HINTS:
            if hint.lower() in lowered and hint not in electrical_hits:
                electrical_hits.append(hint)
    geometry_score = sum(2 if hit in _TEXT_STRONG_GEOMETRY_HINTS else 1 for hit in geometry_hits)
    electrical_score = len(electrical_hits)
    strong_electrical_hits = [hit for hit in electrical_hits if hit in _TEXT_STRONG_ELECTRICAL_HINTS]
    return {
        'geometry_hits': geometry_hits,
        'electrical_hits': electrical_hits,
        'geometry_score': geometry_score,
        'electrical_score': electrical_score,
        'strong_electrical_hits': strong_electrical_hits,
    }


def _format_hits(hits: list[str]) -> str:
    if not hits:
        return 'none'
    return '|'.join(hits[:3])


def _normalize_text(text: str) -> str:
    cleaned = str(text or '')
    cleaned = cleaned.replace('^M^J', ' ').replace('\\P', ' ').replace('{', ' ').replace('}', ' ')
    cleaned = re.sub(r'\\[A-Za-z][^;{}]*;', ' ', cleaned)
    cleaned = re.sub(r'%{2,3}[A-Za-z0-9]+', ' ', cleaned)
    cleaned = cleaned.replace('~', ' ')
    cleaned = ' '.join(part for part in cleaned.split() if part)
    return cleaned.strip()


def _load_manifest(path: Path) -> set[str]:
    raw = path.read_text(encoding='utf-8')
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, list):
        return {
            str(item).replace('\\', '/').strip()
            for item in obj
            if isinstance(item, (str, int, float)) and str(item).strip()
        }
    return {
        line.replace('\\', '/').strip()
        for line in raw.splitlines()
        if line.strip() and not line.strip().startswith('#')
    }
