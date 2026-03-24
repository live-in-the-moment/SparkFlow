from __future__ import annotations

from html import escape
from pathlib import Path

from ..model.types import Point2D, SystemModel


def write_debug_svg(model: SystemModel, path: Path, *, title: str | None = None) -> None:
    points = _collect_points(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not points:
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="320"></svg>', encoding='utf-8')
        return

    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)
    width = max(1.0, max_x - min_x)
    height = max(1.0, max_y - min_y)
    pad = max(20.0, max(width, height) * 0.05)
    draw_width = width + pad * 2.0
    draw_height = height + pad * 2.0
    scale = 1200.0 / max(draw_width, draw_height)
    svg_width = max(640, int(draw_width * scale))
    svg_height = max(480, int(draw_height * scale))

    def tx(x: float) -> float:
        return (x - min_x + pad) * scale

    def ty(y: float) -> float:
        return (max_y - y + pad) * scale

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}">',
        '<rect width="100%" height="100%" fill="#0f172a"/>',
        '<g opacity="0.96">',
    ]

    for wire in model.wires:
        lines.append(
            f'<line x1="{tx(wire.a.x):.2f}" y1="{ty(wire.a.y):.2f}" x2="{tx(wire.b.x):.2f}" y2="{ty(wire.b.y):.2f}" stroke="#94a3b8" stroke-width="1.4" />'
        )

    connectivity = model.connectivity
    if connectivity is not None:
        for idx in connectivity.junctions:
            point = connectivity.nodes[idx]
            lines.append(
                f'<circle cx="{tx(point.x):.2f}" cy="{ty(point.y):.2f}" r="3.5" fill="#38bdf8" />'
            )
        for point in connectivity.nodes:
            lines.append(
                f'<circle cx="{tx(point.x):.2f}" cy="{ty(point.y):.2f}" r="1.6" fill="#475569" />'
            )

    for device in model.devices:
        lines.append(
            f'<circle cx="{tx(device.position.x):.2f}" cy="{ty(device.position.y):.2f}" r="5.5" fill="#f43f5e" />'
        )
        label = device.label or device.device_type or device.id
        lines.append(
            f'<text x="{tx(device.position.x) + 7:.2f}" y="{ty(device.position.y) - 7:.2f}" fill="#f8fafc" font-size="11">{escape(label)}</text>'
        )
        for terminal in device.terminals:
            lines.append(
                f'<circle cx="{tx(terminal.position.x):.2f}" cy="{ty(terminal.position.y):.2f}" r="3.0" fill="#f59e0b" />'
            )

    legend_title = escape(title or 'debug_overlay')
    lines.extend(
        [
            '</g>',
            '<g font-size="12" fill="#e2e8f0" font-family="Consolas, Menlo, monospace">',
            f'<text x="16" y="24">{legend_title}</text>',
            '<text x="16" y="44">gray=line  blue=junction  red=device  orange=terminal</text>',
            '</g>',
            '</svg>',
        ]
    )
    path.write_text('\n'.join(lines), encoding='utf-8')


def _collect_points(model: SystemModel) -> list[Point2D]:
    points: list[Point2D] = []
    for wire in model.wires:
        points.extend((wire.a, wire.b))
    for device in model.devices:
        points.append(device.position)
        for terminal in device.terminals:
            points.append(terminal.position)
    if model.connectivity is not None:
        points.extend(model.connectivity.nodes)
    return points
