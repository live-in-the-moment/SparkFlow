from __future__ import annotations

from .connectivity import connected_components
from .types import (
    ElectricalComponent,
    ElectricalGraph,
    ElectricalNet,
    ElectricalRelation,
    ElectricalTerminal,
    SystemModel,
    UnresolvedItem,
)


def build_electrical_graph(model: SystemModel) -> SystemModel:
    connectivity = model.connectivity
    if connectivity is None:
        return model

    unresolved = list(model.unresolved)
    terminals: list[ElectricalTerminal] = []
    terminal_index: dict[str, ElectricalTerminal] = {}
    components: list[ElectricalComponent] = []

    for device in model.devices:
        component_type = device.device_type or 'unknown_component'
        terminal_ids: list[str] = []
        if not device.terminals:
            unresolved.append(
                UnresolvedItem(
                    kind='component',
                    source_entity_ids=device.source_entity_ids,
                    reason='组件未识别到端子，无法可靠建立电气关系。',
                    extra={'component_id': device.id, 'component_type': component_type},
                )
            )
        for idx, terminal in enumerate(device.terminals, start=1):
            role = terminal.name or f'p{idx}'
            node_id = connectivity.terminal_anchors.get(terminal.id)
            if node_id is None:
                unresolved.append(
                    UnresolvedItem(
                        kind='terminal',
                        source_entity_ids=terminal.source_entity_ids or device.source_entity_ids,
                        reason='端子未映射到连通节点。',
                        extra={'component_id': device.id, 'terminal_id': terminal.id},
                    )
                )
            et = ElectricalTerminal(
                id=terminal.id,
                component_id=device.id,
                role=role,
                x=terminal.position.x,
                y=terminal.position.y,
                node_id=node_id,
            )
            terminals.append(et)
            terminal_index[et.id] = et
            terminal_ids.append(et.id)
        components.append(
            ElectricalComponent(
                id=device.id,
                type=component_type,
                label=device.label,
                source_entity_ids=device.source_entity_ids,
                terminal_ids=tuple(terminal_ids),
            )
        )

    nets: list[ElectricalNet] = []
    groups = connected_components(len(connectivity.nodes), connectivity.edges)
    for idx, group in enumerate(groups, start=1):
        group_set = set(group)
        terminal_ids = tuple(sorted(t.id for t in terminals if t.node_id is not None and t.node_id in group_set))
        nets.append(ElectricalNet(id=f'net:{idx}', terminal_ids=terminal_ids, node_ids=tuple(group)))

    relations: list[ElectricalRelation] = []
    for component in components:
        comp_terms = [terminal_index[terminal_id] for terminal_id in component.terminal_ids if terminal_id in terminal_index]
        relation_type = _relation_type(component.type)
        if relation_type is None:
            continue
        if len(comp_terms) < 2:
            unresolved.append(
                UnresolvedItem(
                    kind='component_relation',
                    source_entity_ids=component.source_entity_ids,
                    reason='组件端子不足，无法建立关系。',
                    extra={'component_id': component.id, 'component_type': component.type},
                )
            )
            continue
        for rel_idx, (left, right) in enumerate(_relation_pairs(component.type, comp_terms), start=1):
            relations.append(
                ElectricalRelation(
                    id=f'{component.id}:rel{rel_idx}',
                    type=relation_type,
                    from_terminal_id=left.id,
                    to_terminal_id=right.id,
                    state=_relation_state(relation_type),
                )
            )

    electrical = ElectricalGraph(
        components=tuple(components),
        terminals=tuple(terminals),
        nets=tuple(nets),
        relations=tuple(relations),
        unresolved=tuple(unresolved),
    )
    return SystemModel(
        wires=model.wires,
        devices=model.devices,
        texts=model.texts,
        entity_index=model.entity_index,
        selection=model.selection,
        unresolved=model.unresolved,
        connectivity=connectivity,
        electrical=electrical,
    )


def _relation_type(component_type: str) -> str | None:
    if component_type == 'breaker':
        return 'switchable'
    if component_type == 'transformer':
        return 'coupled'
    if component_type in {'busbar', 'switchgear_unit', 'cable_branch_box', 'unknown_component'}:
        return 'conductive'
    return None


def _relation_state(relation_type: str) -> str:
    if relation_type == 'switchable':
        return 'unknown'
    if relation_type == 'coupled':
        return 'linked'
    return 'closed'


def _relation_pairs(component_type: str, terminals: list[ElectricalTerminal]) -> list[tuple[ElectricalTerminal, ElectricalTerminal]]:
    if component_type in {'breaker', 'transformer'}:
        return [(terminals[0], terminals[1])]
    head = terminals[0]
    return [(head, terminal) for terminal in terminals[1:]]
