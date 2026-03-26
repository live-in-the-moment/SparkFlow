from __future__ import annotations

import fnmatch
import math
import re
from dataclasses import dataclass

from ..cad.entities import CadEntity
from .build_options import DeviceTemplate, TerminalDef
from .geometry import dist, dist2, distance_point_to_segment, project_point_to_segment, segment_length
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
_AUXILIARY_DRAWING_TOKENS = (
    '系统图',
    '电气图',
    '布置图',
    '杆型图',
    '平面图',
    '剖面图',
    '安装图',
    '安装示意',
    '安装示意图',
    '布置加工图',
    '加工图',
    '方案图',
)
_DEVICE_LABEL_TRANSLATION = str.maketrans(
    {
        '～': '~',
        '—': '-',
        '－': '-',
        '＃': '#',
        '／': '/',
        '（': '(',
        '）': ')',
    }
)


@dataclass(frozen=True)
class _TextCandidate:
    text_id: str
    point: Point2D
    text: str
    template: DeviceTemplate
    keyword: str
    table_override: bool = False


@dataclass(frozen=True)
class _TextGroup:
    template: DeviceTemplate
    items: tuple[_TextCandidate, ...]
    center: Point2D
    label: str
    table_override: bool = False


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

    for group in _build_text_groups(texts, wires=wires, device_templates=device_templates):
        if _group_is_covered_by_existing_devices(group, devices):
            continue
        if not group.table_override and _surrounding_text_count(
            group.center, texts, radius=max(18.0, group.template.text_group_radius * 2.0)
        ) > 6:
            continue
        if any(
            dist(device.position, group.center) <= max(group.template.footprint_radius * 0.6, 8.0)
            and (
                not group.label
                or (device.label is not None and _labels_equivalent(device.label, group.label))
            )
            for device in devices
        ):
            continue
        terminals = _infer_terminals_near_point(
            device_id=f'textdev:{group.items[0].text_id}',
            center=group.center,
            wires=wires,
            template=group.template,
            source_entity_ids=tuple(item.text_id for item in group.items),
        )
        if group.template.device_type == 'cable_branch_box' and len(terminals) < max(1, group.template.min_terminals):
            global_terminals = _infer_branch_box_terminals_from_global_wires(
                device_id=f'textdev:{group.items[0].text_id}',
                wires=wires,
                template=group.template,
                source_entity_ids=tuple(item.text_id for item in group.items),
            )
            if len(global_terminals) > len(terminals):
                terminals = global_terminals
        if _merge_text_group_into_existing_device(group=group, terminals=terminals, devices=devices):
            continue
        if len(terminals) < max(1, group.template.min_terminals):
            unresolved.append(
                UnresolvedItem(
                    kind='terminal_anchor',
                    source_entity_ids=tuple(item.text_id for item in group.items),
                    reason='文本设备候选未识别到足够端子锚点，已跳过。',
                    extra={'device_type': group.template.device_type, 'label': group.label},
                )
            )
            if not _can_materialize_text_device_without_terminals(group):
                continue
            terminals = ()
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
        template = _template_for_device(device, device_templates)
        terminals = device.terminals
        if not terminals:
            terminals = _infer_terminals_near_point(
                device_id=device.id,
                center=device.position,
                wires=wires,
                template=template,
                source_entity_ids=device.source_entity_ids,
            )
        if device.device_type == 'cable_branch_box' and len(terminals) < 3:
            global_terminals = _infer_branch_box_terminals_from_global_wires(
                device_id=device.id,
                wires=wires,
                template=template,
                source_entity_ids=device.source_entity_ids,
            )
            if len(global_terminals) > len(terminals):
                terminals = global_terminals
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


def enrich_contextual_switchgear(devices: list[Device]) -> list[Device]:
    if not devices:
        return []

    enriched = _contextualize_current_rating_breakers(devices)
    proxy_devices = _infer_proxy_incoming_switchgear_devices(enriched)
    if proxy_devices:
        enriched.extend(proxy_devices)

    busbars = [device for device in enriched if device.device_type == 'busbar' and device.terminals]
    transformers = [device for device in enriched if device.device_type == 'transformer' and device.terminals]
    downstream_devices = [
        device
        for device in enriched
        if device.device_type in {'load', 'breaker', 'feeder', 'cable_branch_box'} and not _is_current_rating_label(device.label)
    ]
    out: list[Device] = []
    for device in enriched:
        if device.device_type != 'switchgear_unit':
            out.append(device)
            continue
        if device.id.startswith('proxy:'):
            out.append(device)
            continue
        role = _switchgear_role(device.label)
        context_terminals: tuple[Terminal, ...] = ()
        if role == 'incoming':
            context_terminals = _incoming_switchgear_context_terminals(
                device,
                busbars=busbars,
                transformers=transformers,
            )
        elif role == 'outgoing':
            context_terminals = _outgoing_switchgear_context_terminals(
                device,
                busbars=busbars,
                downstream_devices=downstream_devices,
            )
        elif role == 'tie':
            context_terminals = _tie_switchgear_context_terminals(device, busbars=busbars)
        if len(context_terminals) >= 2:
            out.append(
                Device(
                    id=device.id,
                    position=device.position,
                    label=device.label,
                    device_type=device.device_type,
                    terminals=context_terminals,
                    block_name=device.block_name,
                    source_entity_ids=device.source_entity_ids,
                    footprint_radius=device.footprint_radius,
                )
            )
            continue
        out.append(device)
    return out


