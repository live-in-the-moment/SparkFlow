from __future__ import annotations

import re

from ..contracts import Issue, ObjectRef, Severity
from ..model.types import ElectricalGraph, ElectricalTerminal, SystemModel
from .types import RuleResult


class ElectricalComponentMissingTerminalsRule:
    rule_id = 'electrical.component_missing_terminals'

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        issues: list[Issue] = []
        for component in electrical.components:
            if component.terminal_ids:
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message='组件缺少端子，无法建立可靠电气关系。',
                    refs=(
                        ObjectRef(
                            kind='component',
                            id=component.id,
                            source_entity_ids=component.source_entity_ids,
                            extra={'component_type': component.type},
                        ),
                    ),
                )
            )
        return RuleResult(issues=tuple(issues))


class ElectricalComponentUnconnectedRule:
    rule_id = 'electrical.component_unconnected'

    def __init__(self, *, severity: str = 'error') -> None:
        self._severity = Severity(severity)

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        issues: list[Issue] = []
        for component in electrical.components:
            if not component.terminal_ids:
                continue
            nets = {
                net.id
                for net in electrical.nets
                if any(terminal_id in net.terminal_ids for terminal_id in component.terminal_ids)
            }
            if nets:
                continue
            refs = []
            for terminal_id in component.terminal_ids[:6]:
                terminal = terminal_by_id.get(terminal_id)
                if terminal is None:
                    continue
                refs.append(
                    ObjectRef(
                        kind='terminal',
                        id=terminal.id,
                        source_entity_ids=component.source_entity_ids,
                        extra={'component_id': component.id, 'x': terminal.x, 'y': terminal.y},
                    )
                )
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=self._severity,
                    message='组件未落到任何电气网络。',
                    refs=tuple(refs),
                )
            )
        return RuleResult(issues=tuple(issues))


class ElectricalSwitchSameNetRule:
    rule_id = 'electrical.switch_same_net'

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        terminal_to_net = _terminal_to_net(electrical)
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        issues: list[Issue] = []
        for component in electrical.components:
            if component.type != 'breaker':
                continue
            if len(component.terminal_ids) < 2:
                continue
            nets: list[str | None] = [terminal_to_net.get(terminal_id) for terminal_id in component.terminal_ids]
            seen: set[str] = set()
            for net_id in nets:
                if net_id is None:
                    continue
                if net_id in seen:
                    issues.append(
                        Issue(
                            rule_id=self.rule_id,
                            severity=Severity.ERROR,
                            message='开关组件多个端子落在同一电气网络，可能短接或端子识别异常。',
                            refs=tuple(_component_refs(component.id, component.terminal_ids, component.source_entity_ids, terminal_by_id)),
                        )
                    )
                    break
                seen.add(net_id)
        return RuleResult(issues=tuple(issues))


class ElectricalTransformerSameNetRule:
    rule_id = 'electrical.transformer_same_net'

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        terminal_to_net = _terminal_to_net(electrical)
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        issues: list[Issue] = []
        for component in electrical.components:
            if component.type != 'transformer':
                continue
            if _component_has_duplicate_net(component.terminal_ids, terminal_to_net):
                issues.append(
                    Issue(
                        rule_id=self.rule_id,
                        severity=Severity.ERROR,
                        message='变压器多个端子落在同一电气网络，可能存在短接或端子识别异常。',
                        refs=tuple(
                            _component_refs(component.id, component.terminal_ids, component.source_entity_ids, terminal_by_id)
                        ),
                    )
                )
        return RuleResult(issues=tuple(issues))


class ElectricalBusbarUnderconnectedRule:
    rule_id = 'electrical.busbar_underconnected'

    def __init__(self, *, min_connected_terminals: int = 2, severity: str = 'warning') -> None:
        self._min_connected_terminals = max(2, int(min_connected_terminals))
        self._severity = Severity(severity)

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        terminal_to_net = _terminal_to_net(electrical)
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        issues: list[Issue] = []
        for component in electrical.components:
            if component.type != 'busbar':
                continue
            connected = tuple(tid for tid in component.terminal_ids if terminal_to_net.get(tid) is not None)
            if len(connected) >= self._min_connected_terminals:
                continue
            refs = _component_refs(component.id, component.terminal_ids, component.source_entity_ids, terminal_by_id)
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=self._severity,
                    message=f'母线连接端子数量不足（{len(connected)}/{self._min_connected_terminals}），可能存在漏接或识别不全。',
                    refs=tuple(refs),
                )
            )
        return RuleResult(issues=tuple(issues))


