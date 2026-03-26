from __future__ import annotations

from typing import Any

from .rules import (
    DeviceLabelPatternInvalidRule,
    DeviceNeedsNearbyTextRule,
    DuplicateDeviceLabelRule,
    FloatingWireEndpointsRule,
)
from .topology_rules import (
    ElectricalBranchBoxInsufficientBranchesRule,
    ElectricalBusbarUnderconnectedRule,
    ElectricalComponentMissingTerminalsRule,
    ElectricalComponentUnconnectedRule,
    ElectricalIncomingTransformerBusbarDirectionRule,
    ElectricalRelationUnresolvedRule,
    ElectricalTieBusbarSegmentConsistencyRule,
    ElectricalSwitchgearFeedChainRule,
    ElectricalSwitchgearRoleConnectionRule,
    ElectricalSwitchSameNetRule,
    ElectricalTieSwitchgearDualSideRule,
    ElectricalTransformerSameNetRule,
    TopologyBreakerSameNetRule,
    TopologyTerminalUnconnectedRule,
)
from .types import Rule


def build_rule(rule_id: str, params: dict[str, Any] | None = None) -> Rule:
    params = params or {}
    if rule_id == FloatingWireEndpointsRule.rule_id:
        tol = params.get('tol')
        return FloatingWireEndpointsRule(tol=float(tol)) if tol is not None else FloatingWireEndpointsRule()
    if rule_id == DeviceNeedsNearbyTextRule.rule_id:
        radius = params.get('radius')
        return DeviceNeedsNearbyTextRule(radius=float(radius)) if radius is not None else DeviceNeedsNearbyTextRule()
    if rule_id == DuplicateDeviceLabelRule.rule_id:
        return DuplicateDeviceLabelRule()
    if rule_id == DeviceLabelPatternInvalidRule.rule_id:
        sev = params.get('severity')
        return DeviceLabelPatternInvalidRule(severity=str(sev)) if sev is not None else DeviceLabelPatternInvalidRule()
    if rule_id == ElectricalComponentMissingTerminalsRule.rule_id:
        return ElectricalComponentMissingTerminalsRule()
    if rule_id == ElectricalComponentUnconnectedRule.rule_id:
        sev = params.get('severity')
        return ElectricalComponentUnconnectedRule(severity=str(sev)) if sev is not None else ElectricalComponentUnconnectedRule()
    if rule_id == ElectricalTransformerSameNetRule.rule_id:
        return ElectricalTransformerSameNetRule()
    if rule_id == ElectricalSwitchSameNetRule.rule_id:
        return ElectricalSwitchSameNetRule()
    if rule_id == ElectricalSwitchgearRoleConnectionRule.rule_id:
        sev = params.get('severity')
        return ElectricalSwitchgearRoleConnectionRule(severity=str(sev)) if sev is not None else ElectricalSwitchgearRoleConnectionRule()
    if rule_id == ElectricalSwitchgearFeedChainRule.rule_id:
        sev = params.get('severity')
        return ElectricalSwitchgearFeedChainRule(severity=str(sev)) if sev is not None else ElectricalSwitchgearFeedChainRule()
    if rule_id == ElectricalTieSwitchgearDualSideRule.rule_id:
        sev = params.get('severity')
        return ElectricalTieSwitchgearDualSideRule(severity=str(sev)) if sev is not None else ElectricalTieSwitchgearDualSideRule()
    if rule_id == ElectricalIncomingTransformerBusbarDirectionRule.rule_id:
        sev = params.get('severity')
        separation = params.get('min_axis_separation')
        kwargs = {}
        if sev is not None:
            kwargs['severity'] = str(sev)
        if separation is not None:
            kwargs['min_axis_separation'] = float(separation)
        return ElectricalIncomingTransformerBusbarDirectionRule(**kwargs)
    if rule_id == ElectricalTieBusbarSegmentConsistencyRule.rule_id:
        sev = params.get('severity')
        return ElectricalTieBusbarSegmentConsistencyRule(severity=str(sev)) if sev is not None else ElectricalTieBusbarSegmentConsistencyRule()
    if rule_id == ElectricalBusbarUnderconnectedRule.rule_id:
        sev = params.get('severity')
        minimum = params.get('min_connected_terminals')
        kwargs = {}
        if sev is not None:
            kwargs['severity'] = str(sev)
        if minimum is not None:
            kwargs['min_connected_terminals'] = int(minimum)
        return ElectricalBusbarUnderconnectedRule(**kwargs)
    if rule_id == ElectricalBranchBoxInsufficientBranchesRule.rule_id:
        sev = params.get('severity')
        minimum = params.get('min_branch_terminals')
        kwargs = {}
        if sev is not None:
            kwargs['severity'] = str(sev)
        if minimum is not None:
            kwargs['min_branch_terminals'] = int(minimum)
        return ElectricalBranchBoxInsufficientBranchesRule(**kwargs)
    if rule_id == ElectricalRelationUnresolvedRule.rule_id:
        return ElectricalRelationUnresolvedRule()
    if rule_id == TopologyTerminalUnconnectedRule.rule_id:
        sev = params.get('severity')
        return TopologyTerminalUnconnectedRule(severity=str(sev)) if sev is not None else TopologyTerminalUnconnectedRule()
    if rule_id == TopologyBreakerSameNetRule.rule_id:
        return TopologyBreakerSameNetRule()
    raise KeyError(rule_id)


def list_rule_ids() -> list[str]:
    return [
        FloatingWireEndpointsRule.rule_id,
        DeviceNeedsNearbyTextRule.rule_id,
        DuplicateDeviceLabelRule.rule_id,
        DeviceLabelPatternInvalidRule.rule_id,
        ElectricalComponentMissingTerminalsRule.rule_id,
        ElectricalComponentUnconnectedRule.rule_id,
        ElectricalTransformerSameNetRule.rule_id,
        ElectricalSwitchSameNetRule.rule_id,
        ElectricalSwitchgearRoleConnectionRule.rule_id,
        ElectricalSwitchgearFeedChainRule.rule_id,
        ElectricalTieSwitchgearDualSideRule.rule_id,
        ElectricalIncomingTransformerBusbarDirectionRule.rule_id,
        ElectricalTieBusbarSegmentConsistencyRule.rule_id,
        ElectricalBusbarUnderconnectedRule.rule_id,
        ElectricalBranchBoxInsufficientBranchesRule.rule_id,
        ElectricalRelationUnresolvedRule.rule_id,
    ]
