from __future__ import annotations

import re

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
            if _normalized_device_label(device.label):
                continue
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
        labels: dict[tuple[str | None, str], list[Device]] = {}
        for device in model.devices:
            key = _normalized_device_label(device.label)
            if not key or not _label_requires_uniqueness(device.device_type, key):
                continue
            labels.setdefault((device.device_type, key), []).append(device)

        issues: list[Issue] = []
        for (_, label), devices in labels.items():
            duplicate_clusters = [cluster for cluster in _duplicate_device_clusters(devices) if len(cluster) > 1]
            if not duplicate_clusters:
                continue
            cluster_devices = tuple(device for cluster in duplicate_clusters for device in cluster)
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
                        for device in cluster_devices
                    ),
                )
            )
        return RuleResult(issues=tuple(issues))


class DeviceLabelPatternInvalidRule:
    rule_id = 'device.label_pattern_invalid'

    def __init__(self, *, severity: str = 'warning') -> None:
        self._severity = Severity(severity)

    def run(self, model: SystemModel) -> RuleResult:
        issues: list[Issue] = []
        for device in model.devices:
            label = _normalized_device_label(device.label) or ''
            if not label:
                continue
            if _label_matches_device_type(device.device_type, label):
                continue
            issues.append(
                Issue(
                    rule_id=self.rule_id,
                    severity=self._severity,
                    message=f'设备标注格式可能不符合约定：{label}',
                    refs=(
                        ObjectRef(
                            kind='device',
                            id=device.id,
                            source_entity_ids=device.source_entity_ids,
                            extra={'label': label, 'device_type': device.device_type or 'unknown_component'},
                        ),
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


def _label_matches_device_type(device_type: str | None, label: str) -> bool:
    if not device_type:
        return True
    compact = _normalized_device_label(label) or ''
    if not compact:
        return False
    if device_type == 'breaker':
        return _looks_like_breaker_identifier(compact) or _looks_like_breaker_rating_label(compact) or any(
            token in compact for token in ('断路器', '隔离开关', '负荷开关', '熔断器', '复合开关')
        )
    if device_type == 'transformer':
        return bool(re.search(r'(TA|TM)[-#]?\d+', compact, re.IGNORECASE)) or bool(
            re.search(r'\d+#主变', compact, re.IGNORECASE)
        ) or any(
            token in compact for token in ('主变', '变压器', '电流互感器')
        )
    if device_type == 'switchgear_unit':
        return _looks_like_switchgear_identifier(compact) or any(
            token in compact for token in ('开关柜', '配电箱', '联络柜', '进线总柜', '出线柜', '进线单元', '出线单元', '计量单元', '无功补偿单元', '电容器柜', '单元', '柜')
        )
    if device_type == 'cable_branch_box':
        return bool(re.search(r'DF[-#]?\d+', compact, re.IGNORECASE)) or '分支箱' in compact
    if device_type == 'busbar':
        return '母线' in compact
    if device_type == 'feeder':
        return any(token in compact for token in ('进线', '出线', '馈线'))
    return True


def _normalized_device_label(label: str | None) -> str | None:
    if label is None:
        return None
    compact = re.sub(r'\s+', '', str(label))
    compact = compact.translate(str.maketrans({'～': '~', '—': '-', '－': '-', '＃': '#', '／': '/'}))
    return compact or None


def _looks_like_breaker_identifier(label: str) -> bool:
    return bool(
        re.search(
            r'((QF|QS|QK)[-#]?\d+)|(\d+(?:[#-]?\d+)?(?:~\d+(?:[#-]?\d+)?)?(QF|QS|QK))',
            label,
            re.IGNORECASE,
        )
    )


def _looks_like_breaker_rating_label(label: str) -> bool:
    return bool(re.fullmatch(r'\d{2,4}A', label, re.IGNORECASE))


def _looks_like_switchgear_identifier(label: str) -> bool:
    return bool(re.search(r'(DK|DP)[-#]?\d+', label, re.IGNORECASE)) or bool(
        re.search(r'\d+#?.*(柜|单元)', label, re.IGNORECASE)
    )


def _label_requires_uniqueness(device_type: str | None, label: str) -> bool:
    if not device_type:
        return False
    if device_type == 'breaker':
        return _looks_like_breaker_identifier(label)
    if device_type == 'transformer':
        return bool(re.search(r'(TA|TM)[-#]?\d+', label, re.IGNORECASE)) or bool(
            re.search(r'\d+#主变', label, re.IGNORECASE)
        )
    if device_type == 'switchgear_unit':
        return _looks_like_switchgear_identifier(label)
    if device_type == 'cable_branch_box':
        return bool(re.search(r'DF[-#]?\d+', label, re.IGNORECASE))
    if device_type == 'busbar':
        return '母线' in label and _extract_busbar_segment_token(label) is not None
    return False


def _duplicate_device_clusters(devices: list[Device]) -> list[list[Device]]:
    clusters: list[list[Device]] = []
    for device in devices:
        placed = False
        for cluster in clusters:
            if any(_devices_are_duplicate_neighbors(device, existing) for existing in cluster):
                cluster.append(device)
                placed = True
                break
        if not placed:
            clusters.append([device])
    return clusters


def _devices_are_duplicate_neighbors(left: Device, right: Device) -> bool:
    radius = max(60.0, (left.footprint_radius or 0.0) * 4.0, (right.footprint_radius or 0.0) * 4.0)
    return near(left.position, right.position, radius)


def _extract_busbar_segment_token(label: str) -> str | None:
    patterns = (
        r'([IVX]+)段',
        r'([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)段',
        r'([A-Z])段',
        r'(\d+)段',
    )
    for pattern in patterns:
        match = re.search(pattern, label, re.IGNORECASE)
        if match is not None:
            return match.group(1).upper()
    return None
