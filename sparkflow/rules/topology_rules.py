from __future__ import annotations

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
