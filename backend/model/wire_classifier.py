from __future__ import annotations

import fnmatch
import re

from ..cad.entities import CadEntity
from .build_options import WireFilter
from .geometry import dist, distance_point_to_segment, segment_length
from .types import Device, Point2D, UnresolvedItem, WireSegment


def extract_wire_segments(entities: tuple[CadEntity, ...], *, wire_filter: WireFilter | None) -> list[WireSegment]:
    wires: list[WireSegment] = []
    for entity in entities:
        kind = entity.kind.upper()
        if kind == 'LINE':
            _append_line_wire(wires, entity, wire_filter=wire_filter)
        elif kind == 'LWPOLYLINE':
            _append_lwpolyline_wires(wires, entity, wire_filter=wire_filter)
        elif kind == 'POLYLINE':
            _append_polyline_wires(wires, entity, wire_filter=wire_filter)
    return wires


def filter_wire_segments(
    wires: list[WireSegment],
    devices: list[Device],
    texts: list[tuple[str, Point2D, str]],
    *,
    wire_filter: WireFilter | None,
) -> tuple[list[WireSegment], list[UnresolvedItem]]:
    if wire_filter is None:
        return wires, []
    padding = max(0.0, wire_filter.device_radius_padding)
    out: list[WireSegment] = []
    unresolved: list[UnresolvedItem] = []
    for wire in wires:
        skip = False
        if wire_filter.exclude_internal_device_wires and devices:
            for device in devices:
                radius = (device.footprint_radius or 0.0) + padding
                if radius <= 0:
                    continue
                aggressive_factor = 0.2
                if device.device_type in {'transformer', 'load', 'breaker'}:
                    aggressive_factor = 0.95
                elif device.device_type == 'cable_branch_box':
                    aggressive_factor = 0.6
                inner_radius = radius * 0.7
                aggressive_radius = radius + max(2.0, padding)
                aggressive_mid_radius = radius + 1.0
                aggressive_max_length = max(5.0, radius * aggressive_factor)
                midpoint = Point2D((wire.a.x + wire.b.x) / 2.0, (wire.a.y + wire.b.y) / 2.0)
                wire_len = segment_length(wire.a, wire.b)
                if (
                    dist(device.position, wire.a) <= aggressive_radius
                    and dist(device.position, wire.b) <= aggressive_radius
                    and dist(device.position, midpoint) <= aggressive_mid_radius
                    and wire_len <= aggressive_max_length
                ):
                    unresolved.append(
                        UnresolvedItem(
                            kind='wire_candidate',
                            source_entity_ids=wire.source_entity_ids,
                            reason='导线候选位于设备轮廓内且长度较短，已按符号内部短线剔除。',
                            extra={'wire_id': wire.id, 'device_id': device.id},
                        )
                    )
                    skip = True
                    break
                if (
                    dist(device.position, wire.a) <= inner_radius
                    and dist(device.position, wire.b) <= inner_radius
                    and dist(device.position, midpoint) <= inner_radius
                    and wire_len <= inner_radius * 2.0
                ):
                    unresolved.append(
                        UnresolvedItem(
                            kind='wire_candidate',
                            source_entity_ids=wire.source_entity_ids,
                            reason='导线候选落在同一设备轮廓范围内，已按符号内部几何剔除。',
                            extra={'wire_id': wire.id, 'device_id': device.id},
                        )
                    )
                    skip = True
                    break
        if skip:
            continue
        if _is_text_dense_table_wire(wire, wires, devices, texts, wire_filter=wire_filter):
            unresolved.append(
                UnresolvedItem(
                    kind='wire_candidate',
                    source_entity_ids=wire.source_entity_ids,
                    reason='导线候选位于文本密集区域且形态接近表格线，已剔除。',
                    extra={'wire_id': wire.id},
                )
            )
            continue
        if _is_isolated_annotation_wire(wire, wires, devices, texts):
            unresolved.append(
                UnresolvedItem(
                    kind='wire_candidate',
                    source_entity_ids=wire.source_entity_ids,
                    reason='导线候选与真实网络缺少连接，且位于说明/清单文本附近，已按注释残线剔除。',
                    extra={'wire_id': wire.id},
                )
            )
            continue
        if _is_narrow_symbol_ladder_wire(wire, wires, devices, texts):
            unresolved.append(
                UnresolvedItem(
                    kind='wire_candidate',
                    source_entity_ids=wire.source_entity_ids,
                    reason='导线候选属于狭窄高框符号簇，已按器件内部残线剔除。',
                    extra={'wire_id': wire.id},
                )
            )
            continue
        if _is_compact_symbol_cluster_wire(wire, wires, devices, texts):
            unresolved.append(
                UnresolvedItem(
                    kind='wire_candidate',
                    source_entity_ids=wire.source_entity_ids,
                    reason='导线候选属于器件/说明附近的短正交符号簇，已按符号残线剔除。',
                    extra={'wire_id': wire.id},
                )
            )
            continue
        out.append(wire)
    return out, unresolved


