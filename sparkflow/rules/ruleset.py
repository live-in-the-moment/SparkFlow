from __future__ import annotations

from .rules import DeviceNeedsNearbyTextRule, DuplicateDeviceLabelRule, FloatingWireEndpointsRule
from .topology_rules import (
    ElectricalComponentMissingTerminalsRule,
    ElectricalComponentUnconnectedRule,
    ElectricalRelationUnresolvedRule,
    ElectricalSwitchSameNetRule,
)
from .types import Rule


def rule_version() -> str:
    return 'ruleset_v2'


def default_ruleset() -> list[Rule]:
    return [
        FloatingWireEndpointsRule(),
        DeviceNeedsNearbyTextRule(),
        DuplicateDeviceLabelRule(),
        ElectricalComponentMissingTerminalsRule(),
        ElectricalComponentUnconnectedRule(),
        ElectricalSwitchSameNetRule(),
        ElectricalRelationUnresolvedRule(),
    ]