class ElectricalBranchBoxInsufficientBranchesRule:
    rule_id = 'electrical.branch_box_insufficient_branches'

    def __init__(self, *, min_branch_terminals: int = 2, severity: str = 'error') -> None:
        self._min_branch_terminals = max(1, int(min_branch_terminals))
        self._severity = Severity(severity)

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        terminal_to_net = _terminal_to_net(electrical)
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        issues: list[Issue] = []
        for component in electrical.components:
            if component.type != 'cable_branch_box':
                continue
            connected_ids = tuple(tid for tid in component.terminal_ids if terminal_to_net.get(tid) is not None)
            branch_ids = tuple(
                tid
                for tid in connected_ids
                if (terminal_by_id.get(tid) and (terminal_by_id[tid].role or '').lower().startswith('branch'))
            )
            enough = len(branch_ids) >= self._min_branch_terminals
            if not branch_ids:
                enough = len(connected_ids) >= self._min_branch_terminals + 1
            if enough:
                continue
            refs = _component_refs(component.id, component.terminal_ids, component.source_entity_ids, terminal_by_id)
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=self._severity,
                    message=f'电缆分支箱有效分支数量不足，至少需要 {self._min_branch_terminals} 个分支端。',
                    refs=tuple(refs),
                )
            )
        return RuleResult(issues=tuple(issues))


class ElectricalSwitchgearRoleConnectionRule:
    rule_id = 'electrical.switchgear_role_connection'

    def __init__(self, *, severity: str = 'warning') -> None:
        self._severity = Severity(severity)

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        component_by_id = {component.id: component for component in electrical.components}
        terminal_to_net = _terminal_to_net(electrical)
        net_to_component_ids = _net_to_component_ids(electrical)
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        issues: list[Issue] = []

        for component in electrical.components:
            if component.type != 'switchgear_unit' or _is_inferred_proxy_component(component):
                continue
            role = _switchgear_role(component.label)
            if role is None:
                continue
            component_nets = {terminal_to_net.get(terminal_id) for terminal_id in component.terminal_ids if terminal_to_net.get(terminal_id)}
            neighbor_ids = set()
            for net_id in component_nets:
                neighbor_ids.update(net_to_component_ids.get(net_id, set()))
            neighbor_ids.discard(component.id)
            neighbor_types = {component_by_id[nid].type for nid in neighbor_ids if nid in component_by_id}

            if _switchgear_role_expectation_met(role, component_nets, neighbor_types):
                continue

            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=self._severity,
                    message=_switchgear_role_failure_message(role, component.label or component.id),
                    refs=tuple(_component_refs(component.id, component.terminal_ids, component.source_entity_ids, terminal_by_id)),
                )
            )

        return RuleResult(issues=tuple(issues))


class ElectricalSwitchgearFeedChainRule:
    rule_id = 'electrical.switchgear_feed_chain'

    def __init__(self, *, severity: str = 'warning') -> None:
        self._severity = Severity(severity)

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        component_by_id = {component.id: component for component in electrical.components}
        terminal_to_net = _terminal_to_net(electrical)
        net_to_component_ids = _net_to_component_ids(electrical)
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        issues: list[Issue] = []

        for component in electrical.components:
            if component.type != 'switchgear_unit' or _is_inferred_proxy_component(component):
                continue
            role = _switchgear_role(component.label)
            if role not in {'incoming', 'outgoing'}:
                continue
            component_nets = _component_nets(component, terminal_to_net)
            busbar_ids = {
                neighbor_id
                for neighbor_id in _component_neighbor_ids(component.id, component_nets, net_to_component_ids)
                if component_by_id.get(neighbor_id) is not None and component_by_id[neighbor_id].type == 'busbar'
            }
            linked_roles = _busbar_linked_switchgear_roles(
                busbar_ids,
                component_by_id=component_by_id,
                terminal_to_net=terminal_to_net,
                net_to_component_ids=net_to_component_ids,
                exclude_component_id=component.id,
            )
            if role == 'incoming' and ({'outgoing', 'tie'} & linked_roles):
                continue
            if role == 'outgoing' and ({'incoming', 'tie'} & linked_roles):
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=self._severity,
                    message=_switchgear_feed_chain_failure_message(role, component.label or component.id),
                    refs=tuple(_component_refs(component.id, component.terminal_ids, component.source_entity_ids, terminal_by_id)),
                )
            )
        return RuleResult(issues=tuple(issues))