def _contextualize_current_rating_breakers(devices: list[Device]) -> list[Device]:
    switchgears = [device for device in devices if device.device_type == 'switchgear_unit']
    busbars = [device for device in devices if device.device_type == 'busbar' and device.terminals]
    transformers = [device for device in devices if device.device_type == 'transformer' and device.terminals]
    if not busbars or not transformers:
        return list(devices)

    out: list[Device] = []
    for device in devices:
        if device.device_type != 'breaker' or not _is_current_rating_label(device.label):
            out.append(device)
            continue
        if any(dist(device.position, switchgear.position) <= 80.0 for switchgear in switchgears):
            out.append(device)
            continue
        transformer = _best_transformer_context_device(
            device.position,
            owner_label=device.label,
            transformers=transformers,
            max_distance=120.0,
        )
        busbar = _best_busbar_context_device(
            device.position,
            owner_label=transformer.label if transformer is not None else device.label,
            busbars=busbars,
            max_distance=120.0,
        )
        if transformer is None or busbar is None:
            out.append(device)
            continue
        transformer_terminal = _nearest_terminal(transformer, device.position, preferred_names=('hv',))
        busbar_terminal = _nearest_terminal(busbar, device.position)
        if transformer_terminal is None or busbar_terminal is None:
            out.append(device)
            continue
        if dist(transformer_terminal.position, busbar_terminal.position) < 6.0:
            out.append(device)
            continue
        source_ids = tuple(
            dict.fromkeys(
                device.source_entity_ids
                + transformer.source_entity_ids
                + busbar.source_entity_ids
            )
        )
        out.append(
            Device(
                id=device.id,
                position=device.position,
                label=device.label,
                device_type=device.device_type,
                terminals=_context_terminals(
                    device_id=device.id,
                    pairs=(
                        ('source', transformer_terminal),
                        ('busbar', busbar_terminal),
                    ),
                    source_entity_ids=source_ids,
                ),
                block_name=device.block_name,
                source_entity_ids=source_ids,
                footprint_radius=device.footprint_radius,
            )
        )
    return out


def _infer_proxy_incoming_switchgear_devices(devices: list[Device]) -> list[Device]:
    switchgears = [device for device in devices if device.device_type == 'switchgear_unit']
    busbars = [device for device in devices if device.device_type == 'busbar' and device.terminals]
    transformers = [device for device in devices if device.device_type == 'transformer' and device.terminals]
    proxies: list[Device] = []
    for breaker in devices:
        if breaker.device_type != 'breaker' or not _is_current_rating_label(breaker.label):
            continue
        if any(dist(breaker.position, switchgear.position) <= 80.0 for switchgear in switchgears):
            continue
        transformer = _best_transformer_context_device(
            breaker.position,
            owner_label=breaker.label,
            transformers=transformers,
            max_distance=120.0,
        )
        busbar = _best_busbar_context_device(
            breaker.position,
            owner_label=transformer.label if transformer is not None else breaker.label,
            busbars=busbars,
            max_distance=120.0,
        )
        if transformer is None or busbar is None:
            continue
        transformer_terminal = _nearest_terminal(transformer, breaker.position, preferred_names=('hv',))
        busbar_terminal = _nearest_terminal(busbar, breaker.position)
        if transformer_terminal is None or busbar_terminal is None:
            continue
        if dist(transformer_terminal.position, busbar_terminal.position) < 6.0:
            continue
        source_ids = tuple(
            dict.fromkeys(
                breaker.source_entity_ids
                + transformer.source_entity_ids
                + busbar.source_entity_ids
            )
        )
        label = _proxy_incoming_switchgear_label(transformer.label)
        proxies.append(
            Device(
                id=f'proxy:{breaker.id}:incoming_switchgear',
                position=breaker.position,
                label=label,
                device_type='switchgear_unit',
                terminals=_context_terminals(
                    device_id=f'proxy:{breaker.id}:incoming_switchgear',
                    pairs=(
                        ('source', transformer_terminal),
                        ('busbar', busbar_terminal),
                    ),
                    source_entity_ids=source_ids,
                ),
                block_name=None,
                source_entity_ids=source_ids,
                footprint_radius=max(24.0, breaker.footprint_radius or 0.0),
            )
        )
    return proxies


