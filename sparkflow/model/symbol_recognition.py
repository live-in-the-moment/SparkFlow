from __future__ import annotations

import fnmatch
import math
import re
from dataclasses import dataclass

from ..cad.entities import CadEntity
from .build_options import DeviceTemplate
from .geometry import dist, dist2, distance_point_to_segment, project_point_to_segment
from .types import Device, Point2D, Terminal, UnresolvedItem, WireSegment


_IGNORE_TEXT_KEYWORDS = (
    '说明',
    '规格及型号',
    '序号',
    '代号',
    '名称',
    '数量',
    '单位',
    '典型设计',
    '图纸',
    '宽',
    '深',
    '高',
)
_TABLE_HEADER_KEYWORDS = ('序号', '代号', '名称', '规格及型号', '数量', '单位', '备注')


@dataclass(frozen=True)
class _TextCandidate:
    text_id: str
    point: Point2D
    text: str
    template: DeviceTemplate
    keyword: str


@dataclass(frozen=True)
class _TextGroup:
    template: DeviceTemplate
    items: tuple[_TextCandidate, ...]
    center: Point2D
    label: str


def recognize_devices(
    inserts: list[CadEntity],
    texts: list[tuple[str, Point2D, str]],
    wires: list[WireSegment],
    *,
    device_templates: tuple[DeviceTemplate, ...],
) -> tuple[list[Device], list[UnresolvedItem]]:
    devices: list[Device] = []
    unresolved: list[UnresolvedItem] = []

    for entity in inserts:
        device, issues = _recognize_insert_device(entity, texts, wires, device_templates=device_templates)
        unresolved.extend(issues)
        if device is not None:
            devices.append(device)

    devices_by_position = [device.position for device in devices]
    for group in _build_text_groups(texts, device_templates=device_templates):
        if _group_is_covered_by_existing_devices(group, devices):
            continue
        if _surrounding_text_count(group.center, texts, radius=max(18.0, group.template.text_group_radius * 2.0)) > 6:
            continue
        if any(dist(existing, group.center) <= max(group.template.footprint_radius * 0.6, 8.0) for existing in devices_by_position):
            continue
        terminals = _infer_terminals_near_point(
            device_id=f'textdev:{group.items[0].text_id}',
            center=group.center,
            wires=wires,
            template=group.template,
            source_entity_ids=tuple(item.text_id for item in group.items),
        )
        if len(terminals) < max(1, group.template.min_terminals):
            unresolved.append(
                UnresolvedItem(
                    kind='terminal_anchor',
                    source_entity_ids=tuple(item.text_id for item in group.items),
                    reason='文本设备候选未识别到足够端子锚点，已跳过。',
                    extra={'device_type': group.template.device_type, 'label': group.label},
                )
            )
            continue
        devices.append(
            Device(
                id=f'textdev:{group.items[0].text_id}',
                position=group.center,
                label=group.label,
                device_type=group.template.device_type,
                terminals=terminals,
                block_name=None,
                source_entity_ids=tuple(item.text_id for item in group.items),
                footprint_radius=group.template.footprint_radius,
            )
        )
        devices_by_position.append(group.center)

    return devices, unresolved

def attach_nearby_terminals(
    devices: list[Device],
    wires: list[WireSegment],
    *,
    device_templates: tuple[DeviceTemplate, ...],
) -> tuple[list[Device], list[UnresolvedItem]]:
    unresolved: list[UnresolvedItem] = []
    out: list[Device] = []
    for device in devices:
        if device.terminals:
            out.append(device)
            continue
        template = _template_for_device(device, device_templates)
        terminals = _infer_terminals_near_point(
            device_id=device.id,
            center=device.position,
            wires=wires,
            template=template,
            source_entity_ids=device.source_entity_ids,
        )
        if not terminals:
            unresolved.append(
                UnresolvedItem(
                    kind='terminal_anchor',
                    source_entity_ids=device.source_entity_ids,
                    reason='设备未识别到可靠端子锚点。',
                    extra={'device_id': device.id, 'device_type': device.device_type or 'unknown_component'},
                )
            )
        out.append(
            Device(
                id=device.id,
                position=device.position,
                label=device.label,
                device_type=device.device_type,
                terminals=terminals,
                block_name=device.block_name,
                source_entity_ids=device.source_entity_ids,
                footprint_radius=device.footprint_radius,
            )
        )
    return out, unresolved


