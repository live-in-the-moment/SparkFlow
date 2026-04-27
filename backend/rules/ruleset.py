from __future__ import annotations

from .rules import DeviceLabelPatternInvalidRule, DeviceNeedsNearbyTextRule, DuplicateDeviceLabelRule, FloatingWireEndpointsRule
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
)
from .types import Rule


def rule_version() -> str:
    return 'ruleset_v7'


def default_ruleset() -> list[Rule]:
    return [
        FloatingWireEndpointsRule(),
        DeviceNeedsNearbyTextRule(),
        DuplicateDeviceLabelRule(),
        DeviceLabelPatternInvalidRule(),
        ElectricalComponentMissingTerminalsRule(),
        ElectricalComponentUnconnectedRule(),
        ElectricalTransformerSameNetRule(),
        ElectricalSwitchSameNetRule(),
        ElectricalSwitchgearRoleConnectionRule(),
        ElectricalSwitchgearFeedChainRule(),
        ElectricalTieSwitchgearDualSideRule(),
        ElectricalIncomingTransformerBusbarDirectionRule(),
        ElectricalTieBusbarSegmentConsistencyRule(),
        ElectricalBusbarUnderconnectedRule(),
        ElectricalBranchBoxInsufficientBranchesRule(),
        ElectricalRelationUnresolvedRule(),
    ]