def _incoming_switchgear_context_terminals(
    device: Device,
    *,
    busbars: list[Device],
    transformers: list[Device],
) -> tuple[Terminal, ...]:
    transformer = _best_transformer_context_device(
        device.position,
        owner_label=device.label,
        transformers=transformers,
        max_distance=120.0,
    )
    busbar = _best_busbar_context_device(
        device.position,
        owner_label=device.label,
        busbars=busbars,
        max_distance=120.0,
    )
    if transformer is None or busbar is None:
        return ()
    transformer_terminal = _nearest_terminal(transformer, device.position)
    busbar_terminal = _nearest_terminal(busbar, device.position)
    if transformer_terminal is None or busbar_terminal is None:
        return ()
    if dist(transformer_terminal.position, busbar_terminal.position) < 6.0:
        return ()
    source_ids = tuple(dict.fromkeys(device.source_entity_ids + transformer.source_entity_ids + busbar.source_entity_ids))
    return _context_terminals(
        device_id=device.id,
        pairs=(
            ('source', transformer_terminal),
            ('busbar', busbar_terminal),
        ),
        source_entity_ids=source_ids,
    )


def _tie_switchgear_context_terminals(
    device: Device,
    *,
    busbars: list[Device],
) -> tuple[Terminal, ...]:
    pair = _best_tie_busbar_pair(device, busbars=busbars)
    if pair is None:
        return ()
    left_busbar, right_busbar = pair
    left_terminal = _nearest_terminal(left_busbar, device.position)
    right_terminal = _nearest_terminal(right_busbar, device.position)
    if left_terminal is None or right_terminal is None:
        return ()
    if dist(left_terminal.position, right_terminal.position) < 6.0:
        return ()
    source_ids = tuple(
        dict.fromkeys(device.source_entity_ids + left_busbar.source_entity_ids + right_busbar.source_entity_ids)
    )
    return _context_terminals(
        device_id=device.id,
        pairs=(
            ('left', left_terminal),
            ('right', right_terminal),
        ),
        source_entity_ids=source_ids,
    )


def _outgoing_switchgear_context_terminals(
    device: Device,
    *,
    busbars: list[Device],
    downstream_devices: list[Device],
) -> tuple[Terminal, ...]:
    busbar = _best_busbar_context_device(
        device.position,
        owner_label=device.label,
        busbars=busbars,
        max_distance=120.0,
    )
    if busbar is None:
        return ()
    busbar_terminal = _nearest_terminal(busbar, device.position)
    if busbar_terminal is None:
        return ()
    downstream_terminal, downstream_source_ids = _best_outgoing_downstream_terminal(
        device,
        busbar_terminal=busbar_terminal,
        downstream_devices=downstream_devices,
    )
    if downstream_terminal is None:
        return ()
    source_ids = tuple(
        dict.fromkeys(
            device.source_entity_ids
            + busbar.source_entity_ids
            + downstream_source_ids
            + downstream_terminal.source_entity_ids
        )
    )
    return _context_terminals(
        device_id=device.id,
        pairs=(
            ('busbar', busbar_terminal),
            ('load', downstream_terminal),
        ),
        source_entity_ids=source_ids,
    )


def _best_outgoing_downstream_terminal(
    device: Device,
    *,
    busbar_terminal: Terminal,
    downstream_devices: list[Device],
) -> tuple[Terminal | None, tuple[str, ...]]:
    best: tuple[float, Terminal, tuple[str, ...]] | None = None
    for candidate in downstream_devices:
        if candidate.id == device.id or not candidate.terminals:
            continue
        terminal = _nearest_terminal(candidate, device.position)
        if terminal is None:
            continue
        distance = dist(device.position, terminal.position)
        if distance > 120.0:
            continue
        if dist(busbar_terminal.position, terminal.position) < 6.0:
            continue
        score = distance
        if candidate.device_type == 'breaker':
            score -= 10.0
        elif candidate.device_type == 'load':
            score -= 7.0
        elif candidate.device_type == 'feeder':
            score -= 6.0
        elif candidate.device_type == 'cable_branch_box':
            score -= 5.0
        if abs(candidate.position.x - device.position.x) <= 28.0:
            score -= 6.0
        if abs(candidate.position.y - device.position.y) <= 28.0:
            score -= 3.0
        source_ids = tuple(dict.fromkeys(candidate.source_entity_ids + terminal.source_entity_ids))
        if best is None or score < best[0]:
            best = (score, terminal, source_ids)

    if best is not None:
        return best[1], best[2]

    fallback = [
        terminal
        for terminal in device.terminals
        if dist(terminal.position, busbar_terminal.position) >= 6.0
    ]
    if not fallback:
        return None, ()
    terminal = max(fallback, key=lambda item: dist(item.position, busbar_terminal.position))
    return terminal, tuple(dict.fromkeys(device.source_entity_ids + terminal.source_entity_ids))