def _append_line_wire(wires: list[WireSegment], entity: CadEntity, *, wire_filter: WireFilter | None) -> None:
    if wire_filter is not None and not _wire_entity_allowed(entity, wire_filter):
        return
    a = _point_from_codes(entity, '10', '20')
    b = _point_from_codes(entity, '11', '21')
    if a is None or b is None:
        return
    if wire_filter is not None and wire_filter.min_length > 0 and segment_length(a, b) < wire_filter.min_length:
        return
    wires.append(WireSegment(id=f'wire:{entity.entity_id}', a=a, b=b, source_entity_ids=(entity.entity_id,)))


def _append_lwpolyline_wires(wires: list[WireSegment], entity: CadEntity, *, wire_filter: WireFilter | None) -> None:
    if wire_filter is not None and not _wire_entity_allowed(entity, wire_filter):
        return
    pts = entity.props.get('lwpolyline_xy')
    if not isinstance(pts, list) or len(pts) < 2:
        return
    points: list[Point2D] = []
    for item in pts:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        try:
            points.append(Point2D(float(item[0]), float(item[1])))
        except (TypeError, ValueError):
            continue
    if len(points) < 2:
        return
    closed = bool(entity.props.get('lwpolyline_closed'))
    if closed and wire_filter is not None and wire_filter.exclude_closed_polylines:
        return
    pairs: list[tuple[Point2D, Point2D]] = list(zip(points, points[1:]))
    if closed:
        pairs.append((points[-1], points[0]))
    for idx, (a, b) in enumerate(pairs, start=1):
        if wire_filter is not None and wire_filter.min_length > 0 and segment_length(a, b) < wire_filter.min_length:
            continue
        wires.append(WireSegment(id=f'wire:{entity.entity_id}:{idx}', a=a, b=b, source_entity_ids=(entity.entity_id,)))


def _append_polyline_wires(wires: list[WireSegment], entity: CadEntity, *, wire_filter: WireFilter | None) -> None:
    if wire_filter is not None and not _wire_entity_allowed(entity, wire_filter):
        return
    pts = entity.props.get('polyline_xy')
    if not isinstance(pts, list) or len(pts) < 2:
        return
    points: list[Point2D] = []
    for item in pts:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        try:
            points.append(Point2D(float(item[0]), float(item[1])))
        except (TypeError, ValueError):
            continue
    if len(points) < 2:
        return
    closed = bool(entity.props.get('polyline_closed'))
    if closed and wire_filter is not None and wire_filter.exclude_closed_polylines:
        return
    pairs: list[tuple[Point2D, Point2D]] = list(zip(points, points[1:]))
    if closed:
        pairs.append((points[-1], points[0]))
    for idx, (a, b) in enumerate(pairs, start=1):
        if wire_filter is not None and wire_filter.min_length > 0 and segment_length(a, b) < wire_filter.min_length:
            continue
        wires.append(WireSegment(id=f'wire:{entity.entity_id}:{idx}', a=a, b=b, source_entity_ids=(entity.entity_id,)))


