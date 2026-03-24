from __future__ import annotations

from typing import Any

from .rules import DeviceNeedsNearbyTextRule, DuplicateDeviceLabelRule, FloatingWireEndpointsRule
from .topology_rules import (
    ElectricalComponentMissingTerminalsRule,
    ElectricalComponentUnconnectedRule,
    ElectricalRelationUnresolvedRule,
    ElectricalSwitchSameNetRule,
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
    if rule_id == ElectricalComponentMissingTerminalsRule.rule_id:
        return ElectricalComponentMissingTerminalsRule()
    if rule_id == ElectricalComponentUnconnectedRule.rule_id:
        sev = params.get('severity')
        return ElectricalComponentUnconnectedRule(severity=str(sev)) if sev is not None else ElectricalComponentUnconnectedRule()
    if rule_id == ElectricalSwitchSameNetRule.rule_id:
        return ElectricalSwitchSameNetRule()
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
        ElectricalComponentMissingTerminalsRule.rule_id,
        ElectricalComponentUnconnectedRule.rule_id,
        ElectricalSwitchSameNetRule.rule_id,
        ElectricalRelationUnresolvedRule.rule_id,
    ]