class ElectricalTieSwitchgearDualSideRule:
    rule_id = 'electrical.tie_switchgear_dual_side'

    def __init__(self, *, severity: str = 'warning') -> None:
        self._severity = Severity(severity)

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        component_by_id = {component.id: component for component in electrical.components}
        terminal_to_net = _terminal_to_net(electrical)
        net_to_component_ids = _net_to_component_ids(electrical)
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        issues: list[Issue] = []

        for component in electrical.components:
            if component.type != 'switchgear_unit' or _is_inferred_proxy_component(component) or _switchgear_role(component.label) != 'tie':
                continue
            component_nets = _component_nets(component, terminal_to_net)
            supported_nets = 0
            neighbor_ids: set[str] = set()
            for net_id in component_nets:
                ids = _component_neighbor_ids(component.id, {net_id}, net_to_component_ids)
                supporting = {
                    neighbor_id
                    for neighbor_id in ids
                    if component_by_id.get(neighbor_id) is not None
                    and component_by_id[neighbor_id].type in {'switchgear_unit', 'busbar', 'breaker'}
                }
                if supporting:
                    supported_nets += 1
                    neighbor_ids.update(supporting)
            if supported_nets >= 2 and len(neighbor_ids) >= 2:
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=self._severity,
                    message=f'联络柜双侧网络不完整：{component.label or component.id} 未同时接入两侧独立联络对象。',
                    refs=tuple(_component_refs(component.id, component.terminal_ids, component.source_entity_ids, terminal_by_id)),
                )
            )
        return RuleResult(issues=tuple(issues))


class ElectricalIncomingTransformerBusbarDirectionRule:
    rule_id = 'electrical.incoming_transformer_busbar_direction'

    def __init__(self, *, severity: str = 'warning', min_axis_separation: float = 2.0) -> None:
        self._severity = Severity(severity)
        self._min_axis_separation = max(0.5, float(min_axis_separation))

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        component_by_id = {component.id: component for component in electrical.components}
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        terminal_to_net = _terminal_to_net(electrical)
        net_to_component_ids = _net_to_component_ids(electrical)
        issues: list[Issue] = []

        for component in electrical.components:
            if component.type != 'switchgear_unit' or _switchgear_role(component.label) != 'incoming':
                continue
            neighbor_types = _component_terminal_neighbor_types(
                component,
                terminal_to_net=terminal_to_net,
                net_to_component_ids=net_to_component_ids,
                component_by_id=component_by_id,
            )
            transformer_terminals = [
                terminal_by_id[terminal_id]
                for terminal_id, types in neighbor_types.items()
                if 'transformer' in types and terminal_id in terminal_by_id
            ]
            busbar_terminals = [
                terminal_by_id[terminal_id]
                for terminal_id, types in neighbor_types.items()
                if 'busbar' in types and terminal_id in terminal_by_id
            ]
            if not transformer_terminals or not busbar_terminals:
                continue
            if _terminal_groups_are_opposite(
                transformer_terminals,
                busbar_terminals,
                min_axis_separation=self._min_axis_separation,
            ):
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=self._severity,
                    message=f'进线柜方向关系异常：{component.label or component.id} 的变压器侧与母线侧未分置在相对两侧。',
                    refs=tuple(_component_refs(component.id, component.terminal_ids, component.source_entity_ids, terminal_by_id)),
                )
            )
        return RuleResult(issues=tuple(issues))


class ElectricalTieBusbarSegmentConsistencyRule:
    rule_id = 'electrical.tie_busbar_segment_consistency'

    def __init__(self, *, severity: str = 'warning') -> None:
        self._severity = Severity(severity)

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        component_by_id = {component.id: component for component in electrical.components}
        terminal_to_net = _terminal_to_net(electrical)
        net_to_component_ids = _net_to_component_ids(electrical)
        terminal_by_id = {terminal.id: terminal for terminal in electrical.terminals}
        issues: list[Issue] = []

        for component in electrical.components:
            if component.type != 'switchgear_unit' or _switchgear_role(component.label) != 'tie':
                continue
            component_nets = _component_nets(component, terminal_to_net)
            busbars = [
                component_by_id[neighbor_id]
                for neighbor_id in _component_neighbor_ids(component.id, component_nets, net_to_component_ids)
                if component_by_id.get(neighbor_id) is not None and component_by_id[neighbor_id].type == 'busbar'
            ]
            if len(busbars) < 2:
                continue
            known_tokens = [token for token in (_extract_busbar_segment_token(busbar.label) for busbar in busbars) if token]
            if len(known_tokens) >= 2 and len(set(known_tokens)) >= 2:
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=self._severity,
                    message=f'联络柜母线分段异常：{component.label or component.id} 两侧母线未体现清晰且相互独立的分段标识。',
                    refs=tuple(_component_refs(component.id, component.terminal_ids, component.source_entity_ids, terminal_by_id)),
                )
            )
        return RuleResult(issues=tuple(issues))