def _is_text_dense_table_wire(
    wire: WireSegment,
    wires: list[WireSegment],
    devices: list[Device],
    texts: list[tuple[str, Point2D, str]],
    *,
    wire_filter: WireFilter,
) -> bool:
    if not wire_filter.exclude_text_dense_wires or not texts:
        return False
    length = segment_length(wire.a, wire.b)
    dx = abs(wire.a.x - wire.b.x)
    dy = abs(wire.a.y - wire.b.y)
    axis_like = min(dx, dy) <= max(1.0, length * 0.15)
    radius = max(4.0, wire_filter.text_density_radius)
    threshold = max(2, int(wire_filter.text_density_threshold))
    marker_limit = max(wire_filter.text_dense_max_length, 120.0)
    midpoint = Point2D((wire.a.x + wire.b.x) / 2.0, (wire.a.y + wire.b.y) / 2.0)
    midpoint_count = _count_texts_near(midpoint, texts, radius=radius)
    segment_count = _count_texts_near_segment(wire, texts, radius=radius)
    endpoint_count = _count_texts_near(wire.a, texts, radius=radius) + _count_texts_near(wire.b, texts, radius=radius)
    marker_count = _count_matching_texts_near_segment(wire, texts, radius=radius, predicate=_is_marker_text)
    note_count = _count_matching_texts_near_segment(wire, texts, radius=radius, predicate=_looks_like_auxiliary_text)
    header_count = _count_matching_texts_near_segment(wire, texts, radius=radius, predicate=_is_table_header_text)
    electrical_count = _count_matching_texts_near_segment(wire, texts, radius=radius, predicate=_looks_like_electrical_text)
    parallel_band = _parallel_text_band_cluster_size(wire, wires)
    if _segment_near_device_type(wire, devices, device_type='cable_branch_box', radius=max(60.0, min(140.0, length * 0.9))):
        return False
    if not axis_like and marker_count < 3 and note_count < 2:
        return False
    if length > marker_limit:
        if not axis_like or parallel_band < 4:
            return False
        if segment_count < max(5, threshold):
            return False
        if header_count >= 2:
            return True
        if note_count >= 1 and segment_count >= max(4, threshold - 1):
            return True
        if marker_count >= max(2, threshold - 2) and segment_count >= max(5, threshold):
            return True
        if electrical_count >= max(4, threshold - 1) and midpoint_count >= max(2, threshold - 2):
            return True
        return endpoint_count >= threshold + 1 and parallel_band >= 6
    if segment_count < threshold + 1 and endpoint_count < threshold + 2 and marker_count < 3 and note_count < 2:
        return False
    if length <= wire_filter.text_dense_max_length and (
        midpoint_count >= max(2, threshold - 2) or endpoint_count >= threshold + 2
    ):
        return True
    if axis_like and header_count >= 3 and electrical_count <= 1 and segment_count >= max(6, threshold + 1):
        return True
    if marker_count >= max(3, threshold - 1) and segment_count >= max(4, threshold - 1):
        return True
    return note_count >= 2 and segment_count >= max(3, threshold - 2)


def _is_isolated_annotation_wire(
    wire: WireSegment,
    wires: list[WireSegment],
    devices: list[Device],
    texts: list[tuple[str, Point2D, str]],
) -> bool:
    length = segment_length(wire.a, wire.b)
    if length < 20.0 or length > 140.0:
        return False
    if _count_device_terminals_near_segment(wire, devices, radius=10.0) > 1:
        return False
    if _connected_wire_neighbor_count(wire, wires, tol=1.5) > 0:
        return False
    aux_count = _count_matching_texts_near_segment(wire, texts, radius=26.0, predicate=_looks_like_auxiliary_text)
    header_count = _count_matching_texts_near_segment(wire, texts, radius=26.0, predicate=_is_table_header_text)
    marker_count = _count_matching_texts_near_segment(wire, texts, radius=26.0, predicate=_is_marker_text)
    electrical_count = _count_matching_texts_near_segment(wire, texts, radius=26.0, predicate=_looks_like_electrical_text)
    segment_count = _count_texts_near_segment(wire, texts, radius=26.0)
    parallel_band = _parallel_text_band_cluster_size(wire, wires)
    if aux_count >= 1 and segment_count >= 1:
        return True
    if header_count >= 1 and segment_count >= 2:
        return True
    if parallel_band >= 2 and segment_count >= 4 and (marker_count >= 2 or electrical_count >= 2):
        return True
    return False