def _best_transformer_context_device(
    origin: Point2D,
    *,
    owner_label: str | None,
    transformers: list[Device],
    max_distance: float,
) -> Device | None:
    owner_tokens = _numeric_tag_tokens(owner_label)
    best: tuple[float, Device] | None = None
    for transformer in transformers:
        label = transformer.label or ''
        compact = _compact_text(label)
        if '电流互感器' in compact:
            continue
        terminal = _nearest_terminal(transformer, origin)
        if terminal is None:
            continue
        score = dist(origin, terminal.position)
        if score > max_distance:
            continue
        if owner_tokens and owner_tokens & _numeric_tag_tokens(label):
            score -= 18.0
        if '主变' in compact:
            score -= 12.0
        elif '变压器' in compact:
            score -= 8.0
        if best is None or score < best[0]:
            best = (score, transformer)
    return best[1] if best is not None else None


def _best_busbar_context_device(
    origin: Point2D,
    *,
    owner_label: str | None,
    busbars: list[Device],
    max_distance: float,
) -> Device | None:
    preferred_tokens = _preferred_busbar_segment_tokens(owner_label)
    best: tuple[float, Device] | None = None
    for busbar in busbars:
        terminal = _nearest_terminal(busbar, origin)
        if terminal is None:
            continue
        score = dist(origin, terminal.position)
        if score > max_distance:
            continue
        token = _busbar_segment_token(busbar.label)
        if token and token in preferred_tokens:
            score -= 16.0
        if '母线' in _compact_text(busbar.label or ''):
            score -= 4.0
        if best is None or score < best[0]:
            best = (score, busbar)
    return best[1] if best is not None else None


def _best_tie_busbar_pair(device: Device, *, busbars: list[Device]) -> tuple[Device, Device] | None:
    candidates: list[tuple[float, Device, Terminal]] = []
    for busbar in busbars:
        terminal = _nearest_terminal(busbar, device.position)
        if terminal is None:
            continue
        distance = dist(device.position, terminal.position)
        if distance > 160.0:
            continue
        candidates.append((distance, busbar, terminal))
    if len(candidates) < 2:
        return None

    left = [
        item for item in candidates if item[2].position.x <= device.position.x - 2.0
    ]
    right = [
        item for item in candidates if item[2].position.x >= device.position.x + 2.0
    ]
    if left and right:
        left_busbar = min(left, key=lambda item: item[0])[1]
        right_busbar = min(right, key=lambda item: item[0])[1]
        if left_busbar.id != right_busbar.id:
            return left_busbar, right_busbar

    ordered = sorted(candidates, key=lambda item: (item[0], item[1].id))
    best_pair: tuple[Device, Device] | None = None
    best_score: tuple[int, float] | None = None
    for idx, (_, first_busbar, _) in enumerate(ordered):
        for _, second_busbar, _ in ordered[idx + 1 :]:
            if first_busbar.id == second_busbar.id:
                continue
            first_token = _busbar_segment_token(first_busbar.label)
            second_token = _busbar_segment_token(second_busbar.label)
            same_segment = int(bool(first_token and second_token and first_token == second_token))
            spread = dist(first_busbar.position, second_busbar.position)
            score = (same_segment, -spread)
            if best_score is None or score < best_score:
                best_score = score
                best_pair = (first_busbar, second_busbar)
    return best_pair


def _context_terminals(
    *,
    device_id: str,
    pairs: tuple[tuple[str, Terminal], ...],
    source_entity_ids: tuple[str, ...],
) -> tuple[Terminal, ...]:
    terminals: list[Terminal] = []
    for idx, (name, terminal) in enumerate(pairs, start=1):
        terminals.append(
            Terminal(
                id=f'{device_id}:ctx{idx}',
                position=terminal.position,
                name=name,
                source_entity_ids=source_entity_ids or terminal.source_entity_ids,
                confidence=min(1.0, (terminal.confidence or 0.85) + 0.05),
            )
        )
    return tuple(terminals)