class ElectricalRelationUnresolvedRule:
    rule_id = 'electrical.relation_unresolved'

    def run(self, model: SystemModel) -> RuleResult:
        electrical = model.electrical
        if electrical is None:
            return RuleResult(issues=())
        issues: list[Issue] = []
        for item in electrical.unresolved:
            if item.kind not in {'component_relation', 'terminal', 'terminal_anchor'}:
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=item.reason or '存在未闭合的电气关系。',
                    refs=(
                        ObjectRef(
                            kind=item.kind,
                            id=str(item.extra.get('component_id', item.kind)) if isinstance(item.extra, dict) else item.kind,
                            source_entity_ids=item.source_entity_ids,
                            extra=item.extra,
                        ),
                    ),
                )
            )
        return RuleResult(issues=tuple(issues))


class TopologyTerminalUnconnectedRule(ElectricalComponentUnconnectedRule):
    rule_id = 'topo.terminal_unconnected'


class TopologyBreakerSameNetRule(ElectricalSwitchSameNetRule):
    rule_id = 'topo.breaker_same_net'


def _component_has_duplicate_net(terminal_ids: tuple[str, ...], terminal_to_net: dict[str, str]) -> bool:
    seen: set[str] = set()
    for terminal_id in terminal_ids:
        net_id = terminal_to_net.get(terminal_id)
        if net_id is None:
            continue
        if net_id in seen:
            return True
        seen.add(net_id)
    return False


def _net_to_component_ids(electrical: ElectricalGraph) -> dict[str, set[str]]:
    terminal_to_component = {terminal.id: terminal.component_id for terminal in electrical.terminals}
    mapping: dict[str, set[str]] = {}
    for net in electrical.nets:
        ids = {terminal_to_component[tid] for tid in net.terminal_ids if tid in terminal_to_component}
        mapping[net.id] = ids
    return mapping


def _component_terminal_neighbor_types(
    component,
    *,
    terminal_to_net: dict[str, str],
    net_to_component_ids: dict[str, set[str]],
    component_by_id,
) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for terminal_id in component.terminal_ids:
        net_id = terminal_to_net.get(terminal_id)
        if net_id is None:
            continue
        neighbor_types = {
            component_by_id[neighbor_id].type
            for neighbor_id in net_to_component_ids.get(net_id, set())
            if neighbor_id != component.id and component_by_id.get(neighbor_id) is not None
        }
        if neighbor_types:
            mapping[terminal_id] = neighbor_types
    return mapping


def _component_nets(component, terminal_to_net: dict[str, str]) -> set[str]:
    return {terminal_to_net[terminal_id] for terminal_id in component.terminal_ids if terminal_id in terminal_to_net}


def _component_neighbor_ids(
    component_id: str,
    component_nets: set[str],
    net_to_component_ids: dict[str, set[str]],
) -> set[str]:
    neighbor_ids: set[str] = set()
    for net_id in component_nets:
        neighbor_ids.update(net_to_component_ids.get(net_id, set()))
    neighbor_ids.discard(component_id)
    return neighbor_ids


def _busbar_linked_switchgear_roles(
    busbar_ids: set[str],
    *,
    component_by_id,
    terminal_to_net: dict[str, str],
    net_to_component_ids: dict[str, set[str]],
    exclude_component_id: str,
) -> set[str]:
    linked_roles: set[str] = set()
    for busbar_id in busbar_ids:
        busbar = component_by_id.get(busbar_id)
        if busbar is None:
            continue
        busbar_nets = _component_nets(busbar, terminal_to_net)
        for neighbor_id in _component_neighbor_ids(busbar_id, busbar_nets, net_to_component_ids):
            if neighbor_id == exclude_component_id:
                continue
            neighbor = component_by_id.get(neighbor_id)
            if neighbor is None or neighbor.type != 'switchgear_unit':
                continue
            role = _switchgear_role(neighbor.label)
            if role is not None:
                linked_roles.add(role)
    return linked_roles