def _is_compact_symbol_cluster_wire(
    wire: WireSegment,
    wires: list[WireSegment],
    devices: list[Device],
    texts: list[tuple[str, Point2D, str]],
) -> bool:
    wire_len = segment_length(wire.a, wire.b)
    if wire_len > 40.0:
        return False
    midpoint = Point2D((wire.a.x + wire.b.x) / 2.0, (wire.a.y + wire.b.y) / 2.0)
    cluster = [wire]
    horizontal = 0
    vertical = 0
    short_count = 0
    for other in wires:
        if other is wire:
            continue
        other_len = segment_length(other.a, other.b)
        if other_len > 40.0:
            continue
        other_mid = Point2D((other.a.x + other.b.x) / 2.0, (other.a.y + other.b.y) / 2.0)
        endpoint_gap = min(
            dist(wire.a, other.a),
            dist(wire.a, other.b),
            dist(wire.b, other.a),
            dist(wire.b, other.b),
        )
        if other is not wire and dist(midpoint, other_mid) > 32.0 and endpoint_gap > 16.0:
            continue
        cluster.append(other)
    if len(cluster) < 4:
        return False

    xs = [point.x for item in cluster for point in (item.a, item.b)]
    ys = [point.y for item in cluster for point in (item.a, item.b)]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if width > 140.0 or height > 90.0:
        return False

    for item in cluster:
        item_len = segment_length(item.a, item.b)
        dx = abs(item.a.x - item.b.x)
        dy = abs(item.a.y - item.b.y)
        if dx <= max(1.5, item_len * 0.18):
            vertical += 1
        if dy <= max(1.5, item_len * 0.18):
            horizontal += 1
        if item_len <= 8.0:
            short_count += 1
    if horizontal < 1 or vertical < 1 or short_count < 2:
        return False

    near_device = any(
        _cluster_near_device(midpoint, device)
        for device in devices
        if device.device_type in {'breaker', 'transformer', 'load', 'busbar', 'switchgear_unit', 'cable_branch_box'}
    )
    aux_count = _count_matching_texts_near_segment(wire, texts, radius=42.0, predicate=_looks_like_auxiliary_text)
    electrical_count = _count_matching_texts_near_segment(wire, texts, radius=42.0, predicate=_looks_like_electrical_text)
    return near_device or aux_count >= 1 or electrical_count >= 2


def _is_narrow_symbol_ladder_wire(
    wire: WireSegment,
    wires: list[WireSegment],
    devices: list[Device],
    texts: list[tuple[str, Point2D, str]],
) -> bool:
    midpoint = Point2D((wire.a.x + wire.b.x) / 2.0, (wire.a.y + wire.b.y) / 2.0)
    cluster = [wire]
    for other in wires:
        if other is wire:
            continue
        other_mid = Point2D((other.a.x + other.b.x) / 2.0, (other.a.y + other.b.y) / 2.0)
        endpoint_gap = min(
            dist(wire.a, other.a),
            dist(wire.a, other.b),
            dist(wire.b, other.a),
            dist(wire.b, other.b),
        )
        if (
            dist(midpoint, other_mid) <= 90.0
            or endpoint_gap <= 24.0
            or (abs(midpoint.x - other_mid.x) <= 24.0 and abs(midpoint.y - other_mid.y) <= 170.0)
        ):
            cluster.append(other)
    if len(cluster) < 5:
        return False

    xs = [point.x for item in cluster for point in (item.a, item.b)]
    ys = [point.y for item in cluster for point in (item.a, item.b)]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if width > 70.0 or height < 30.0 or height > 220.0:
        return False

    long_vertical = 0
    short_wires = 0
    horizontal = 0
    for item in cluster:
        item_len = segment_length(item.a, item.b)
        dx = abs(item.a.x - item.b.x)
        dy = abs(item.a.y - item.b.y)
        if dx <= max(1.5, item_len * 0.12) and item_len >= 40.0:
            long_vertical += 1
        if dy <= max(1.5, item_len * 0.12):
            horizontal += 1
        if item_len <= 20.0:
            short_wires += 1
    if long_vertical < 2 or short_wires < 3 or horizontal < 1:
        return False

    if _count_device_terminals_near_segment(wire, devices, radius=10.0) > 1:
        return False
    if _count_texts_near(midpoint, texts, radius=28.0) > 1:
        return False
    return True


