from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class WireSegment:
    id: str
    a: Point2D
    b: Point2D
    source_entity_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Terminal:
    id: str
    position: Point2D
    name: str | None = None
    source_entity_ids: tuple[str, ...] = ()
    confidence: float | None = None


@dataclass(frozen=True)
class Device:
    id: str
    position: Point2D
    label: str | None
    device_type: str | None = None
    terminals: tuple[Terminal, ...] = ()
    block_name: str | None = None
    source_entity_ids: tuple[str, ...] = ()
    footprint_radius: float | None = None


@dataclass(frozen=True)
class DrawingSelection:
    drawing_class: str
    reason: str
    eligible_for_electrical: bool


@dataclass(frozen=True)
class ConnectivityEdge:
    a: int
    b: int
    source_entity_ids: tuple[str, ...] = ()
    kind: str = 'wire_segment'


@dataclass(frozen=True)
class ConnectivityGraph:
    tol: float
    nodes: tuple[Point2D, ...]
    edges: tuple[ConnectivityEdge, ...]
    junctions: tuple[int, ...]
    terminal_anchors: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ElectricalComponent:
    id: str
    type: str
    label: str | None
    source_entity_ids: tuple[str, ...] = ()
    terminal_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ElectricalTerminal:
    id: str
    component_id: str
    role: str | None
    x: float
    y: float
    node_id: int | None = None


@dataclass(frozen=True)
class ElectricalNet:
    id: str
    terminal_ids: tuple[str, ...]
    node_ids: tuple[int, ...]


@dataclass(frozen=True)
class ElectricalRelation:
    id: str
    type: str
    from_terminal_id: str
    to_terminal_id: str
    state: str | None = None


@dataclass(frozen=True)
class UnresolvedItem:
    kind: str
    source_entity_ids: tuple[str, ...] = ()
    reason: str = ''
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ElectricalGraph:
    components: tuple[ElectricalComponent, ...] = ()
    terminals: tuple[ElectricalTerminal, ...] = ()
    nets: tuple[ElectricalNet, ...] = ()
    relations: tuple[ElectricalRelation, ...] = ()
    unresolved: tuple[UnresolvedItem, ...] = ()


@dataclass(frozen=True)
class SystemModel:
    wires: tuple[WireSegment, ...] = ()
    devices: tuple[Device, ...] = ()
    texts: tuple[tuple[str, Point2D, str], ...] = ()
    entity_index: dict[str, str] = field(default_factory=dict)
    selection: DrawingSelection | None = None
    unresolved: tuple[UnresolvedItem, ...] = ()
    connectivity: ConnectivityGraph | None = None
    electrical: ElectricalGraph | None = None

    @property
    def topology(self) -> ConnectivityGraph | None:
        return self.connectivity
