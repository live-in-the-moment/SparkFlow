from __future__ import annotations

from ..contracts import Issue, ObjectRef, Severity
from ..model.geometry import near
from ..model.types import Device, Point2D, SystemModel
from .types import RuleResult


class FloatingWireEndpointsRule:
    rule_id = 'wire.floating_endpoints'

    def __init__(self, tol: float = 1e-3) -> None:
        self._tol = tol

    def run(self, model: SystemModel) -> RuleResult:
        if model.connectivity is not None:
            return self._run_from_connectivity(model)
        return self._run_from_raw_wires(model)

    def _run_from_connectivity(self, model: SystemModel) -> RuleResult:
        connectivity = model.connectivity
        assert connectivity is not None
        degree = {idx: 0 for idx in range(len(connectivity.nodes))}
        refs_by_node: dict[int, tuple[str, ...]] = {}
        for edge in connectivity.edges:
            degree[edge.a] = degree.get(edge.a, 0) + 1
            degree[edge.b] = degree.get(edge.b, 0) + 1
            if edge.source_entity_ids:
                refs_by_node.setdefault(edge.a, edge.source_entity_ids)
                refs_by_node.setdefault(edge.b, edge.source_entity_ids)
        anchored_nodes = set(connectivity.terminal_anchors.values())

        issues: list[Issue] = []
        for node_id, node_point in enumerate(connectivity.nodes):
            if degree.get(node_id, 0) > 1:
                continue
            if node_id in anchored_nodes:
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message='发现悬空线端点，未与其他线段或设备连接。',
                    refs=(
                        ObjectRef(
                            kind='node',
                            id=f'node:{node_id}',
                            source_entity_ids=refs_by_node.get(node_id, ()),
                            extra={'x': node_point.x, 'y': node_point.y, 'degree': degree.get(node_id, 0)},
                        ),
                    ),
                )
            )
        return RuleResult(issues=tuple(issues))

    def _run_from_raw_wires(self, model: SystemModel) -> RuleResult:
        endpoints: list[tuple[str, Point2D]] = []
        for wire in model.wires:
            endpoints.append((wire.id, wire.a))
            endpoints.append((wire.id, wire.b))

        device_points: list[Point2D] = []
        for device in model.devices:
            if device.terminals:
                device_points.extend(terminal.position for terminal in device.terminals)
            else:
                device_points.append(device.position)

        issues: list[Issue] = []
        for idx, (wire_id, point) in enumerate(endpoints):
            connected = False
            for other_idx, (_, other) in enumerate(endpoints):
                if idx == other_idx:
                    continue
                if near(point, other, self._tol):
                    connected = True
                    break
            if not connected:
                for device_point in device_points:
                    if near(point, device_point, self._tol):
                        connected = True
                        break
            if not connected:
                issues.append(
                    Issue(
                        rule_id=self.rule_id,
                        severity=Severity.ERROR,
                        message='发现悬空线端点，未与其他线段或设备连接。',
                        refs=(
                            ObjectRef(
                                kind='wire',
                                id=wire_id,
                                extra={'x': point.x, 'y': point.y},
                            ),
                        ),
                    )
                )

        return RuleResult(issues=tuple(issues))


class DeviceNeedsNearbyTextRule:
    rule_id = 'device.missing_label'

    def __init__(self, radius: float = 10.0) -> None:
        self._radius = radius

    def run(self, model: SystemModel) -> RuleResult:
        issues: list[Issue] = []
        for device in model.devices:
            if _has_text_nearby(model, device.position, self._radius):
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message='设备附近未发现文本标注。',
                    refs=(
                        ObjectRef(
                            kind='device',
                            id=device.id,
                            source_entity_ids=device.source_entity_ids,
                            extra={'x': device.position.x, 'y': device.position.y},
                        ),
                    ),
                )
            )
        return RuleResult(issues=tuple(issues))


class DuplicateDeviceLabelRule:
    rule_id = 'device.duplicate_label'

    def run(self, model: SystemModel) -> RuleResult:
        labels: dict[str, list[Device]] = {}
        for device in model.devices:
            if not device.label:
                continue
            key = device.label.strip()
            if not key:
                continue
            labels.setdefault(key, []).append(device)

        issues: list[Issue] = []
        for label, devices in labels.items():
            if len(devices) <= 1:
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message=f'发现重复设备标注：{label}',
                    refs=tuple(
                        ObjectRef(
                            kind='device',
                            id=device.id,
                            source_entity_ids=device.source_entity_ids,
                            extra={'label': label},
                        )
                        for device in devices
                    ),
                )
            )
        return RuleResult(issues=tuple(issues))


def _has_text_nearby(model: SystemModel, point: Point2D, radius: float) -> bool:
    for _, text_point, text in model.texts:
        if not text.strip():
            continue
        if near(point, text_point, radius):
            return True
    return False
