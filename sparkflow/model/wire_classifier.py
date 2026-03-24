from __future__ import annotations

import fnmatch

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
                inner_radius = radius * 0.7
                midpoint = Point2D((wire.a.x + wire.b.x) / 2.0, (wire.a.y + wire.b.y) / 2.0)
                if (
                    dist(device.position, wire.a) <= inner_radius
                    and dist(device.position, wire.b) <= inner_radius
                    and dist(device.position, midpoint) <= inner_radius
                    and segment_length(wire.a, wire.b) <= inner_radius * 2.0
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
        if _is_text_dense_table_wire(wire, texts, wire_filter=wire_filter):
            unresolved.append(
                UnresolvedItem(
                    kind='wire_candidate',
                    source_entity_ids=wire.source_entity_ids,
                    reason='导线候选位于文本密集区域且形态接近表格线，已剔除。',
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
    texts: list[tuple[str, Point2D, str]],
    *,
    wire_filter: WireFilter,
) -> bool:
    if not wire_filter.exclude_text_dense_wires or not texts:
        return False
    length = segment_length(wire.a, wire.b)
    if wire_filter.text_dense_max_length > 0 and length > wire_filter.text_dense_max_length:
        return False
    dx = abs(wire.a.x - wire.b.x)
    dy = abs(wire.a.y - wire.b.y)
    if min(dx, dy) > max(1.0, length * 0.15):
        return False
    radius = max(4.0, wire_filter.text_density_radius)
    threshold = max(2, int(wire_filter.text_density_threshold))
    midpoint = Point2D((wire.a.x + wire.b.x) / 2.0, (wire.a.y + wire.b.y) / 2.0)
    midpoint_count = _count_texts_near(midpoint, texts, radius=radius)
    segment_count = _count_texts_near_segment(wire, texts, radius=radius)
    if segment_count < threshold + 1:
        return False
    return midpoint_count >= max(2, threshold - 2)


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


def _point_from_codes(entity: CadEntity, x: str, y: str) -> Point2D | None:
    sx = entity.props.get(f'gc_{x}')
    sy = entity.props.get(f'gc_{y}')
    if sx is None or sy is None:
        return None
    try:
        return Point2D(float(sx), float(sy))
    except (TypeError, ValueError):
        return None
