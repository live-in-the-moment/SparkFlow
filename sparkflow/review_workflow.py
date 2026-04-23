from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterable

import ezdxf
from ezdxf import bbox as ezdxf_bbox

from .cad.parse import CadParseOptions
from .model.build_options import ModelBuildOptions
from .review import ReviewAuditOutput, review_audit

_FRAME_HINTS: dict[str, tuple[float, float, float, float]] = {
    "frame_a3l1hfl": (-25.0, -5.0, 395.0, 292.0),
    "frame_a3l1vl": (-5.0, -5.0, 292.0, 415.0),
    "frame_a4l1v": (-25.0, -37.0, 185.0, 260.0),
}
_FRAME_ORDER = ("frame_a3l1hfl", "frame_a3l1vl", "frame_a4l1v")
_FRAME_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "frame_a3l1hfl": ("擎能a3横",),
    "frame_a3l1vl": ("擎能a3竖",),
    "frame_a4l1v": ("擎能a4竖",),
}
_CODE_PATTERNS = (
    re.compile(r"\b[0-9A-Z]{2,}(?:-[0-9A-Z]{1,})*-(?:\d{2,3}|[A-Z]\d{2,3})\b", re.IGNORECASE),
)
_PLACEHOLDER_RE = re.compile(r"(?:FXX|FXXX|XXX|XXXX|XX工程|暂命名)", re.IGNORECASE)
_TITLE_GENERIC_LABELS = {
    "图号",
    "设计阶段",
    "施工图",
    "比例",
    "日期",
    "审核",
    "校核",
    "批准",
    "设计",
    "核定",
    "会签",
}
_TITLE_STRONG_HINTS = ("单线图", "系统图", "平断面图", "示意图", "接线图", "走向图", "布置图", "安装图", "材料表", "目录")
_TITLE_WEAK_HINTS = ("图", "表", "示意", "布置", "系统", "接线", "大样", "安装", "目录")


@dataclass(frozen=True)
class ReviewPipelineOutput:
    run_dir: Path
    drawing_info_json_path: Path
    review_rules_json_path: Path
    review_report_json_path: Path
    review_report_md_path: Path
    sparkflow_report_json_path: Path | None
    sparkflow_report_md_path: Path | None
    split_manifest_json_path: Path
    rectification_checklist_md_path: Path
    rectification_checklist_json_path: Path

    @property
    def review_bundle_json_path(self) -> Path:
        return self.review_rules_json_path


@dataclass(frozen=True)
class _FrameRef:
    seq: int
    kind: str
    bbox: tuple[float, float, float, float]
    center: tuple[float, float]


@dataclass(frozen=True)
class _TextItem:
    text: str
    x: float
    y: float
    space: str
    height: float


@dataclass(frozen=True)
class _LineItem:
    x1: float
    y1: float
    x2: float
    y2: float
    space: str


@dataclass(frozen=True)
class _ViewportRef:
    center_x: float
    center_y: float
    width: float
    height: float
    view_center_x: float
    view_center_y: float
    view_height: float
    twist_angle_deg: float