def _nearest_terminal(
    device: Device,
    point: Point2D,
    *,
    preferred_names: tuple[str, ...] = (),
) -> Terminal | None:
    if not device.terminals:
        return None
    lowered_preferences = {name.lower() for name in preferred_names if name}
    if lowered_preferences:
        matching = [
            terminal
            for terminal in device.terminals
            if (terminal.name or '').lower() in lowered_preferences
        ]
        if matching:
            return min(matching, key=lambda terminal: dist(point, terminal.position))
    return min(device.terminals, key=lambda terminal: dist(point, terminal.position))


def _proxy_incoming_switchgear_label(transformer_label: str | None) -> str:
    tokens = sorted(_numeric_tag_tokens(transformer_label))
    prefix = tokens[0] if tokens else ''
    return f'{prefix}进线柜' if prefix else '进线柜'


def _switchgear_role(label: str | None) -> str | None:
    compact = _compact_text(label)
    if not compact:
        return None
    if '联络柜' in compact:
        return 'tie'
    if '进线' in compact and '柜' in compact:
        return 'incoming'
    if '出线' in compact and '柜' in compact:
        return 'outgoing'
    return None


def _preferred_busbar_segment_tokens(label: str | None) -> set[str]:
    compact = _compact_text(label).upper()
    if not compact:
        return set()
    out: set[str] = set()
    digit_map = {'1': 'I', '2': 'II', '3': 'III'}
    for token in _numeric_tag_tokens(label):
        digits = re.findall(r'\d+', token)
        if not digits:
            continue
        out.add(digits[0])
        roman = digit_map.get(digits[0])
        if roman:
            out.add(roman)
    if 'I段' in compact:
        out.update({'I', '1'})
    if 'II段' in compact:
        out.update({'II', '2'})
    if 'III段' in compact:
        out.update({'III', '3'})
    return out


def _busbar_segment_token(label: str | None) -> str | None:
    compact = _compact_text(label).upper()
    if not compact:
        return None
    for pattern in (r'([IVX]+)段', r'([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)段', r'(\d+)段'):
        match = re.search(pattern, compact)
        if match is not None:
            return match.group(1)
    return None


def _numeric_tag_tokens(label: str | None) -> set[str]:
    if not label:
        return set()
    compact = _compact_text(label)
    return {match.group(1) for match in re.finditer(r'(\d+#)', compact)}


def _is_current_rating_label(label: str | None) -> bool:
    return bool(re.fullmatch(r'\d{2,4}A', _compact_text(label).upper()))


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

    if template is not None and label:
        label = _normalize_device_label(label, template.device_type)

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

    if (
        template.device_type == 'switchgear_unit'
        and not label
        and len(terminals) <= 2
        and _is_auxiliary_drawing_context(point, texts)
    ):
        return None, [
            UnresolvedItem(
                kind='unclassified_symbol',
                source_entity_ids=(entity.entity_id,),
                reason='块参照位于布置/安装视图上下文且缺少可靠设备标注，已忽略。',
                extra={'block_name': normalized_block, 'device_type': template.device_type},
            )
        ]

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
    a = _compact_text(left).lower()
    b = _compact_text(right).lower()
    return a == b or a in b or b in a