def _switchgear_role(label: str | None) -> str | None:
    compact = _compact_label(label)
    if not compact:
        return None
    if '联络柜' in compact:
        return 'tie'
    if '进线' in compact and '柜' in compact:
        return 'incoming'
    if '出线' in compact and '柜' in compact:
        return 'outgoing'
    return None


def _switchgear_role_expectation_met(role: str, component_nets: set[str], neighbor_types: set[str]) -> bool:
    if len(component_nets) < 2:
        return False
    if role == 'tie':
        return bool({'switchgear_unit', 'busbar', 'breaker'} & neighbor_types)
    if role == 'incoming':
        return bool({'transformer', 'busbar', 'feeder', 'switchgear_unit'} & neighbor_types)
    if role == 'outgoing':
        return bool({'load', 'feeder', 'cable_branch_box', 'breaker'} & neighbor_types) and bool(
            {'busbar', 'switchgear_unit', 'transformer'} & neighbor_types
        )
    return True


def _switchgear_role_failure_message(role: str, label: str) -> str:
    if role == 'tie':
        return f'联络柜连接关系不足：{label} 未形成有效的双侧联络网络。'
    if role == 'incoming':
        return f'进线柜连接关系不足：{label} 未同时体现来源侧与柜内母线/联络侧连接。'
    if role == 'outgoing':
        return f'出线柜连接关系不足：{label} 未同时体现上游柜内侧与下游出线侧连接。'
    return f'开关柜连接关系不足：{label}'


def _switchgear_feed_chain_failure_message(role: str, label: str) -> str:
    if role == 'incoming':
        return f'进线柜母线链路不足：{label} 未通过母线连接到出线柜或联络柜。'
    if role == 'outgoing':
        return f'出线柜母线链路不足：{label} 未通过母线连接到进线柜或联络柜。'
    return f'开关柜母线链路不足：{label}'


def _terminal_groups_are_opposite(
    first: list[ElectricalTerminal],
    second: list[ElectricalTerminal],
    *,
    min_axis_separation: float,
) -> bool:
    terminals = first + second
    if len(terminals) < 2:
        return False
    center_x = sum(terminal.x for terminal in terminals) / len(terminals)
    center_y = sum(terminal.y for terminal in terminals) / len(terminals)
    x_span = max(terminal.x for terminal in terminals) - min(terminal.x for terminal in terminals)
    y_span = max(terminal.y for terminal in terminals) - min(terminal.y for terminal in terminals)
    axis = 'x' if x_span >= y_span else 'y'

    def _projection(terminal: ElectricalTerminal) -> float:
        return terminal.x - center_x if axis == 'x' else terminal.y - center_y

    first_mid = _median_value([_projection(terminal) for terminal in first])
    second_mid = _median_value([_projection(terminal) for terminal in second])
    return first_mid * second_mid < 0 and abs(first_mid - second_mid) >= min_axis_separation


def _median_value(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _extract_busbar_segment_token(label: str | None) -> str | None:
    compact = _compact_label(label)
    if not compact:
        return None
    patterns = (
        r'([IVX]+)段',
        r'([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)段',
        r'([A-Z])段',
        r'(\d+)段',
    )
    for pattern in patterns:
        match = re.search(pattern, compact, re.IGNORECASE)
        if match is not None:
            return match.group(1).upper()
    return None


def _compact_label(label: str | None) -> str:
    return ''.join((label or '').split())


def _is_inferred_proxy_component(component) -> bool:
    return str(getattr(component, 'id', '')).startswith('proxy:')


def _component_refs(
    component_id: str,
    terminal_ids: tuple[str, ...],
    source_entity_ids: tuple[str, ...],
    terminal_by_id: dict[str, ElectricalTerminal],
) -> list[ObjectRef]:
    refs: list[ObjectRef] = []
    for terminal_id in terminal_ids[:6]:
        terminal = terminal_by_id.get(terminal_id)
        if terminal is None:
            continue
        refs.append(
            ObjectRef(
                kind='terminal',
                id=terminal.id,
                source_entity_ids=source_entity_ids,
                extra={
                    'component_id': component_id,
                    'node': terminal.node_id,
                    'x': terminal.x,
                    'y': terminal.y,
                },
            )
        )
    return refs


def _terminal_to_net(electrical: ElectricalGraph) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for net in electrical.nets:
        for terminal_id in net.terminal_ids:
            mapping[terminal_id] = net.id
    return mapping