def review_pipeline(
    drawing_path: Path,
    review_dir: Path,
    out_dir: Path,
    *,
    project_code: str | None = None,
    parse_options: CadParseOptions | None = None,
    level: int = 3,
    model_options: ModelBuildOptions | None = None,
    ruleset_dir: Path | None = None,
    selection_mode: str = "auto",
    graph: str = "electrical",
    include_sparkflow_audit: bool = True,
) -> ReviewPipelineOutput:
    review_output = review_audit(
        drawing_path,
        review_dir,
        out_dir,
        project_code=project_code,
        parse_options=parse_options,
        level=level,
        model_options=model_options,
        ruleset_dir=ruleset_dir,
        selection_mode=selection_mode,
        graph=graph,
        include_sparkflow_audit=include_sparkflow_audit,
    )
    drawing_info = _read_json(review_output.drawing_info_json_path)
    split_source_path = _resolve_split_source_path(drawing_path, drawing_info)
    split_manifest_json_path = split_review_pages(split_source_path, review_output.run_dir / "split")
    review_report = _read_json(review_output.review_report_json_path)
    manifest = _read_json(split_manifest_json_path)
    checklist = build_rectification_checklist(review_report, manifest)
    checklist["split_manifest_json_path"] = str(split_manifest_json_path)
    checklist["review_report_json_path"] = str(review_output.review_report_json_path)
    checklist["drawing_info_json_path"] = str(review_output.drawing_info_json_path)
    checklist["review_rules_json_path"] = str(review_output.review_rules_json_path)
    checklist["review_bundle_json_path"] = str(review_output.review_rules_json_path)

    rectification_checklist_md_path = review_output.run_dir / "整改问题清单.md"
    rectification_checklist_json_path = review_output.run_dir / "整改问题清单.json"
    rectification_checklist_md_path.write_text(
        render_rectification_checklist_markdown(checklist),
        encoding="utf-8",
    )
    rectification_checklist_json_path.write_text(
        json.dumps(checklist, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ReviewPipelineOutput(
        run_dir=review_output.run_dir,
        drawing_info_json_path=review_output.drawing_info_json_path,
        review_rules_json_path=review_output.review_rules_json_path,
        review_report_json_path=review_output.review_report_json_path,
        review_report_md_path=review_output.review_report_md_path,
        sparkflow_report_json_path=review_output.sparkflow_report_json_path,
        sparkflow_report_md_path=review_output.sparkflow_report_md_path,
        split_manifest_json_path=split_manifest_json_path,
        rectification_checklist_md_path=rectification_checklist_md_path,
        rectification_checklist_json_path=rectification_checklist_json_path,
    )


def split_review_pages(path: Path, out_dir: Path) -> Path:
    doc = ezdxf.readfile(path)
    layout = _resolve_layout(doc)
    out_dir = out_dir.resolve()
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    frames = _collect_frames(layout)
    layout_texts, layout_lines = _collect_space_items(layout, space_name="layout")
    layout_viewports = _collect_viewports(layout)
    model_texts, model_lines = _collect_space_items(doc.modelspace(), space_name="model")
    directory_maps: dict[str, str] = {}
    frame_payloads: list[dict[str, Any]] = []
    for frame in frames:
        payload = _build_page_payload(
            frame,
            layout_texts=layout_texts,
            layout_lines=layout_lines,
            layout_viewports=layout_viewports,
            model_texts=model_texts,
            model_lines=model_lines,
        )
        frame_payloads.append(payload)
        if frame.kind == "frame_a4l1v":
            directory_maps.update(_extract_directory_titles(payload["texts"]))

    manifest: list[dict[str, Any]] = []
    directory_index = 0
    used_slugs: set[str] = set()
    for payload in frame_payloads:
        codes = payload["codes"]
        primary_code = _pick_primary_code(codes, directory_maps)
        sheet_no = None if payload["frame"].kind == "frame_a4l1v" else _infer_sheet_no([primary_code] if primary_code else codes)
        page_seq = payload["frame"].seq
        title = directory_maps.get(primary_code, "") if primary_code else ""
        if not title:
            title = _infer_page_title(payload["texts"], codes, bbox=payload["frame"].bbox)
        title_part_no, title_part_total = _infer_title_part(title)
        if payload["frame"].kind == "frame_a4l1v":
            directory_index += 1
            slug = f"directory_{directory_index}"
        else:
            resolved_code = primary_code or (codes[0] if codes else f"page_{payload['frame'].seq}")
            prefix_no = sheet_no if sheet_no is not None else page_seq
            prefix = f"{prefix_no:02d}_"
            slug = f"{prefix}{resolved_code}"
        slug = _dedupe_slug(slug, used_slugs)
        svg_path = pages_dir / f"{slug}.svg"
        png_path = pages_dir / f"{slug}.png"
        texts_path = pages_dir / f"{slug}.texts.json"
        _write_page_svg(svg_path, payload["frame"].bbox, payload["drawables"], title=title or slug)
        _write_page_png(svg_path, png_path)
        texts_path.write_text(
            json.dumps(
                {
                    "texts": [
                        {
                            "text": item.text,
                            "x": item.x,
                            "y": item.y,
                            "space": item.space,
                        }
                        for item in payload["texts"]
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        placeholder_texts = _extract_placeholder_texts(payload["texts"])
        manifest.append(
            {
                "slug": slug,
                "seq": payload["frame"].seq,
                "sheet_no": sheet_no,
                "page_seq": page_seq,
                "title_part_no": title_part_no,
                "title_part_total": title_part_total,
                "kind": payload["frame"].kind,
                "primary_code": primary_code or (codes[0] if codes else ""),
                "codes": codes,
                "title": title,
                "bbox": list(payload["frame"].bbox),
                "viewport": payload["has_viewport"],
                "svg_path": str(svg_path),
                "png_path": str(png_path) if png_path.exists() else None,
                "texts_path": str(texts_path),
                "text_count": len(payload["texts"]),
                "placeholder_texts": placeholder_texts,
            }
        )

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def build_rectification_checklist(review_report: dict[str, Any], manifest: list[dict[str, Any]]) -> dict[str, Any]:
    page_issues = _build_page_issues(manifest)
    grouped_review_issues = _build_review_issues(review_report, manifest)
    drawing_issues = grouped_review_issues["drawing_issues"]
    manual_issues = grouped_review_issues["manual_issues"]
    review_issues = drawing_issues + manual_issues
    summary = review_report.get("summary") or {}
    placeholder_count = int(summary.get("placeholder_text_count") or 0)
    if placeholder_count <= 0:
        placeholder_count = sum(len(item.get("placeholder_texts") or []) for item in page_issues)
    drawing_rule_count = len(drawing_issues)
    manual_rule_count = len(manual_issues)
    filtered_candidate_count = int(summary.get("filtered_candidate_count") or 0)
    if filtered_candidate_count <= 0:
        filtered_candidate_count = drawing_rule_count + manual_rule_count
    return {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "project_code": review_report.get("project_code"),
        "project_name": review_report.get("project_name"),
        "input_path": review_report.get("input_path"),
        "review_dir": review_report.get("review_dir"),
        "review_report_json_path": review_report.get("review_report_json_path"),
        "drawing_info_json_path": review_report.get("drawing_info_json_path"),
        "review_rules_json_path": review_report.get("review_rules_json_path"),
        "review_bundle_json_path": review_report.get("review_bundle_json_path"),
        "split_manifest_json_path": None,
        "summary": {
            "split_page_count": len(manifest),
            "page_issue_count": len(page_issues),
            "review_issue_count": len(review_issues),
            "placeholder_text_count": placeholder_count,
            "drawing_rule_count": drawing_rule_count,
            "manual_rule_count": manual_rule_count,
            "filtered_candidate_count": filtered_candidate_count,
            "review_rule_counts": summary.get("review_rule_counts") or {},
            "requirement_counts": summary.get("requirement_counts") or {},
        },
        "page_issues": page_issues,
        "review_issues": review_issues,
        "drawing_issues": drawing_issues,
        "manual_issues": manual_issues,
    }


def render_rectification_checklist_markdown(checklist: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 整改问题清单")
    lines.append("")
    lines.append(f"- 工程编号：{checklist.get('project_code') or ''}")
    lines.append(f"- 工程名称：{checklist.get('project_name') or ''}")
    lines.append(f"- 图纸路径：{checklist.get('input_path') or ''}")
    lines.append(f"- 评审意见目录：{checklist.get('review_dir') or ''}")
    lines.append("")
    lines.append("## 1. 审核摘要")
    lines.append("")
    summary = checklist.get("summary") or {}
    for key in (
        "split_page_count",
        "page_issue_count",
        "review_issue_count",
        "placeholder_text_count",
        "drawing_rule_count",
        "manual_rule_count",
        "filtered_candidate_count",
    ):
        lines.append(f"- {key}: {summary.get(key)}")
    review_rule_counts = summary.get("review_rule_counts") or {}
    if review_rule_counts:
        lines.append(
            "- review_rule_counts: "
            + "；".join(f"{key}={value}" for key, value in review_rule_counts.items())
        )
    requirement_counts = summary.get("requirement_counts") or {}
    if requirement_counts:
        lines.append(
            "- requirement_counts: "
            + "；".join(f"{key}={value}" for key, value in requirement_counts.items())
        )
    lines.append("")
    lines.append("## 2. 逐页整改项")
    lines.append("")
    page_issues = checklist.get("page_issues") or []
    if not page_issues:
        lines.append("无逐页占位符或未定稿问题。")
    else:
        for index, item in enumerate(page_issues, start=1):
            lines.append(f"### 2.{index} {item['page_label']}")
            lines.append("")
            lines.append(f"- 图号：{item['code']}")
            lines.append(f"- 证据文件：`{item['texts_path']}`")
            lines.append(f"- 问题描述：{item['problem']}")
            lines.append(f"- 整改建议：{item['suggestion']}")
            lines.append("")
    lines.append("## 3. 评审规则审查情况（图纸可判定）")
    lines.append("")
    drawing_issues = checklist.get("drawing_issues") or []
    if not drawing_issues:
        lines.append("无图纸可判定规则待跟踪。")
    else:
        for index, item in enumerate(drawing_issues, start=1):
            lines.append(f"### 3.{index} {item['title']}")
            lines.append("")
            lines.append(f"- 结果：{item['result']}")
            lines.append(f"- 评审规则：{item['text']}")
            if item.get("reply"):
                lines.append(f"- 回复：{item['reply']}")
            if item.get("related_pages"):
                lines.append("- 关联图纸：" + "；".join(item["related_pages"]))
            lines.append(f"- 说明：{item['explanation']}")
            lines.append("")
    lines.append("## 4 人工复核项（非图纸自动判定）")
    lines.append("")
    manual_issues = checklist.get("manual_issues") or []
    if not manual_issues:
        lines.append("无人工复核项。")
    else:
        for index, item in enumerate(manual_issues, start=1):
            lines.append(f"### 4.{index} {item['title']}")
            lines.append("")
            lines.append(f"- 结果：{item['result']}")
            lines.append(f"- 评审规则：{item['text']}")
            if item.get("reply"):
                lines.append(f"- 回复：{item['reply']}")
            if item.get("related_pages"):
                lines.append("- 关联图纸：" + "；".join(item["related_pages"]))
            lines.append(f"- 说明：{item['explanation']}")
            lines.append("- 固定说明：依赖附件资料，系统不做自动通过/不通过判定。")
            lines.append("")
    return "\n".join(lines)


def _resolve_split_source_path(drawing_path: Path, drawing_info: dict[str, Any]) -> Path:
    parse_meta = drawing_info.get("parse_meta") if isinstance(drawing_info.get("parse_meta"), dict) else {}
    converted_dxf = parse_meta.get("converted_dxf")
    if converted_dxf:
        return Path(str(converted_dxf)).resolve()
    return drawing_path.resolve()


def _resolve_layout(doc: ezdxf.EzDxfDocument):
    try:
        return doc.layouts.get("Layout1")
    except Exception:
        try:
            return doc.layout()
        except Exception:
            return doc.modelspace()


def _collect_frames(layout) -> list[_FrameRef]:
    frames: list[_FrameRef] = []
    block_bbox_cache: dict[str, tuple[float, float, float, float] | None] = {}
    doc = getattr(layout, "doc", None)
    for entity in layout:
        if entity.dxftype() != "INSERT":
            continue
        kind = _frame_kind(str(entity.dxf.name))
        if not kind:
            continue
        bbox = _frame_bbox(entity, kind, doc=doc, block_bbox_cache=block_bbox_cache)
        frames.append(
            _FrameRef(
                seq=0,
                kind=kind,
                bbox=bbox,
                center=((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0),
            )
        )
    ordered = sorted(frames, key=lambda item: (-item.center[1], item.center[0], _FRAME_ORDER.index(item.kind)))
    return [
        _FrameRef(seq=index, kind=item.kind, bbox=item.bbox, center=item.center)
        for index, item in enumerate(ordered, start=1)
    ]


def _frame_kind(name: str) -> str | None:
    lowered = name.lower()
    for key in _FRAME_ORDER:
        if key in lowered:
            return key
    for kind, aliases in _FRAME_NAME_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return kind
    return None


def _frame_bbox(
    insert,
    kind: str,
    *,
    doc: ezdxf.EzDxfDocument | None,
    block_bbox_cache: dict[str, tuple[float, float, float, float] | None],
) -> tuple[float, float, float, float]:
    origin = insert.dxf.insert
    xscale = float(getattr(insert.dxf, "xscale", 1.0) or 1.0)
    yscale = float(getattr(insert.dxf, "yscale", 1.0) or 1.0)
    block_name = str(insert.dxf.name)
    cached_bbox = block_bbox_cache.get(block_name)
    if cached_bbox is None and block_name not in block_bbox_cache:
        cached_bbox = _resolve_block_frame_bbox(doc, block_name, kind)
        block_bbox_cache[block_name] = cached_bbox
    if cached_bbox is None:
        cached_bbox = _FRAME_HINTS[kind]
    min_x, min_y, max_x, max_y = cached_bbox
    x0 = float(origin[0]) + min_x * xscale
    y0 = float(origin[1]) + min_y * yscale
    x1 = float(origin[0]) + max_x * xscale
    y1 = float(origin[1]) + max_y * yscale
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _resolve_block_frame_bbox(
    doc: ezdxf.EzDxfDocument | None,
    block_name: str,
    kind: str,
) -> tuple[float, float, float, float] | None:
    if doc is None:
        return None
    try:
        block = doc.blocks.get(block_name)
    except Exception:
        return None
    try:
        extents = ezdxf_bbox.extents(block)
    except Exception:
        return None
    min_x = float(extents.extmin.x)
    min_y = float(extents.extmin.y)
    max_x = float(extents.extmax.x)
    max_y = float(extents.extmax.y)
    expected = _FRAME_HINTS[kind]
    expected_width = expected[2] - expected[0]
    expected_height = expected[3] - expected[1]
    actual_width = max_x - min_x
    actual_height = max_y - min_y
    tolerance = max(expected_width, expected_height) * 0.35
    if abs(actual_width - expected_width) > tolerance or abs(actual_height - expected_height) > tolerance:
        return None
    return (min_x, min_y, max_x, max_y)


def _build_page_payload(
    frame: _FrameRef,
    *,
    layout_texts: list[_TextItem],
    layout_lines: list[_LineItem],
    layout_viewports: list[_ViewportRef],
    model_texts: list[_TextItem],
    model_lines: list[_LineItem],
) -> dict[str, Any]:
    bbox = frame.bbox
    texts = [item for item in layout_texts if _point_in_bbox(item.x, item.y, bbox)]
    drawables: list[_TextItem | _LineItem] = texts + [
        item for item in layout_lines if _line_intersects_bbox(item, bbox)
    ]
    viewports = [
        item for item in layout_viewports if _point_in_bbox(item.center_x, item.center_y, bbox)
    ]
    if viewports:
        viewport_texts, viewport_drawables = _collect_modelspace_payload(model_texts, model_lines, viewports, bbox)
        texts = _dedupe_texts(texts + viewport_texts)
        drawables = drawables + viewport_drawables
    texts = sorted(texts, key=lambda item: (round(-item.y, 3), round(item.x, 3), item.text))
    codes = _extract_page_codes(texts, bbox=bbox, kind=frame.kind)
    return {
        "frame": frame,
        "texts": texts,
        "drawables": drawables,
        "codes": codes,
        "has_viewport": bool(viewports),
    }


def _collect_space_items(space_obj, *, space_name: str) -> tuple[list[_TextItem], list[_LineItem]]:
    texts: list[_TextItem] = []
    lines: list[_LineItem] = []
    for entity in _iter_supported_entities(space_obj):
        text_item = _entity_to_text_item(entity, space=space_name)
        if text_item is None:
            lines.extend(_entity_to_line_items(entity, None, space=space_name))
            continue
        texts.append(text_item)
    return texts, lines


def _collect_viewports(layout, bbox: tuple[float, float, float, float] | None = None) -> list[_ViewportRef]:
    viewports: list[_ViewportRef] = []
    for entity in layout:
        if entity.dxftype() != "VIEWPORT":
            continue
        status = int(getattr(entity.dxf, "status", 0) or 0)
        if status <= 1:
            continue
        center = getattr(entity.dxf, "center", None)
        if center is None:
            continue
        center_x = float(center[0])
        center_y = float(center[1])
        if bbox is not None and not _point_in_bbox(center_x, center_y, bbox):
            continue
        viewports.append(
            _ViewportRef(
                center_x=center_x,
                center_y=center_y,
                width=float(getattr(entity.dxf, "width", 0.0) or 0.0),
                height=float(getattr(entity.dxf, "height", 0.0) or 0.0),
                view_center_x=float(getattr(entity.dxf, "view_center_point", center)[0]),
                view_center_y=float(getattr(entity.dxf, "view_center_point", center)[1]),
                view_height=float(getattr(entity.dxf, "view_height", 0.0) or 0.0),
                twist_angle_deg=float(getattr(entity.dxf, "view_twist_angle", 0.0) or 0.0),
            )
        )
    return viewports


def _collect_modelspace_payload(
    model_texts: list[_TextItem],
    model_lines: list[_LineItem],
    viewports: list[_ViewportRef],
    bbox: tuple[float, float, float, float],
) -> tuple[list[_TextItem], list[_TextItem | _LineItem]]:
    texts: list[_TextItem] = []
    drawables: list[_TextItem | _LineItem] = []
    for viewport in viewports:
        model_bbox = _viewport_model_bbox(viewport)
        scale = viewport.height / viewport.view_height if viewport.view_height else 1.0
        for text_item in model_texts:
            if not _point_in_bbox(text_item.x, text_item.y, model_bbox):
                continue
            mapped = _map_text_to_viewport(text_item, viewport, scale)
            if _point_in_bbox(mapped.x, mapped.y, bbox):
                texts.append(mapped)
                drawables.append(mapped)
        for line in model_lines:
            if not _line_intersects_bbox(line, model_bbox):
                continue
            mapped = _map_line_to_viewport(line, viewport, scale)
            if _line_intersects_bbox(mapped, bbox):
                drawables.append(mapped)
    return _dedupe_texts(texts), drawables


def _iter_supported_entities(space) -> Iterable[Any]:
    for entity in space:
        yield from _expand_entity(entity)


def _expand_entity(entity) -> Iterable[Any]:
    if entity.dxftype() != "INSERT":
        yield entity
        return
    yield entity
    try:
        virtuals = list(entity.virtual_entities())
    except Exception:
        return
    for item in virtuals:
        yield from _expand_entity(item)
    for attrib in getattr(entity, "attribs", []) or []:
        yield attrib


def _entity_to_text_item(entity, *, space: str) -> _TextItem | None:
    kind = entity.dxftype()
    if kind == "TEXT":
        insert = getattr(entity.dxf, "insert", None)
        raw = getattr(entity.dxf, "text", "")
        height = float(getattr(entity.dxf, "height", 0.0) or 0.0)
    elif kind == "MTEXT":
        insert = getattr(entity.dxf, "insert", None)
        raw = entity.plain_text()
        height = float(getattr(entity.dxf, "char_height", 0.0) or 0.0)
    elif kind in {"ATTRIB", "ATTDEF"}:
        insert = getattr(entity.dxf, "insert", None)
        raw = getattr(entity.dxf, "text", "")
        height = float(getattr(entity.dxf, "height", 0.0) or 0.0)
    else:
        return None
    if insert is None:
        return None
    text = str(raw or "").strip()
    if not text:
        return None
    return _TextItem(
        text=text,
        x=float(insert[0]),
        y=float(insert[1]),
        space=space,
        height=height or 6.0,
    )


def _entity_to_line_items(
    entity,
    bbox: tuple[float, float, float, float] | None,
    *,
    space: str,
) -> list[_LineItem]:
    kind = entity.dxftype()
    items: list[_LineItem] = []
    if kind == "LINE":
        start = getattr(entity.dxf, "start", None)
        end = getattr(entity.dxf, "end", None)
        if start is None or end is None:
            return items
        candidate = _LineItem(float(start[0]), float(start[1]), float(end[0]), float(end[1]), space)
        if bbox is None or _line_intersects_bbox(candidate, bbox):
            return [candidate]
        return []
    if kind == "LWPOLYLINE":
        try:
            points = [(float(x), float(y)) for x, y, *_ in entity.get_points("xy")]
        except Exception:
            return items
        return _polyline_to_lines(points, bbox, space=space, closed=bool(entity.closed))
    if kind == "POLYLINE":
        try:
            points = [(float(vertex.dxf.location[0]), float(vertex.dxf.location[1])) for vertex in entity.vertices]
        except Exception:
            return items
        return _polyline_to_lines(points, bbox, space=space, closed=bool(entity.is_closed))
    return items


def _polyline_to_lines(
    points: list[tuple[float, float]],
    bbox: tuple[float, float, float, float] | None,
    *,
    space: str,
    closed: bool,
) -> list[_LineItem]:
    if len(points) < 2:
        return []
    segments = list(zip(points, points[1:]))
    if closed:
        segments.append((points[-1], points[0]))
    lines = [
        _LineItem(start[0], start[1], end[0], end[1], space)
        for start, end in segments
    ]
    if bbox is None:
        return lines
    return [item for item in lines if _line_intersects_bbox(item, bbox)]


def _viewport_model_bbox(viewport: _ViewportRef) -> tuple[float, float, float, float]:
    aspect = viewport.width / viewport.height if viewport.height else 1.0
    view_width = viewport.view_height * aspect
    return (
        viewport.view_center_x - view_width / 2.0,
        viewport.view_center_y - viewport.view_height / 2.0,
        viewport.view_center_x + view_width / 2.0,
        viewport.view_center_y + viewport.view_height / 2.0,
    )


def _map_text_to_viewport(text: _TextItem, viewport: _ViewportRef, scale: float) -> _TextItem:
    x, y = _map_point_to_viewport(text.x, text.y, viewport, scale)
    return _TextItem(text=text.text, x=x, y=y, space="viewport", height=max(text.height * scale, 4.0))


def _map_line_to_viewport(line: _LineItem, viewport: _ViewportRef, scale: float) -> _LineItem:
    x1, y1 = _map_point_to_viewport(line.x1, line.y1, viewport, scale)
    x2, y2 = _map_point_to_viewport(line.x2, line.y2, viewport, scale)
    return _LineItem(x1=x1, y1=y1, x2=x2, y2=y2, space="viewport")


def _map_point_to_viewport(x: float, y: float, viewport: _ViewportRef, scale: float) -> tuple[float, float]:
    dx = x - viewport.view_center_x
    dy = y - viewport.view_center_y
    if viewport.twist_angle_deg:
        angle = math.radians(-viewport.twist_angle_deg)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dx, dy = (dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a)
    return (viewport.center_x + dx * scale, viewport.center_y + dy * scale)


def _extract_directory_titles(texts: list[_TextItem]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    codes = [item for item in texts if _is_code_text(item.text)]
    titles = [item for item in texts if _looks_like_title(item.text)]
    for code in codes:
        candidates = [
            item
            for item in titles
            if item.x >= code.x and item.text != code.text
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda item: (abs(item.y - code.y) * 8.0 + max(item.x - code.x, 0.0), -len(item.text)))
        mapping[code.text] = best.text
    return mapping


def _infer_sheet_no(codes: list[str]) -> int | None:
    if not codes:
        return None
    tail = codes[0].rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _pick_primary_code(codes: list[str], directory_maps: dict[str, str]) -> str:
    for code in codes:
        if code in directory_maps:
            return code
    ranked = sorted(codes, key=_code_priority, reverse=True)
    return ranked[0] if ranked else ""


def _infer_page_title(
    texts: list[_TextItem],
    codes: list[str],
    *,
    bbox: tuple[float, float, float, float] | None = None,
) -> str:
    code_set = set(codes)
    candidates = [item for item in texts if _looks_like_title(item.text) and item.text not in code_set]
    if bbox is not None:
        title_band_candidates = [item for item in candidates if _is_in_title_band(item, bbox)]
        if title_band_candidates:
            candidates = title_band_candidates
    if not candidates:
        return ""
    ranked = sorted(candidates, key=_title_priority, reverse=True)
    return ranked[0].text


def _looks_like_title(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped or _is_code_text(stripped):
        return False
    if _PLACEHOLDER_RE.search(stripped):
        return False
    if _normalized_text(stripped) in _TITLE_GENERIC_LABELS:
        return False
    return any(token in stripped for token in _TITLE_WEAK_HINTS)


def _extract_page_codes(
    texts: list[_TextItem],
    *,
    bbox: tuple[float, float, float, float],
    kind: str,
) -> list[str]:
    if kind != "frame_a4l1v":
        title_band_codes = _extract_codes_from_items(item for item in texts if _is_in_title_band(item, bbox))
        if title_band_codes:
            return title_band_codes
    return _extract_codes_from_items(texts)


def _extract_codes_from_items(items: Iterable[_TextItem]) -> list[str]:
    codes: list[str] = []
    for item in items:
        for match in _find_code_matches(item.text):
            if match not in codes:
                codes.append(match)
    return codes


def _find_code_matches(text: str) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    matches: list[str] = []
    for pattern in _CODE_PATTERNS:
        for match in pattern.finditer(value):
            candidate = match.group(0).strip()
            if candidate not in matches:
                matches.append(candidate)
    return matches


def _is_code_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return any(pattern.fullmatch(value) for pattern in _CODE_PATTERNS)


def _code_priority(code: str) -> tuple[int, int, int]:
    value = str(code or "").strip().upper()
    hyphen_count = value.count("-")
    score = len(value)
    if re.fullmatch(r"[0-9A-Z]{8,}-[A-Z]\d{2,3}", value):
        score += 80
    if any(value.startswith(prefix) for prefix in ("CSG-", "GD-", "4K-", "035")):
        score += 40
    if hyphen_count >= 3:
        score += hyphen_count * 6
    if re.search(r"[A-Z]", value) and re.search(r"\d", value):
        score += 10
    return score, hyphen_count, len(value)


def _title_priority(item: _TextItem) -> tuple[int, int, float]:
    text = str(item.text or "").strip()
    normalized = _normalized_text(text)
    score = len(normalized)
    if any(token in normalized for token in _TITLE_STRONG_HINTS):
        score += 120
    if re.search(r"\d+/\d+", normalized):
        score += 30
    if any(token in normalized for token in ("改造前", "改造后", "一次接线", "单线")):
        score += 20
    if normalized in _TITLE_GENERIC_LABELS:
        score -= 1000
    return score, len(normalized), -item.y


def _is_in_title_band(item: _TextItem, bbox: tuple[float, float, float, float]) -> bool:
    band_height = max((bbox[3] - bbox[1]) * 0.16, 42.0)
    return bbox[1] <= item.y <= bbox[1] + band_height


def _normalized_text(text: str) -> str:
    return "".join(str(text or "").split())


def _infer_title_part(title: str) -> tuple[int | None, int | None]:
    normalized = _normalized_text(title)
    match = re.search(r"(\d+)\s*/\s*(\d+)", normalized)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _dedupe_texts(items: list[_TextItem]) -> list[_TextItem]:
    seen: set[tuple[str, int, int, str]] = set()
    result: list[_TextItem] = []
    for item in items:
        key = (item.text, round(item.x * 1000), round(item.y * 1000), item.space)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe_slug(slug: str, used_slugs: set[str]) -> str:
    candidate = slug
    index = 2
    while candidate in used_slugs:
        candidate = f"{slug}_{index}"
        index += 1
    used_slugs.add(candidate)
    return candidate


def _extract_placeholder_texts(texts: list[_TextItem]) -> list[str]:
    placeholders: list[str] = []
    for item in texts:
        normalized = _normalize_placeholder_text(item.text)
        if normalized and normalized not in placeholders:
            placeholders.append(normalized)
    return sorted(placeholders)


def _normalize_placeholder_text(text: str) -> str | None:
    value = " ".join(str(text or "").split())
    if not value or not _PLACEHOLDER_RE.search(value):
        return None
    if len(value) > 80:
        return None
    return value


def _build_page_issues(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for page in manifest:
        placeholders = list(page.get("placeholder_texts") or [])
        if not placeholders:
            continue
        title = str(page.get("title") or "") or "未识别图名"
        code = (page.get("codes") or [""])[0]
        issues.append(
            {
                "sheet_no": page.get("sheet_no"),
                "page_seq": page.get("page_seq"),
                "code": page.get("primary_code") or code,
                "page_label": f"{_page_index_label(page)} {title}".strip(),
                "problem": "存在占位符或未定稿文本：" + "；".join(placeholders),
                "suggestion": "将占位符、临时命名和未定稿编号替换为正式线路名称、间隔号和设备名称后再出图。",
                "texts_path": page.get("texts_path"),
                "png_path": page.get("png_path"),
                "svg_path": page.get("svg_path"),
                "placeholder_texts": placeholders,
            }
        )
    return issues


def _build_review_issues(review_report: dict[str, Any], manifest: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    drawing_issues: list[dict[str, Any]] = []
    manual_issues: list[dict[str, Any]] = []
    for item in review_report.get("review_rule_results") or []:
        result = str(item.get("result") or "")
        if result == "passed":
            continue
        related_pages = _match_related_pages(item, manifest)
        issue = {
            "title": f"{item.get('rule_id', '')}",
            "result": result,
            "text": item.get("source_text") or "",
            "reply": item.get("reply") or "",
            "related_pages": related_pages,
            "explanation": item.get("explanation") or "",
        }
        scope = str(item.get("scope") or "").strip().lower()
        check_type = str(item.get("check_type") or "").strip().lower()
        if scope == "drawing" or check_type == "drawing":
            drawing_issues.append(issue)
        else:
            manual_issues.append(issue)
    return {
        "drawing_issues": drawing_issues,
        "manual_issues": manual_issues,
    }


def _match_related_pages(item: dict[str, Any], manifest: list[dict[str, Any]]) -> list[str]:
    keywords = [str(value).strip() for value in (item.get("keywords") or []) if str(value).strip()]
    if not keywords:
        return []
    related: list[str] = []
    for page in manifest:
        haystacks = [str(page.get("title") or "")]
        haystacks.extend(str(value) for value in (page.get("codes") or []))
        text = " ".join(haystacks)
        if any(keyword in text for keyword in keywords):
            label = f"{_page_index_label(page)} {page.get('title') or page.get('slug')}"
            related.append(label)
    return related


def _page_index_label(page: dict[str, Any]) -> str:
    value = page.get("sheet_no")
    if isinstance(value, int):
        return str(value)
    value = page.get("page_seq")
    if isinstance(value, int):
        return str(value)
    return "-"


def _write_page_svg(
    path: Path,
    bbox: tuple[float, float, float, float],
    drawables: list[_TextItem | _LineItem],
    *,
    title: str,
) -> None:
    width = max(1.0, bbox[2] - bbox[0])
    height = max(1.0, bbox[3] - bbox[1])

    def tx(x: float) -> float:
        return x - bbox[0]

    def ty(y: float) -> float:
        return bbox[3] - y

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(width * 3)}" height="{int(height * 3)}" viewBox="0 0 {width:.2f} {height:.2f}">',
        '<rect width="100%" height="100%" fill="#000000" />',
        '<g stroke="#d4d4d4" fill="none" stroke-width="0.5">',
    ]
    for item in drawables:
        if isinstance(item, _LineItem):
            lines.append(
                f'<line x1="{tx(item.x1):.2f}" y1="{ty(item.y1):.2f}" x2="{tx(item.x2):.2f}" y2="{ty(item.y2):.2f}" />'
            )
    lines.append("</g>")
    lines.append('<g fill="#f5f5f5" font-family="SimSun, Microsoft YaHei, sans-serif">')
    for item in drawables:
        if isinstance(item, _TextItem):
            font_size = max(3.6, min(item.height * 1.2, 16.0))
            lines.append(
                f'<text x="{tx(item.x):.2f}" y="{ty(item.y):.2f}" font-size="{font_size:.2f}">{escape(item.text)}</text>'
            )
    lines.append("</g>")
    lines.append(
        f'<text x="6" y="16" font-size="10" fill="#60a5fa" font-family="Consolas, monospace">{escape(title)}</text>'
    )
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_page_png(svg_path: Path, png_path: Path) -> None:
    try:
        import fitz
    except Exception:
        return
    try:
        doc = fitz.open(stream=svg_path.read_bytes(), filetype="svg")
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        pix.save(str(png_path))
    except Exception:
        return


def _point_in_bbox(x: float, y: float, bbox: tuple[float, float, float, float]) -> bool:
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _line_intersects_bbox(line: _LineItem, bbox: tuple[float, float, float, float]) -> bool:
    min_x = min(line.x1, line.x2)
    max_x = max(line.x1, line.x2)
    min_y = min(line.y1, line.y2)
    max_y = max(line.y1, line.y2)
    return not (max_x < bbox[0] or min_x > bbox[2] or max_y < bbox[1] or min_y > bbox[3])


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
