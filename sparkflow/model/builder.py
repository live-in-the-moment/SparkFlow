from __future__ import annotations

from .build_options import ModelBuildOptions, effective_device_templates
from .symbol_recognition import attach_nearby_terminals, recognize_devices
from .types import Point2D, SystemModel
from .wire_classifier import extract_wire_segments, filter_wire_segments
from ..cad.entities import CadEntity


def build_system_model(entities: tuple[CadEntity, ...], *, options: ModelBuildOptions | None = None) -> SystemModel:
    texts: list[tuple[str, Point2D, str]] = []
    inserts: list[CadEntity] = []
    entity_index: dict[str, str] = {entity.entity_id: entity.kind for entity in entities}

    for entity in entities:
        kind = entity.kind.upper()
        if kind in {'TEXT', 'MTEXT'}:
            point = _point_from_codes(entity, '10', '20')
            text = entity.props.get('gc_1')
            if point is None or text is None:
                continue
            texts.append((f'text:{entity.entity_id}', point, str(text)))
        elif kind == 'INSERT':
            inserts.append(entity)

    wire_filter = options.wire_filter if options else None
    raw_wires = extract_wire_segments(entities, wire_filter=wire_filter)
    device_templates = effective_device_templates(options)

    devices, unresolved = recognize_devices(
        inserts,
        texts,
        raw_wires,
        device_templates=device_templates,
    )
    wires, wire_unresolved = filter_wire_segments(raw_wires, devices, texts, wire_filter=wire_filter)
    devices, terminal_unresolved = attach_nearby_terminals(devices, wires, device_templates=device_templates)
    unresolved.extend(wire_unresolved)
    unresolved.extend(terminal_unresolved)

    return SystemModel(
        wires=tuple(wires),
        devices=tuple(devices),
        texts=tuple(texts),
        entity_index=entity_index,
        unresolved=tuple(unresolved),
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