def _cluster_near_device(point: Point2D, device: Device) -> bool:
    radius = max(24.0, (device.footprint_radius or 0.0) * 1.8)
    if dist(point, device.position) <= radius:
        return True
    for terminal in device.terminals:
        if dist(point, terminal.position) <= max(18.0, radius * 0.9):
            return True
    return False


def _parallel_text_band_cluster_size(wire: WireSegment, wires: list[WireSegment]) -> int:
    length = segment_length(wire.a, wire.b)
    if length <= 0:
        return 0
    dx = abs(wire.a.x - wire.b.x)
    dy = abs(wire.a.y - wire.b.y)
    horizontal = dy <= max(1.5, length * 0.08)
    vertical = dx <= max(1.5, length * 0.08)
    if not horizontal and not vertical:
        return 0
    count = 1
    for other in wires:
        if other is wire:
            continue
        other_len = segment_length(other.a, other.b)
        if other_len <= 0:
            continue
        other_dx = abs(other.a.x - other.b.x)
        other_dy = abs(other.a.y - other.b.y)
        if horizontal and other_dy > max(1.5, other_len * 0.08):
            continue
        if vertical and other_dx > max(1.5, other_len * 0.08):
            continue
        if abs(other_len - length) > max(18.0, length * 0.18):
            continue
        if horizontal:
            gap = abs(((wire.a.y + wire.b.y) / 2.0) - ((other.a.y + other.b.y) / 2.0))
            overlap = _axis_overlap(sorted((wire.a.x, wire.b.x)), sorted((other.a.x, other.b.x)))
        else:
            gap = abs(((wire.a.x + wire.b.x) / 2.0) - ((other.a.x + other.b.x) / 2.0))
            overlap = _axis_overlap(sorted((wire.a.y, wire.b.y)), sorted((other.a.y, other.b.y)))
        if gap > max(72.0, min(120.0, length * 0.45)):
            continue
        if overlap < min(length, other_len) * 0.72:
            continue
        count += 1
    return count


def _count_device_terminals_near_segment(wire: WireSegment, devices: list[Device], *, radius: float) -> int:
    count = 0
    for device in devices:
        for terminal in device.terminals:
            if distance_point_to_segment(terminal.position, wire.a, wire.b) <= radius:
                count += 1
    return count


def _segment_near_device_type(wire: WireSegment, devices: list[Device], *, device_type: str, radius: float) -> bool:
    for device in devices:
        if device.device_type != device_type:
            continue
        if distance_point_to_segment(device.position, wire.a, wire.b) <= radius:
            return True
    return False


def _connected_wire_neighbor_count(wire: WireSegment, wires: list[WireSegment], *, tol: float) -> int:
    count = 0
    for other in wires:
        if other is wire:
            continue
        if (
            dist(wire.a, other.a) <= tol
            or dist(wire.a, other.b) <= tol
            or dist(wire.b, other.a) <= tol
            or dist(wire.b, other.b) <= tol
        ):
            count += 1
    return count


def _axis_overlap(left: list[float], right: list[float]) -> float:
    start = max(left[0], right[0])
    end = min(left[1], right[1])
    return max(0.0, end - start)


def _count_texts_near(center: Point2D, texts: list[tuple[str, Point2D, str]], *, radius: float) -> int:
    radius2 = radius * radius
    count = 0
    for _, point, text in texts:
        if not isinstance(text, str) or not text.strip():
            continue
        dx = point.x - center.x
        dy = point.y - center.y
        if dx * dx + dy * dy <= radius2:
            count += 1
    return count