def _build_text_groups(
    texts: list[tuple[str, Point2D, str]],
    *,
    wires: list[WireSegment],
    device_templates: tuple[DeviceTemplate, ...],
) -> list[_TextGroup]:
    candidates: list[_TextCandidate] = []
    for text_id, point, text in texts:
        normalized = _normalize_text(text)
        if not normalized or _should_ignore_text(normalized):
            continue
        if _looks_like_descriptive_device_text(normalized):
            continue
        template, keyword = _match_text_template_with_keyword(normalized, device_templates)
        if template is None:
            template, keyword = _match_special_text_template(normalized, point=point, texts=texts, wires=wires)
        if template is None or not keyword:
            continue
        if template.device_type == 'feeder' and not _has_wire_near_point(
            point,
            wires,
            radius=max(18.0, template.footprint_radius * 1.2),
        ):
            continue
        table_context = _is_table_context(point, texts)
        if table_context and not _allow_table_context_candidate(normalized, point=point, template=template, wires=wires):
            continue
        candidates.append(
            _TextCandidate(
                text_id=text_id,
                point=point,
                text=normalized,
                template=template,
                keyword=keyword,
                table_override=table_context,
            )
        )

    groups: list[list[_TextCandidate]] = []
    for candidate in candidates:
        placed = False
        for group in groups:
            head = group[0]
            radius = max(head.template.text_group_radius, candidate.template.text_group_radius)
            if (
                head.template.device_type == candidate.template.device_type
                and dist(head.point, candidate.point) <= radius
                and all(_text_candidates_can_group(existing, candidate) for existing in group)
            ):
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
        table_override = any(item.table_override for item in group)
        if _is_table_context(center, texts) and not table_override:
            continue
        ordered = sorted(group, key=lambda item: (-item.point.y, item.point.x, item.text_id))
        label = _normalize_device_label('/'.join(dict.fromkeys(item.text for item in ordered)), group[0].template.device_type)
        out.append(
            _TextGroup(
                template=group[0].template,
                items=tuple(ordered),
                center=center,
                label=label,
                table_override=table_override,
            )
        )
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
    compact_lowered = _compact_text(normalized).lower()
    best: tuple[int, int, DeviceTemplate, str] | None = None
    for idx, template in enumerate(device_templates):
        for keyword in template.text_keywords:
            normalized_keyword = _normalize_text(keyword)
            compact_keyword = _compact_text(normalized_keyword).lower()
            if normalized_keyword and (
                normalized_keyword.lower() in lowered or (compact_keyword and compact_keyword in compact_lowered)
            ):
                score = len(keyword)
                if best is None or score > best[0] or (score == best[0] and idx < best[1]):
                    best = (score, idx, template, keyword)
        for pattern in template.label_globs:
            normalized_pattern = _normalize_text(pattern)
            compact_pattern = _compact_text(normalized_pattern).lower()
            if pattern and (
                fnmatch.fnmatch(lowered, normalized_pattern.lower())
                or (compact_pattern and fnmatch.fnmatch(compact_lowered, compact_pattern))
            ):
                score = len(pattern.replace('*', '').replace('?', '')) + 1
                if best is None or score > best[0] or (score == best[0] and idx < best[1]):
                    best = (score, idx, template, pattern)
    if best is None:
        return None, None
    return best[2], best[3]


def _match_special_text_template(
    text: str,
    *,
    point: Point2D,
    texts: list[tuple[str, Point2D, str]],
    wires: list[WireSegment],
) -> tuple[DeviceTemplate | None, str | None]:
    compact = _compact_text(text).upper()
    current_match = re.fullmatch(r'(\d{2,3})A', compact)
    if current_match is None:
        return None, None
    current = int(current_match.group(1))
    if current < 63 or current > 1000:
        return None, None
    if not _looks_like_current_rating_breaker(point, wires=wires, texts=texts):
        return None, None
    return (
        DeviceTemplate(
            device_type='breaker',
            text_keywords=(text,),
            terminals=(
                TerminalDef(name='line_in', x=0.0, y=-10.0),
                TerminalDef(name='line_out', x=0.0, y=10.0),
            ),
            footprint_radius=18.0,
            min_terminals=2,
            max_terminals=2,
            text_group_radius=6.0,
            terminal_layout='vertical',
        ),
        text,
    )


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