def _recognize_insert_device(
    entity: CadEntity,
    texts: list[tuple[str, Point2D, str]],
    wires: list[WireSegment],
    *,
    device_templates: tuple[DeviceTemplate, ...],
) -> tuple[Device | None, list[UnresolvedItem]]:
    point = _point_from_codes(entity, '10', '20')
    if point is None:
        return None, []

    block_name = entity.get_str('gc_2')
    normalized_block = block_name.strip() if isinstance(block_name, str) and block_name.strip() else None
    attribs = entity.props.get('insert_attribs')
    attrib_map = attribs if isinstance(attribs, dict) else {}
    label = _nearest_text_label(point, texts)

    template = _match_block_template(normalized_block, attrib_map, device_templates)
    if template is None and label:
        template = _match_text_template(label, device_templates)
    if template is None:
        return None, [
            UnresolvedItem(
                kind='unclassified_symbol',
                source_entity_ids=(entity.entity_id,),
                reason='块参照未命中设备模板，已忽略。',
                extra={'block_name': normalized_block, 'label': label},
            )
        ]

    terminals = ()
    if normalized_block and template.terminals:
        terminals = _build_terminals_from_template(
            device_id=f'dev:{entity.entity_id}',
            center=point,
            entity=entity,
            template=template,
            source_entity_ids=(entity.entity_id,),
        )
    if not terminals:
        terminals = _infer_terminals_near_point(
            device_id=f'dev:{entity.entity_id}',
            center=point,
            wires=wires,
            template=template,
            source_entity_ids=(entity.entity_id,),
            rotation_deg=_float_prop(entity, 'gc_50') or 0.0,
            scale_x=_float_prop(entity, 'gc_41') or 1.0,
            scale_y=_float_prop(entity, 'gc_42') or 1.0,
        )

    return (
        Device(
            id=f'dev:{entity.entity_id}',
            position=point,
            label=label,
            device_type=template.device_type,
            terminals=terminals,
            block_name=normalized_block,
            source_entity_ids=(entity.entity_id,),
            footprint_radius=template.footprint_radius,
        ),
        [],
    )


def _group_is_covered_by_existing_devices(group: _TextGroup, devices: list[Device]) -> bool:
    if not devices:
        return False
    group_tokens = _split_label_tokens(group.label)
    nearby_labels: set[str] = set()
    found_nearby = False
    for device in devices:
        radius = max(group.template.footprint_radius, device.footprint_radius or 0.0, group.template.text_group_radius, 10.0)
        if dist(device.position, group.center) > radius:
            continue
        found_nearby = True
        if device.label:
            nearby_labels.update(_split_label_tokens(device.label))
    if not found_nearby:
        return False
    if not group_tokens:
        return True
    if group_tokens.issubset(nearby_labels):
        return True
    if len(group_tokens) == 1:
        token = next(iter(group_tokens))
        return any(_labels_equivalent(token, other) for other in nearby_labels)
    return False


def _split_label_tokens(label: str | None) -> set[str]:
    if not label:
        return set()
    normalized = _normalize_text(label)
    raw_tokens = re.split(r'[\/?,?\s]+', normalized)
    return {token for token in raw_tokens if token}


def _labels_equivalent(left: str, right: str) -> bool:
    a = left.strip().lower()
    b = right.strip().lower()
    return a == b or a in b or b in a


