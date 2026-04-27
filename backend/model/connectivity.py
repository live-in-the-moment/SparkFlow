from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .geometry import dist2
from .types import ConnectivityEdge, ConnectivityGraph, Point2D, SystemModel, UnresolvedItem


@dataclass(frozen=True)
class ConnectivityBuildOptions:
    tol: float = 1.0


def build_connectivity(model: SystemModel, *, options: ConnectivityBuildOptions | None = None) -> SystemModel:
    tol = float(options.tol) if options is not None else 1.0
    if tol <= 0:
        tol = 1.0

    points: list[Point2D] = []
    terminal_ids: list[str] = []

    for wire in model.wires:
        points.append(wire.a)
        terminal_ids.append('')
        points.append(wire.b)
        terminal_ids.append('')

    for device in model.devices:
        for terminal in device.terminals:
            points.append(terminal.position)
            terminal_ids.append(terminal.id)

    if not points:
        return model

    clusters = _cluster_points(points, tol=tol)
    node_points = tuple(_centroid([points[idx] for idx in group]) for group in clusters)
    point_to_node: dict[int, int] = {}
    for node_id, group in enumerate(clusters):
        for idx in group:
            point_to_node[idx] = node_id

    unresolved = list(model.unresolved)
    edges: list[ConnectivityEdge] = []
    for wire_index, wire in enumerate(model.wires):
        a_idx = wire_index * 2
        b_idx = wire_index * 2 + 1
        a_node = point_to_node[a_idx]
        b_node = point_to_node[b_idx]
        if a_node == b_node:
            unresolved.append(
                UnresolvedItem(
                    kind='connectivity_edge',
                    source_entity_ids=wire.source_entity_ids,
                    reason='导线端点吸附到同一节点，已跳过自环边。',
                    extra={'wire_id': wire.id, 'node_id': a_node},
                )
            )
            continue
        edges.append(ConnectivityEdge(a=a_node, b=b_node, source_entity_ids=wire.source_entity_ids))

    terminal_anchors: dict[str, int] = {}
    for idx, terminal_id in enumerate(terminal_ids):
        if terminal_id:
            terminal_anchors[terminal_id] = point_to_node[idx]

    used_nodes = set(terminal_anchors.values())
    for edge in edges:
        used_nodes.add(edge.a)
        used_nodes.add(edge.b)
    if len(used_nodes) < len(node_points):
        ordered_nodes = sorted(used_nodes)
        remap = {old: new for new, old in enumerate(ordered_nodes)}
        node_points = tuple(node_points[old] for old in ordered_nodes)
        edges = [
            ConnectivityEdge(a=remap[edge.a], b=remap[edge.b], source_entity_ids=edge.source_entity_ids)
            for edge in edges
        ]
        terminal_anchors = {terminal_id: remap[node_id] for terminal_id, node_id in terminal_anchors.items()}

    degree = _node_degree(len(node_points), edges)
    junctions = tuple(sorted(node_id for node_id, deg in degree.items() if deg >= 3))
    connectivity = ConnectivityGraph(
        tol=tol,
        nodes=node_points,
        edges=tuple(edges),
        junctions=junctions,
        terminal_anchors=terminal_anchors,
    )
    return SystemModel(
        wires=model.wires,
        devices=model.devices,
        texts=model.texts,
        entity_index=model.entity_index,
        selection=model.selection,
        unresolved=tuple(unresolved),
        connectivity=connectivity,
        electrical=model.electrical,
        project_documents=model.project_documents,
    )


def connected_components(node_count: int, edges: Iterable[ConnectivityEdge]) -> list[list[int]]:
    parent = list(range(node_count))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for edge in edges:
        union(edge.a, edge.b)

    groups: dict[int, list[int]] = {}
    for node_id in range(node_count):
        groups.setdefault(find(node_id), []).append(node_id)
    out = list(groups.values())
    out.sort(key=lambda group: (-len(group), min(group)))
    return out


def _cluster_points(points: list[Point2D], *, tol: float) -> list[list[int]]:
    tol2 = tol * tol
    grid: dict[tuple[int, int], list[int]] = {}
    parent = list(range(len(points)))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    def cell(point: Point2D) -> tuple[int, int]:
        return (round(point.x / tol), round(point.y / tol))

    for idx, point in enumerate(points):
        cx, cy = cell(point)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in grid.get((cx + dx, cy + dy), []):
                    if dist2(point, points[other]) <= tol2:
                        union(idx, other)
        grid.setdefault((cx, cy), []).append(idx)

    groups: dict[int, list[int]] = {}
    for idx in range(len(points)):
        groups.setdefault(find(idx), []).append(idx)
    return list(groups.values())


def _centroid(points: list[Point2D]) -> Point2D:
    sx = sum(point.x for point in points)
    sy = sum(point.y for point in points)
    return Point2D(sx / len(points), sy / len(points))


def _node_degree(node_count: int, edges: Iterable[ConnectivityEdge]) -> dict[int, int]:
    degree = {idx: 0 for idx in range(node_count)}
    for edge in edges:
        degree[edge.a] = degree.get(edge.a, 0) + 1
        degree[edge.b] = degree.get(edge.b, 0) + 1
    return degree
