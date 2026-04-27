from __future__ import annotations

import math

from .types import Point2D


def dist2(a: Point2D, b: Point2D) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return dx * dx + dy * dy


def dist(a: Point2D, b: Point2D) -> float:
    return math.sqrt(dist2(a, b))


def near(a: Point2D, b: Point2D, tol: float) -> bool:
    return dist2(a, b) <= tol * tol


def segment_length(a: Point2D, b: Point2D) -> float:
    return dist(a, b)


def project_point_to_segment(point: Point2D, a: Point2D, b: Point2D) -> tuple[Point2D, float]:
    dx = b.x - a.x
    dy = b.y - a.y
    denom = dx * dx + dy * dy
    if denom <= 0:
        return a, 0.0
    t = ((point.x - a.x) * dx + (point.y - a.y) * dy) / denom
    t = max(0.0, min(1.0, t))
    return Point2D(a.x + t * dx, a.y + t * dy), t


def distance_point_to_segment(point: Point2D, a: Point2D, b: Point2D) -> float:
    projected, _ = project_point_to_segment(point, a, b)
    return dist(point, projected)