def _build_text_groups(
    texts: list[tuple[str, Point2D, str]],
    *,
    device_templates: tuple[DeviceTemplate, ...],
) -> list[_TextGroup]:
    candidates: list[_TextCandidate] = []
    for text_id, point, text in texts:
        normalized = _normalize_text(text)
        if not normalized or _should_ignore_text(normalized):
            continue
        if _is_table_context(point, texts):
            continue
        template, keyword = _match_text_template_with_keyword(normalized, device_templates)
        if template is None or not keyword:
            continue
        candidates.append(_TextCandidate(text_id=text_id, point=point, text=normalized, template=template, keyword=keyword))

    groups: list[list[_TextCandidate]] = []
    for candidate in candidates:
        placed = False
        for group in groups:
            head = group[0]
            radius = max(head.template.text_group_radius, candidate.template.text_group_radius)
            if head.template.device_type == candidate.template.device_type and dist(head.point, candidate.point) <= radius:
                group.append(candidate)
                placed = True
                break
        if not placed:
            groups.append([candidate])

    out: list[_TextGroup] = []
    for group in groups:
        center = Point2D(
            sum(item.point.x for item in group) / len(group),
            sum(item.point.y for item in group) / len(group),
        )
        if _is_table_context(center, texts):
            continue
        ordered = sorted(group, key=lambda item: (-item.point.y, item.point.x, item.text_id))
        label = '/'.join(dict.fromkeys(item.text for item in ordered))
        out.append(_TextGroup(template=group[0].template, items=tuple(ordered), center=center, label=label))
    return out

def _template_for_device(device: Device, device_templates: tuple[DeviceTemplate, ...]) -> DeviceTemplate:
    if device.block_name:
        matched = _match_block_template(device.block_name, {}, device_templates)
        if matched is not None:
            return matched
    if device.label:
        matched = _match_text_template(device.label, device_templates)
        if matched is not None:
            return matched
    if device.device_type:
        for template in device_templates:
            if template.device_type == device.device_type:
                return template
    return DeviceTemplate(device_type=device.device_type or 'unknown_component', footprint_radius=device.footprint_radius or 18.0, terminal_layout='auto')


def _match_block_template(
    block_name: str | None,
    attribs: dict[str, object],
    device_templates: tuple[DeviceTemplate, ...],
) -> DeviceTemplate | None:
    if not block_name:
        return None
    for template in device_templates:
        if not template.block_name:
            continue
        if not _matches_pattern(block_name, template.block_name, template.match_mode):
            continue
        if template.attrib_equals:
            matched = True
            for key, expected in template.attrib_equals.items():
                actual = attribs.get(key)
                if actual is None or str(actual) != expected:
                    matched = False
                    break
            if not matched:
                continue
        return template
    return None


def _match_text_template(text: str, device_templates: tuple[DeviceTemplate, ...]) -> DeviceTemplate | None:
    template, _ = _match_text_template_with_keyword(text, device_templates)
    return template


def _match_text_template_with_keyword(
    text: str,
    device_templates: tuple[DeviceTemplate, ...],
) -> tuple[DeviceTemplate | None, str | None]:
    normalized = _normalize_text(text)
    lowered = normalized.lower()
    best: tuple[int, int, DeviceTemplate, str] | None = None
    for idx, template in enumerate(device_templates):
        for keyword in template.text_keywords:
            if keyword and keyword.lower() in lowered:
                score = len(keyword)
                if best is None or score > best[0] or (score == best[0] and idx < best[1]):
                    best = (score, idx, template, keyword)
        for pattern in template.label_globs:
            if pattern and fnmatch.fnmatch(lowered, pattern.lower()):
                score = len(pattern.replace('*', '').replace('?', '')) + 1
                if best is None or score > best[0] or (score == best[0] and idx < best[1]):
                    best = (score, idx, template, pattern)
    if best is None:
        return None, None
    return best[2], best[3]