def _infer_branch_box_terminals_from_global_wires(
    *,
    device_id: str,
    wires: list[WireSegment],
    template: DeviceTemplate,
    source_entity_ids: tuple[str, ...],
) -> tuple[Terminal, ...]:
    if len(wires) < 3 or len(wires) > 24:
        return ()
    horizontal = [wire for wire in wires if abs(wire.a.y - wire.b.y) <= max(1.5, segment_length(wire.a, wire.b) * 0.08)]
    vertical = [wire for wire in wires if abs(wire.a.x - wire.b.x) <= max(1.5, segment_length(wire.a, wire.b) * 0.08)]
    dominant = horizontal if len(horizontal) >= len(vertical) else vertical
    if len(dominant) < 3:
        return ()

    starts = [wire.a if _point_axis(wire.a, horizontal=len(horizontal) >= len(vertical)) <= _point_axis(wire.b, horizontal=len(horizontal) >= len(vertical)) else wire.b for wire in dominant]
    ends = [wire.b if _point_axis(wire.a, horizontal=len(horizontal) >= len(vertical)) <= _point_axis(wire.b, horizontal=len(horizontal) >= len(vertical)) else wire.a for wire in dominant]
    start_points = _cluster_points(starts, tol=3.0)
    end_points = _cluster_points(ends, tol=3.0)
    if len(start_points) < 1 or len(end_points) < 2:
        return ()

    lateral_axis = (lambda point: point.y) if len(horizontal) >= len(vertical) else (lambda point: point.x)
    feed = min(start_points, key=lambda point: abs(lateral_axis(point) - _median([lateral_axis(item) for item in start_points])))
    branches = _select_spread_points(end_points, count=min(3, max(2, template.max_terminals or 4) - 1), axis=lateral_axis)
    points = [feed]
    for point in branches:
        if point != feed and point not in points:
            points.append(point)
    if len(points) < 3:
        return ()
    names = _terminal_names(template, len(points))
    out: list[Terminal] = []
    for idx, point in enumerate(points, start=1):
        out.append(
            Terminal(
                id=f'{device_id}:t{idx}',
                position=point,
                name=names[idx - 1],
                source_entity_ids=source_entity_ids,
                confidence=0.55,
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


def _point_axis(point: Point2D, *, horizontal: bool) -> float:
    return point.x if horizontal else point.y


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _select_spread_points(points: list[Point2D], *, count: int, axis) -> list[Point2D]:
    ordered = sorted(dict.fromkeys(points), key=axis)
    if count <= 0 or not ordered:
        return []
    if len(ordered) <= count:
        return ordered
    if count == 1:
        return [ordered[len(ordered) // 2]]
    out: list[Point2D] = []
    last_idx = len(ordered) - 1
    for idx in range(count):
        target = round(idx * last_idx / max(1, count - 1))
        candidate = ordered[target]
        if candidate not in out:
            out.append(candidate)
    for point in ordered:
        if len(out) >= count:
            break
        if point not in out:
            out.append(point)
    return out


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
        centroid = Point2D(sx / len(cluster), sy / len(cluster))
        representative = min(cluster, key=lambda point: dist2(point, centroid))
        out.append(representative)
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
        if (
            not normalized
            or _should_ignore_text(normalized)
            or _looks_like_descriptive_device_text(normalized)
            or _is_marker_text(normalized)
        ):
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


def _compact_text(text: str) -> str:
    return ''.join(str(text or '').split())


def _normalize_device_label(label: str | None, device_type: str | None) -> str | None:
    if label is None:
        return None
    normalized = _normalize_text(label).translate(_DEVICE_LABEL_TRANSLATION)
    compact = _compact_text(normalized)
    if not compact:
        return None
    return compact


def _merge_text_group_into_existing_device(
    *,
    group: _TextGroup,
    terminals: tuple[Terminal, ...],
    devices: list[Device],
) -> bool:
    best_idx: int | None = None
    best_score: float | None = None
    merged_sources = tuple(item.text_id for item in group.items)
    for idx, device in enumerate(devices):
        if device.device_type != group.template.device_type:
            continue
        if device.label and group.label and not _labels_equivalent(device.label, group.label):
            continue
        radius = max(
            36.0,
            group.template.footprint_radius * 4.0,
            (device.footprint_radius or 0.0) * 4.0,
            group.template.text_group_radius * 4.0,
        )
        current_distance = dist(device.position, group.center)
        if current_distance > radius:
            continue
        score = current_distance
        if device.block_name is not None:
            score -= 8.0
        if not device.label:
            score -= 12.0
        if best_score is None or score < best_score:
            best_idx = idx
            best_score = score
    if best_idx is None:
        return False

    existing = devices[best_idx]
    combined_sources = tuple(dict.fromkeys(existing.source_entity_ids + merged_sources))
    merged_label = existing.label or group.label
    merged_terminals = existing.terminals
    if len(terminals) > len(merged_terminals):
        merged_terminals = terminals
    devices[best_idx] = Device(
        id=existing.id,
        position=existing.position,
        label=merged_label,
        device_type=existing.device_type,
        terminals=merged_terminals,
        block_name=existing.block_name,
        source_entity_ids=combined_sources,
        footprint_radius=existing.footprint_radius,
    )
    return True


def _looks_like_descriptive_device_text(text: str) -> bool:
    compact = _compact_text(text)
    if not compact:
        return True
    if compact.startswith('图') and ('：' in compact or ':' in compact):
        return True
    if compact.startswith('图') and any(token in compact for token in _AUXILIARY_DRAWING_TOKENS):
        return True
    if re.match(r'^\d+[.、].{6,}', compact):
        return True
    descriptive_tokens = (
        *_AUXILIARY_DRAWING_TOKENS,
        '示意图',
        '本图',
        '连接',
        '横担',
        '安装横担',
        '接地',
        '引上线',
        '调整',
        '配置',
        '接地系统',
        '接地连接',
        '采用',
        '方案图',
        '外壳',
        '加工图',
    )
    if any(token in compact for token in descriptive_tokens):
        return True
    if len(compact) >= 24 and any(mark in compact for mark in ('：', ':', '；', ';', '。')):
        return True
    return False


def _text_candidates_can_group(left: _TextCandidate, right: _TextCandidate) -> bool:
    if left.template.device_type != right.template.device_type:
        return False
    left_code_like = _looks_like_device_code_text(left.text, left.template.device_type)
    right_code_like = _looks_like_device_code_text(right.text, right.template.device_type)
    if left_code_like and right_code_like:
        return _labels_equivalent(left.text, right.text)
    return True


def _looks_like_device_code_text(text: str, device_type: str) -> bool:
    compact = _compact_text(text).upper()
    if not compact:
        return False
    if device_type == 'breaker':
        return 'QF' in compact or 'QS' in compact or 'QK' in compact
    if device_type == 'switchgear_unit':
        return re.search(r'(DK|DP)[-#]?\d+', compact) is not None
    if device_type == 'cable_branch_box':
        return re.search(r'DF[-#]?\d+', compact) is not None
    if device_type == 'transformer':
        return bool(re.search(r'(TA|TM)[-#]?\d+', compact)) or '主变' in compact
    return False


def _looks_like_current_rating_breaker(
    point: Point2D,
    *,
    wires: list[WireSegment],
    texts: list[tuple[str, Point2D, str]],
    radius: float = 28.0,
) -> bool:
    vertical_like = 0
    nearby_wires = 0
    for wire in wires:
        if distance_point_to_segment(point, wire.a, wire.b) > radius and min(dist(point, wire.a), dist(point, wire.b)) > radius:
            continue
        nearby_wires += 1
        dx = abs(wire.a.x - wire.b.x)
        dy = abs(wire.a.y - wire.b.y)
        if dy >= max(8.0, dx * 2.0):
            vertical_like += 1
    if nearby_wires < 4 or vertical_like < 3:
        return False
    for _, text_point, text in texts:
        if dist(point, text_point) > radius:
            continue
        compact = _compact_text(text)
        if any(token in compact for token in ('断路器', '隔离开关', '负荷开关', '熔断器', 'QF', 'QS', '进线', '出线')):
            return False
    return True


def _is_auxiliary_drawing_context(center: Point2D, texts: list[tuple[str, Point2D, str]], radius: float = 80.0) -> bool:
    radius2 = radius * radius
    descriptive_count = 0
    marker_count = 0
    neutral_count = 0
    for _, point, text in texts:
        normalized = _normalize_text(text)
        if not normalized or dist2(center, point) > radius2:
            continue
        compact = _compact_text(normalized)
        if _looks_like_descriptive_device_text(normalized):
            descriptive_count += 1
            continue
        if _is_marker_text(compact):
            marker_count += 1
            continue
        neutral_count += 1
    return descriptive_count >= 1 and (marker_count >= 2 or neutral_count <= 1)


def _is_marker_text(text: str) -> bool:
    compact = _compact_text(text)
    if not compact or len(compact) > 2:
        return False
    return compact.isascii() and compact.isalnum()


def _allow_table_context_candidate(
    text: str,
    *,
    point: Point2D,
    template: DeviceTemplate,
    wires: list[WireSegment],
) -> bool:
    compact = _compact_text(text).lower()
    radius = max(24.0, template.footprint_radius * 1.6)
    if template.device_type in {'switchgear_unit', 'breaker', 'transformer', 'busbar', 'feeder', 'load'}:
        return _has_wire_near_point(point, wires, radius=radius)
    if template.device_type == 'cable_branch_box':
        if _matches_equipment_code(compact, prefix='df'):
            return True
        return _has_wire_near_point(point, wires, radius=max(28.0, radius))
    return False


def _can_materialize_text_device_without_terminals(group: _TextGroup) -> bool:
    compact = _compact_text(group.label).lower()
    if group.template.device_type == 'switchgear_unit':
        return _matches_equipment_code(compact, prefix='dk') or _matches_equipment_code(compact, prefix='dp') or any(
            token in compact for token in ('开关柜', '配电箱', '联络柜', '进线总柜', '出线柜')
        )
    if group.template.device_type == 'cable_branch_box':
        return _matches_equipment_code(compact, prefix='df') or '分支箱' in compact
    return False


def _matches_equipment_code(text: str, *, prefix: str) -> bool:
    return re.search(rf'{re.escape(prefix.lower())}[-#]?\d+', text.lower()) is not None


def _has_wire_near_point(point: Point2D, wires: list[WireSegment], *, radius: float) -> bool:
    radius2 = radius * radius
    for wire in wires:
        if dist2(point, wire.a) <= radius2 or dist2(point, wire.b) <= radius2:
            return True
        if distance_point_to_segment(point, wire.a, wire.b) <= radius:
            return True
    return False


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