def _count_texts_near_segment(wire: WireSegment, texts: list[tuple[str, Point2D, str]], *, radius: float) -> int:
    count = 0
    for _, point, text in texts:
        if not isinstance(text, str) or not text.strip():
            continue
        if distance_point_to_segment(point, wire.a, wire.b) <= radius:
            count += 1
    return count


def _count_matching_texts_near_segment(
    wire: WireSegment,
    texts: list[tuple[str, Point2D, str]],
    *,
    radius: float,
    predicate,
) -> int:
    count = 0
    for _, point, text in texts:
        if not isinstance(text, str) or not text.strip():
            continue
        normalized = _normalize_text(text)
        if not normalized or distance_point_to_segment(point, wire.a, wire.b) > radius:
            continue
        if predicate(normalized):
            count += 1
    return count


def _wire_entity_allowed(entity: CadEntity, wire_filter: WireFilter) -> bool:
    layer = entity.props.get('gc_8')
    ltype = entity.props.get('gc_6')
    layer_s = str(layer) if isinstance(layer, str) else ''
    ltype_s = str(ltype) if isinstance(ltype, str) else ''
    if wire_filter.include_layers and not _match_any(layer_s, wire_filter.include_layers):
        return False
    if wire_filter.exclude_layers and _match_any(layer_s, wire_filter.exclude_layers):
        return False
    if wire_filter.include_linetypes and not _match_any(ltype_s, wire_filter.include_linetypes):
        return False
    if wire_filter.exclude_linetypes and _match_any(ltype_s, wire_filter.exclude_linetypes):
        return False
    return True


def _match_any(value: str, patterns: tuple[str, ...]) -> bool:
    lowered = value.lower()
    for pattern in patterns:
        current = pattern.lower()
        if not current:
            continue
        if '*' in current or '?' in current:
            if fnmatch.fnmatch(lowered, current):
                return True
        elif current == lowered or current in lowered:
            return True
    return False


def _normalize_text(text: str) -> str:
    cleaned = str(text or '')
    cleaned = cleaned.replace('^M^J', ' ').replace('\\P', ' ').replace('{', ' ').replace('}', ' ')
    cleaned = re.sub(r'\\[A-Za-z][^;{}]*;', ' ', cleaned)
    cleaned = re.sub(r'%{2,3}[A-Za-z0-9]+', ' ', cleaned)
    cleaned = cleaned.replace('~', ' ')
    cleaned = ' '.join(part for part in cleaned.split() if part)
    return cleaned.strip()


def _compact_text(text: str) -> str:
    return ''.join(str(text or '').split())


def _is_marker_text(text: str) -> bool:
    compact = _compact_text(text)
    if not compact or len(compact) > 2:
        return False
    return compact.isascii() and compact.isalnum()


def _is_table_header_text(text: str) -> bool:
    compact = _compact_text(text)
    return any(token in compact for token in ('序号', '代号', '名称', '规格及型号', '数量', '单位', '备注'))


def _looks_like_electrical_text(text: str) -> bool:
    compact = _compact_text(text)
    return any(
        token in compact
        for token in ('QF', 'QS', '进线', '出线', '馈线', '母线', '柜', '变压器', '主变', 'TA', 'SPD', 'BK', '电能表', '分支箱')
    )


def _looks_like_auxiliary_text(text: str) -> bool:
    compact = _compact_text(text)
    if not compact:
        return False
    if compact.startswith('图') and any(token in compact for token in ('系统图', '电气图', '布置图', '杆型图', '安装图', '安装示意', '加工图')):
        return True
    if compact.startswith('说明'):
        return True
    if re.match(r'^\d+[.、].{4,}', compact):
        return True
    return any(
        token in compact
        for token in ('本图', '接地', '接地系统', '备注', '数量', '单位', '采用', '连接', '横担', '安装横担', '引上线', '调整', '配置', '外壳')
    )


def _point_from_codes(entity: CadEntity, x: str, y: str) -> Point2D | None:
    sx = entity.props.get(f'gc_{x}')
    sy = entity.props.get(f'gc_{y}')
    if sx is None or sy is None:
        return None
    try:
        return Point2D(float(sx), float(sy))
    except (TypeError, ValueError):
        return None