def _build_terminals_from_template(
    *,
    device_id: str,
    center: Point2D,
    entity: CadEntity,
    template: DeviceTemplate,
    source_entity_ids: tuple[str, ...],
) -> tuple[Terminal, ...]:
    rotation_deg = _float_prop(entity, 'gc_50') or 0.0
    scale_x = _float_prop(entity, 'gc_41') or 1.0
    scale_y = _float_prop(entity, 'gc_42') or 1.0
    angle = math.radians(rotation_deg)
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)

    out: list[Terminal] = []
    for idx, terminal_def in enumerate(template.terminals, start=1):
        local_x = terminal_def.x * scale_x
        local_y = terminal_def.y * scale_y
        world_x = center.x + local_x * cos_angle - local_y * sin_angle
        world_y = center.y + local_x * sin_angle + local_y * cos_angle
        out.append(
            Terminal(
                id=f'{device_id}:t{idx}',
                position=Point2D(world_x, world_y),
                name=terminal_def.name,
                source_entity_ids=source_entity_ids,
                confidence=1.0,
            )
        )
    return tuple(out)


def _infer_terminals_near_point(
    *,
    device_id: str,
    center: Point2D,
    wires: list[WireSegment],
    template: DeviceTemplate,
    source_entity_ids: tuple[str, ...],
    rotation_deg: float = 0.0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> tuple[Terminal, ...]:
    footprint_radius = max(4.0, template.footprint_radius)
    search_radius = footprint_radius + max(2.0, footprint_radius * 0.35)
    search_radius2 = search_radius * search_radius
    projection_tol = max(1.5, min(search_radius * 0.22, 12.0))
    endpoint_points: list[Point2D] = []
    projected_points: list[Point2D] = []

    for wire in wires:
        if dist2(center, wire.a) <= search_radius2:
            endpoint_points.append(wire.a)
        if dist2(center, wire.b) <= search_radius2:
            endpoint_points.append(wire.b)
        if distance_point_to_segment(center, wire.a, wire.b) <= projection_tol:
            projected, t = project_point_to_segment(center, wire.a, wire.b)
            if 0.0 < t < 1.0 and dist2(center, projected) <= search_radius2:
                projected_points.append(projected)

    tol = max(1.0, min(search_radius / 8.0, 4.0))
    clustered_endpoints = _cluster_points(endpoint_points, tol=tol)
    clustered_projected = _cluster_points(projected_points, tol=tol)
    min_points = max(1, template.min_terminals)
    candidates = list(clustered_endpoints)
    if len(candidates) < min_points:
        candidates = _merge_candidate_points(candidates, clustered_projected, tol=tol)
    elif template.max_terminals is None or len(candidates) < template.max_terminals:
        candidates = _merge_candidate_points(candidates, clustered_projected, tol=tol)

    limited = _limit_terminal_points(
        candidates,
        center=center,
        max_terminals=template.max_terminals,
        template=template,
        rotation_deg=rotation_deg,
        scale_x=scale_x,
        scale_y=scale_y,
    )
    names = _terminal_names(template, len(limited))
    out: list[Terminal] = []
    for idx, point in enumerate(limited, start=1):
        out.append(
            Terminal(
                id=f'{device_id}:t{idx}',
                position=point,
                name=names[idx - 1],
                source_entity_ids=source_entity_ids,
                confidence=0.75 if point in clustered_endpoints else 0.6,
            )
        )
    return tuple(out)

def _terminal_names(template: DeviceTemplate, count: int) -> list[str | None]:
    names = [terminal.name for terminal in template.terminals if terminal.name]
    if not names:
        return [f'p{idx}' for idx in range(1, count + 1)]
    out: list[str | None] = []
    for idx in range(count):
        if idx < len(names):
            out.append(names[idx])
        else:
            out.append(f'p{idx + 1}')
    return out


def _limit_terminal_points(
    points: list[Point2D],
    *,
    center: Point2D,
    max_terminals: int | None,
    template: DeviceTemplate,
    rotation_deg: float = 0.0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> list[Point2D]:
    if not points:
        return []
    target_count = len(points) if max_terminals is None else min(len(points), max_terminals)
    guided = _template_guided_points(
        points,
        center=center,
        target_count=target_count,
        template=template,
        rotation_deg=rotation_deg,
        scale_x=scale_x,
        scale_y=scale_y,
    )
    if guided:
        return guided
    if max_terminals is None or len(points) <= max_terminals:
        return _sort_terminal_points(points, center=center)
    if max_terminals <= 1:
        return [min(points, key=lambda item: dist(center, item))]
    if max_terminals == 2:
        best_pair: tuple[Point2D, Point2D] | None = None
        best_distance = -1.0
        for idx, left in enumerate(points):
            for right in points[idx + 1 :]:
                candidate_distance = dist(left, right)
                if candidate_distance > best_distance:
                    best_distance = candidate_distance
                    best_pair = (left, right)
        if best_pair is not None:
            return _sort_terminal_points(list(best_pair), center=center)
    ordered = sorted(points, key=lambda item: (-dist(center, item), math.atan2(item.y - center.y, item.x - center.x)))
    return _sort_terminal_points(ordered[:max_terminals], center=center)


def _template_guided_points(
    points: list[Point2D],
    *,
    center: Point2D,
    target_count: int,
    template: DeviceTemplate,
    rotation_deg: float,
    scale_x: float,
    scale_y: float,
) -> list[Point2D]:
    if not points or target_count <= 0:
        return []
    expected = _expected_terminal_points(
        center=center,
        template=template,
        rotation_deg=rotation_deg,
        scale_x=scale_x,
        scale_y=scale_y,
    )
    if expected:
        selected: list[Point2D] = []
        remaining = list(points)
        for expected_point in expected[:target_count]:
            if not remaining:
                break
            best_idx = min(
                range(len(remaining)),
                key=lambda idx: _terminal_match_score(center, remaining[idx], expected_point),
            )
            selected.append(remaining.pop(best_idx))
        if len(selected) < target_count and remaining:
            selected.extend(_sort_terminal_points(remaining, center=center)[: target_count - len(selected)])
        return _sort_terminal_points(selected, center=center)
    if target_count == 2 and template.terminal_layout in {'horizontal', 'vertical'}:
        pair = _select_axis_pair(points, center=center, axis=template.terminal_layout)
        if pair:
            return _sort_terminal_points(pair, center=center)
    return []


def _expected_terminal_points(
    *,
    center: Point2D,
    template: DeviceTemplate,
    rotation_deg: float,
    scale_x: float,
    scale_y: float,
) -> list[Point2D]:
    if not template.terminals:
        return []
    angle = math.radians(rotation_deg)
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    out: list[Point2D] = []
    for terminal_def in template.terminals:
        local_x = terminal_def.x * scale_x
        local_y = terminal_def.y * scale_y
        out.append(
            Point2D(
                center.x + local_x * cos_angle - local_y * sin_angle,
                center.y + local_x * sin_angle + local_y * cos_angle,
            )
        )
    return out


def _terminal_match_score(center: Point2D, actual: Point2D, expected: Point2D) -> float:
    return dist(actual, expected) + abs(dist(center, actual) - dist(center, expected)) * 0.35


def _select_axis_pair(points: list[Point2D], *, center: Point2D, axis: str) -> list[Point2D]:
    if axis == 'horizontal':
        negative = [point for point in points if point.x < center.x]
        positive = [point for point in points if point.x > center.x]
        if negative and positive:
            left = max(negative, key=lambda item: center.x - item.x)
            right = max(positive, key=lambda item: item.x - center.x)
            return [left, right]
    if axis == 'vertical':
        negative = [point for point in points if point.y < center.y]
        positive = [point for point in points if point.y > center.y]
        if negative and positive:
            lower = max(negative, key=lambda item: center.y - item.y)
            upper = max(positive, key=lambda item: item.y - center.y)
            return [lower, upper]
    return []


def _sort_terminal_points(points: list[Point2D], *, center: Point2D) -> list[Point2D]:
    ordered = list(dict.fromkeys(points))
    ordered.sort(key=lambda item: (math.atan2(item.y - center.y, item.x - center.x), dist(center, item)))
    return ordered


def _is_table_context(center: Point2D, texts: list[tuple[str, Point2D, str]], radius: float = 90.0) -> bool:
    radius2 = radius * radius
    header_hits = 0
    nearby_count = 0
    numeric_count = 0
    for _, point, text in texts:
        normalized = _normalize_text(text)
        if not normalized:
            continue
        if dist2(center, point) > radius2:
            continue
        nearby_count += 1
        if any(keyword in normalized for keyword in _TABLE_HEADER_KEYWORDS):
            header_hits += 1
        if normalized.replace('.', '').replace('-', '').isdigit():
            numeric_count += 1
    if header_hits >= 2:
        return True
    return nearby_count >= 10 and numeric_count >= 3

def _merge_candidate_points(primary: list[Point2D], secondary: list[Point2D], *, tol: float) -> list[Point2D]:
    out = list(primary)
    tol2 = tol * tol
    for point in secondary:
        if any(dist2(point, existing) <= tol2 for existing in out):
            continue
        out.append(point)
    return out


def _cluster_points(points: list[Point2D], *, tol: float) -> list[Point2D]:
    if not points:
        return []
    tol2 = tol * tol
    clusters: list[list[Point2D]] = []
    for point in points:
        placed = False
        for cluster in clusters:
            if dist2(point, cluster[0]) <= tol2:
                cluster.append(point)
                placed = True
                break
        if not placed:
            clusters.append([point])
    out: list[Point2D] = []
    for cluster in clusters:
        sx = sum(point.x for point in cluster)
        sy = sum(point.y for point in cluster)
        out.append(Point2D(sx / len(cluster), sy / len(cluster)))
    out.sort(key=lambda item: (item.x, item.y))
    return out


def _nearest_text_label(
    center: Point2D,
    texts: list[tuple[str, Point2D, str]],
    radius: float = 30.0,
) -> str | None:
    best: tuple[float, str] | None = None
    max_d2 = radius * radius
    for _, point, text in texts:
        normalized = _normalize_text(text)
        if not normalized or _should_ignore_text(normalized):
            continue
        current = dist2(center, point)
        if current > max_d2:
            continue
        if best is None or current < best[0]:
            best = (current, normalized)
    return best[1] if best is not None else None


def _surrounding_text_count(center: Point2D, texts: list[tuple[str, Point2D, str]], radius: float) -> int:
    radius2 = radius * radius
    count = 0
    for _, point, text in texts:
        normalized = _normalize_text(text)
        if not normalized:
            continue
        if dist2(center, point) <= radius2:
            count += 1
    return count


def _matches_pattern(value: str, pattern: str, mode: str) -> bool:
    normalized_value = value.strip()
    normalized_pattern = pattern.strip()
    if mode == 'contains':
        return normalized_pattern.lower() in normalized_value.lower()
    if mode == 'glob':
        return fnmatch.fnmatch(normalized_value.lower(), normalized_pattern.lower())
    return normalized_value.lower() == normalized_pattern.lower()


def _normalize_text(text: str) -> str:
    cleaned = str(text or '')
    cleaned = cleaned.replace('^M^J', ' ').replace('\\P', ' ').replace('{', ' ').replace('}', ' ')
    cleaned = re.sub(r'\\[A-Za-z][^;{}]*;', ' ', cleaned)
    cleaned = re.sub(r'%{2,3}[A-Za-z0-9]+', ' ', cleaned)
    cleaned = cleaned.replace('~', ' ')
    cleaned = ' '.join(part for part in cleaned.split() if part)
    return cleaned.strip()


def _should_ignore_text(text: str) -> bool:
    if not text:
        return True
    if text.isdigit():
        return True
    for token in _IGNORE_TEXT_KEYWORDS:
        if token in text:
            return True
    return False


def _point_from_codes(entity: CadEntity, x: str, y: str) -> Point2D | None:
    sx = entity.props.get(f'gc_{x}')
    sy = entity.props.get(f'gc_{y}')
    if sx is None or sy is None:
        return None
    try:
        return Point2D(float(sx), float(sy))
    except (TypeError, ValueError):
        return None


def _float_prop(entity: CadEntity, key: str) -> float | None:
    value = entity.props.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
