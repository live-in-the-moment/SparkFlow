from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .cad.parse import CadParseOptions, parse_cad
from .core import audit_file
from .model.build_options import ModelBuildOptions
from .project_docs import _read_xls_rows_via_excel
from .util import sha256_file

_XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XLSX_DOCUMENT_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XLSX_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_XLSX_NS = {
    "main": _XLSX_MAIN_NS,
    "rel": _XLSX_DOCUMENT_REL_NS,
    "pkg": _XLSX_PACKAGE_REL_NS,
}

_PROJECT_CODE_RE = re.compile(r"[0-9A-Z]{10,}")
_PLACEHOLDER_RE = re.compile(r"(?:FXX|FXXX|XXX|XXXX|XX工程|暂命名)", re.IGNORECASE)
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

_DRAWING_REQUIRED_PHRASES = (
    "10kV土建通道走向图",
    "智能设备安装布置图",
    "智能网关",
    "综合测控",
    "综合测控通信单元",
    "智能化",
    "电缆线路",
    "二次柜",
    "DTU",
    "安装位置",
    "工程量说明",
)

_MANUAL_ONLY_HINTS = (
    "设计说明书",
    "预算",
    "可研",
    "控制线",
    "物探报告",
    "材料清册",
    "预算书",
    "反事故措施",
    "危大清单",
    "带电作业位置照片",
    "勘察费",
    "甲供设备",
    "附件",
)

_TECHNICAL_POINT_FILTER_PATTERNS = (
    re.compile(r"附件\d+"),
    re.compile(r"设计说明书"),
    re.compile(r"材料清册"),
    re.compile(r"评审意见表"),
    re.compile(r"预算"),
    re.compile(r"概算"),
    re.compile(r"清册"),
)


@dataclass(frozen=True)
class ReviewAuditOutput:
    run_dir: Path
    drawing_info_json_path: Path
    review_rules_json_path: Path
    review_report_json_path: Path
    review_report_md_path: Path
    sparkflow_report_json_path: Path | None
    sparkflow_report_md_path: Path | None

    @property
    def review_bundle_json_path(self) -> Path:
        return self.review_rules_json_path


def extract_drawing_info(path: Path, *, parse_options: CadParseOptions | None = None) -> dict[str, Any]:
    parsed = parse_cad(path, options=parse_options)
    entities = parsed.entities
    kinds = Counter(entity.kind for entity in entities)
    layers = Counter((entity.props.get("gc_8") or "").strip() for entity in entities if entity.props.get("gc_8"))

    texts: list[str] = []
    blocks: list[str] = []
    for entity in entities:
        if entity.kind in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
            value = entity.props.get("gc_1") or entity.props.get("gc_3")
            if value:
                text = str(value).strip()
                if text:
                    texts.append(text)
        if entity.kind == "INSERT":
            value = entity.props.get("gc_2")
            if value:
                block = str(value).strip()
                if block:
                    blocks.append(block)

    unique_texts = sorted(set(texts))
    unique_blocks = sorted(set(blocks))
    placeholder_texts = sorted({text for text in unique_texts if _PLACEHOLDER_RE.search(text)})

    return {
        "input_path": str(path.resolve()),
        "input_sha256": sha256_file(path),
        "parser_id": parsed.parser_id,
        "parse_meta": parsed.meta,
        "entity_count": len(entities),
        "kinds": dict(kinds),
        "layers": {name: count for name, count in layers.items() if name},
        "bbox": _compute_bbox(entities),
        "unique_blocks": unique_blocks,
        "unique_texts": unique_texts,
        "placeholder_texts": placeholder_texts,
    }


def write_drawing_info(
    path: Path,
    out_path: Path,
    *,
    parse_options: CadParseOptions | None = None,
) -> Path:
    info = extract_drawing_info(path, parse_options=parse_options)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def load_review_rules(
    review_dir: Path,
    *,
    project_code: str | None = None,
    project_name: str | None = None,
) -> dict[str, Any]:
    review_dir = review_dir.resolve()
    if not review_dir.exists():
        raise FileNotFoundError(str(review_dir))
    if not review_dir.is_dir():
        raise NotADirectoryError(str(review_dir))

    review_dir = _resolve_review_dir(review_dir)
    discovered = _discover_review_files(review_dir)
    major_issues_path = discovered.get("major_issues")
    summary_path = discovered.get("summary")
    resolved_project_code = (project_code or "").strip()
    resolved_project_name = _normalize_space(project_name or "")
    technical_points_excels = discovered.get("technical_points_excels", ())
    if major_issues_path is None and not technical_points_excels:
        raise FileNotFoundError("评审意见目录中未找到“主要问题统计表”XLSX，也未找到评审技术要点 Excel。")

    major_row = None
    if major_issues_path is not None:
        major_row = _resolve_project_row(
            major_issues_path,
            project_code=resolved_project_code,
            project_name=resolved_project_name,
            preferred_sheet_keyword="主要问题统计表",
        )
        resolved_project_code = resolved_project_code or _project_code_from_row(major_row)
        resolved_project_name = resolved_project_name or _project_name_from_major_row(major_row, project_code=resolved_project_code)

    summary_row = None
    if summary_path is not None:
        summary_row = _resolve_project_row(
            summary_path,
            project_code=resolved_project_code,
            project_name=resolved_project_name,
            preferred_sheet_keyword="评审情况明细表",
            allow_missing=True,
        )
        resolved_project_code = resolved_project_code or _project_code_from_row(summary_row)

    if not resolved_project_name and len(technical_points_excels) == 1:
        resolved_project_name = _infer_project_name(technical_points_excels[0])
    if not resolved_project_name:
        resolved_project_name = _project_name_from_major_row(summary_row, project_code=resolved_project_code)
    if not resolved_project_code and not resolved_project_name:
        raise ValueError("缺少 project_code/project_name，无法从评审意见目录中定位项目。")

    rules_doc = {
        "project_code": resolved_project_code,
        "project_name": resolved_project_name,
        "review_dir": str(review_dir),
        "source_files": {
            "major_issues_xlsx": str(major_issues_path) if major_issues_path is not None else None,
            "summary_xlsx": str(summary_path) if summary_path is not None else None,
            "supporting_docs": [str(path) for path in discovered.get("supporting_docs", ())],
            "technical_points_excels": [str(path) for path in technical_points_excels],
        },
        "project_summary": _build_project_summary(summary_row),
        "major_issues": _extract_major_issues(major_row, project_code=resolved_project_code),
    }
    technical_point_result = _load_technical_point_rules(
        technical_points_excels,
        project_name=resolved_project_name,
        project_code=resolved_project_code,
    )
    rules_doc["review_rules"] = _build_review_rules(rules_doc)
    rules_doc["review_rules"].extend(technical_point_result["review_rules"])
    rules_doc["filtered_candidates"] = technical_point_result["filtered_candidates"]
    return rules_doc


def load_review_bundle(review_dir: Path, *, project_code: str | None = None) -> dict[str, Any]:
    return load_review_rules(review_dir, project_code=project_code)


def review_audit(
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
) -> ReviewAuditOutput:
    drawing_path = drawing_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    resolved_project_code = (project_code or _infer_project_code(drawing_path)).strip()
    inferred_project_name = _infer_project_name(drawing_path)

    run_dir = out_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    review_rules = load_review_rules(
        review_dir,
        project_code=(resolved_project_code or None),
        project_name=(inferred_project_name or None),
    )
    resolved_project_code = resolved_project_code or str(review_rules.get("project_code") or "").strip()
    if not resolved_project_code:
        raise ValueError("无法从图纸路径或评审意见中定位工程编号，请显式传入 --project-code。")

    drawing_info_json_path = write_drawing_info(
        drawing_path,
        run_dir / "drawing_info.json",
        parse_options=parse_options,
    )
    drawing_info = json.loads(drawing_info_json_path.read_text(encoding="utf-8"))
    review_rules_json_path = run_dir / "review_rules.json"
    review_rules_json_path.write_text(json.dumps(review_rules, ensure_ascii=False, indent=2), encoding="utf-8")

    sparkflow_output = None
    sparkflow_report: dict[str, Any] | None = None
    if include_sparkflow_audit:
        sparkflow_output = audit_file(
            drawing_path,
            run_dir / "sparkflow_audit",
            parse_options=parse_options,
            level=level,
            model_options=model_options,
            ruleset_dir=ruleset_dir,
            selection_mode=selection_mode,
            graph=graph,
        )
        sparkflow_report = json.loads(sparkflow_output.report_json_path.read_text(encoding="utf-8"))

    review_report = _build_review_report(
        drawing_path=drawing_path,
        project_code=resolved_project_code,
        drawing_info=drawing_info,
        review_rules_doc=review_rules,
        sparkflow_report=sparkflow_report,
        drawing_info_json_path=drawing_info_json_path,
        review_rules_json_path=review_rules_json_path,
        sparkflow_report_json_path=(sparkflow_output.report_json_path if sparkflow_output is not None else None),
        sparkflow_report_md_path=(sparkflow_output.report_md_path if sparkflow_output is not None else None),
        include_sparkflow_audit=include_sparkflow_audit,
    )

    review_report_json_path = run_dir / "review_report.json"
    review_report_md_path = run_dir / "review_report.md"
    review_report_json_path.write_text(json.dumps(review_report, ensure_ascii=False, indent=2), encoding="utf-8")
    review_report_md_path.write_text(render_review_report_markdown(review_report), encoding="utf-8")

    return ReviewAuditOutput(
        run_dir=run_dir,
        drawing_info_json_path=drawing_info_json_path,
        review_rules_json_path=review_rules_json_path,
        review_report_json_path=review_report_json_path,
        review_report_md_path=review_report_md_path,
        sparkflow_report_json_path=(sparkflow_output.report_json_path if sparkflow_output is not None else None),
        sparkflow_report_md_path=(sparkflow_output.report_md_path if sparkflow_output is not None else None),
    )


def render_review_report_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# SparkFlow 评审规则审查报告")
    lines.append("")
    lines.append(f"- created_at: {report.get('created_at')}")
    lines.append(f"- input_path: {report.get('input_path')}")
    lines.append(f"- project_code: {report.get('project_code')}")
    lines.append(f"- project_name: {report.get('project_name')}")
    lines.append(f"- review_dir: {report.get('review_dir')}")
    lines.append("")

    summary = report.get("summary") or {}
    if summary:
        lines.append("## Summary")
        lines.append("")
        for key, value in summary.items():
            lines.append(f"- {key}: {_format_value(value)}")
        lines.append("")

    source_files = report.get("source_files") or {}
    if source_files:
        lines.append("## Review Sources")
        lines.append("")
        for key, value in source_files.items():
            lines.append(f"- {key}: {_format_value(value)}")
        lines.append("")

    rules_doc = report.get("review_rules") or {}
    project_summary = rules_doc.get("project_summary") or {}
    if project_summary:
        lines.append("## Project Summary")
        lines.append("")
        for key, value in project_summary.items():
            if value not in (None, "", []):
                lines.append(f"- {key}: {_format_value(value)}")
        lines.append("")

    major = rules_doc.get("major_issues") or {}
    if major:
        lines.append("## Review Rules Source")
        lines.append("")
        for key in (
            "technical_opinion",
            "technical_reply",
            "cost_opinion",
            "cost_reply",
            "execution_status",
        ):
            value = major.get(key)
            if value:
                lines.append(f"### {key}")
                lines.append("")
                lines.append(str(value))
                lines.append("")

    items = report.get("review_rule_results") or []
    lines.append("## Rule Results")
    lines.append("")
    if not items:
        lines.append("无评审规则。")
        lines.append("")
    else:
        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. [{item.get('result')}] {item.get('rule_id')}: {item.get('source_text')}")
            lines.append(f"   - source_type: {item.get('source_type')}")
            lines.append(f"   - check_type: {item.get('check_type')}")
            lines.append(f"   - scope: {item.get('scope')}")
            if item.get("keywords"):
                lines.append(f"   - keywords: {', '.join(item.get('keywords') or [])}")
            if item.get("matches"):
                for match in item.get("matches") or []:
                    lines.append(f"   - evidence: {match}")
            if item.get("reply"):
                lines.append(f"   - reply: {item.get('reply')}")
            if item.get("explanation"):
                lines.append(f"   - explanation: {item.get('explanation')}")
        lines.append("")

    return "\n".join(lines)


def _build_review_report(
    *,
    drawing_path: Path,
    project_code: str,
    drawing_info: dict[str, Any],
    review_rules_doc: dict[str, Any],
    sparkflow_report: dict[str, Any] | None,
    drawing_info_json_path: Path,
    review_rules_json_path: Path,
    sparkflow_report_json_path: Path | None,
    sparkflow_report_md_path: Path | None,
    include_sparkflow_audit: bool,
) -> dict[str, Any]:
    unique_texts = [str(item) for item in drawing_info.get("unique_texts") or []]
    review_rule_results = [_evaluate_review_rule(item, unique_texts) for item in review_rules_doc.get("review_rules") or []]
    counts = Counter(item["result"] for item in review_rule_results)
    placeholder_texts = list(drawing_info.get("placeholder_texts") or [])
    return {
        "created_at": datetime.now().astimezone().isoformat(),
        "input_path": str(drawing_path),
        "project_code": project_code,
        "project_name": review_rules_doc.get("project_name"),
        "review_dir": review_rules_doc.get("review_dir"),
        "source_files": review_rules_doc.get("source_files"),
        "drawing_info_json_path": str(drawing_info_json_path),
        "review_rules_json_path": str(review_rules_json_path),
        "review_bundle_json_path": str(review_rules_json_path),
        "sparkflow_report_json_path": str(sparkflow_report_json_path) if sparkflow_report_json_path is not None else None,
        "sparkflow_report_md_path": str(sparkflow_report_md_path) if sparkflow_report_md_path is not None else None,
        "summary": {
            "sparkflow_audit_skipped": not include_sparkflow_audit,
            "sparkflow_passed": (bool(sparkflow_report.get("passed")) if sparkflow_report is not None else None),
            "sparkflow_issue_count": (len(sparkflow_report.get("issues") or []) if sparkflow_report is not None else None),
            "placeholder_text_count": len(placeholder_texts),
            "placeholder_texts": placeholder_texts,
            "review_rule_counts": dict(counts),
            "requirement_counts": dict(counts),
        },
        "review_rules": {
            "project_summary": review_rules_doc.get("project_summary"),
            "major_issues": review_rules_doc.get("major_issues"),
        },
        "review_bundle": {
            "project_summary": review_rules_doc.get("project_summary"),
            "major_issues": review_rules_doc.get("major_issues"),
        },
        "review_rule_results": review_rule_results,
        "requirements": review_rule_results,
    }


def _evaluate_review_rule(item: dict[str, Any], unique_texts: list[str]) -> dict[str, Any]:
    scope = item.get("scope") or "drawing"
    check_type = item.get("check_type") or "drawing_text_presence"
    keywords = [str(keyword) for keyword in item.get("keywords") or [] if str(keyword).strip()]
    matches = _find_text_matches(unique_texts, keywords)
    result = "manual_review"
    explanation = ""
    if check_type == "manual_review" or scope != "drawing":
        explanation = "该条规则依赖说明书、预算或其他附件，不能仅凭解析后的图纸判定。"
    elif not keywords:
        explanation = "该条规则未能提炼出稳定的图纸关键词，当前仅能保留为人工复核项。"
    elif matches:
        result = "passed"
        explanation = "规则命中的图纸文本证据已找到。"
    else:
        result = "failed"
        explanation = "解析后的图纸文本中未找到该规则要求的证据。"
    return {
        **item,
        "result": result,
        "matches": matches,
        "explanation": explanation,
    }


def _find_text_matches(unique_texts: list[str], keywords: list[str]) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        for text in unique_texts:
            if keyword in text and text not in seen:
                matches.append(text)
                seen.add(text)
                if len(matches) >= 8:
                    return matches
    return matches


def _build_review_rules(rules_doc: dict[str, Any]) -> list[dict[str, Any]]:
    major = rules_doc.get("major_issues") or {}
    technical_items = _split_technical_items(major.get("technical_opinion") or "")
    technical_replies = _split_sub_items(major.get("technical_reply") or "")
    cost_items = _split_numbered_items(major.get("cost_opinion") or "")
    cost_replies = _split_numbered_items(major.get("cost_reply") or "")

    review_rules: list[dict[str, Any]] = []
    for index, text in enumerate(technical_items):
        review_rules.append(
            {
                "rule_id": f"technical.{index + 1}",
                "source_type": "technical",
                "item_no": index + 1,
                "source_text": text,
                "reply": technical_replies[index] if index < len(technical_replies) else "",
                "scope": _classify_scope(text),
                "check_type": _classify_check_type(text),
                "keywords": _extract_keywords(text),
            }
        )
    for index, text in enumerate(cost_items):
        review_rules.append(
            {
                "rule_id": f"cost.{index + 1}",
                "source_type": "cost",
                "item_no": index + 1,
                "source_text": text,
                "reply": cost_replies[index] if index < len(cost_replies) else "",
                "scope": _classify_scope(text),
                "check_type": _classify_check_type(text),
                "keywords": _extract_keywords(text),
            }
        )
    return review_rules


def _build_requirements(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return _build_review_rules(bundle)


def _classify_scope(text: str) -> str:
    normalized = _normalize_space(text)
    if any(hint in normalized for hint in _MANUAL_ONLY_HINTS):
        return "manual"
    return "drawing"


def _classify_check_type(text: str) -> str:
    if _classify_scope(text) != "drawing":
        return "manual_review"
    return "drawing_text_presence"


def _extract_keywords(text: str) -> list[str]:
    normalized = _normalize_space(text)
    keywords: list[str] = []
    for phrase in _DRAWING_REQUIRED_PHRASES:
        if phrase in normalized:
            keywords.append(phrase)
    quoted = re.findall(r"[“\"]([^”\"]{2,40})[”\"]", normalized)
    for token in quoted:
        if token not in keywords:
            keywords.append(token)
    for token in _CHINESE_RE.findall(normalized):
        if len(token) < 4:
            continue
        if token in keywords:
            continue
        if any(hint in token for hint in _MANUAL_ONLY_HINTS):
            continue
        if token.endswith("图") or token.endswith("位置") or token.endswith("说明") or token.endswith("工程量"):
            keywords.append(token)
    return keywords[:8]


def _split_technical_items(text: str) -> list[str]:
    normalized = _normalize_space(text)
    if not normalized:
        return []
    marker = "技术意见："
    body = normalized.split(marker, 1)[1] if marker in normalized else normalized
    items = _split_sub_items(body)
    if items:
        return items
    return [body]


def _split_sub_items(text: str) -> list[str]:
    normalized = _normalize_space(text)
    if not normalized:
        return []
    parts = re.split(r"(?:^|\n)\s*[（(](\d+)[）)]\s*", normalized)
    if len(parts) <= 1:
        return _split_numbered_items(normalized)
    items: list[str] = []
    for index in range(1, len(parts), 2):
        body = parts[index + 1].strip()
        if body:
            items.append(body)
    return items


def _split_numbered_items(text: str) -> list[str]:
    normalized = _normalize_space(text)
    if not normalized:
        return []
    matches = list(re.finditer(r"(?:(?<=\n)|^)\s*\d+、", normalized))
    if not matches:
        return [normalized]
    items: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        body = normalized[start:end].strip()
        if body:
            items.append(body)
    return items


def _discover_review_files(review_dir: Path) -> dict[str, Any]:
    files = list(review_dir.iterdir())
    xlsx_files = [path for path in files if path.is_file() and path.suffix.lower() == ".xlsx"]
    if review_dir.name == "评审技术要点":
        technical_points_excels = tuple(
            sorted(
                path
                for path in review_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in {".xls", ".xlsx"}
            )
        )
    else:
        technical_points_dir = review_dir / "评审技术要点"
        technical_points_excels = tuple(
            sorted(
                path
                for path in technical_points_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in {".xls", ".xlsx"}
            )
        ) if technical_points_dir.exists() else ()
    supporting_docs = sorted(
        path for path in files if path.is_file() and path.suffix.lower() in {".doc", ".docx", ".pdf", ".xls", ".xlsx"}
    )
    return {
        "major_issues": _pick_preferred_file(xlsx_files, "主要问题统计表"),
        "summary": _pick_preferred_file(xlsx_files, "评审情况汇总表"),
        "supporting_docs": tuple(dict.fromkeys([*supporting_docs, *technical_points_excels])),
        "technical_points_excels": technical_points_excels,
    }


def _pick_preferred_file(paths: list[Path], keyword: str) -> Path | None:
    candidates = [path for path in paths if keyword in path.name]
    if not candidates:
        return None
    candidates.sort(key=lambda path: ("_1" in path.stem, len(path.name), path.name))
    return candidates[0]


def _resolve_review_dir(review_dir: Path) -> Path:
    if review_dir.name != "评审技术要点":
        return review_dir
    parent = review_dir.parent
    if not parent.exists() or not parent.is_dir():
        return review_dir
    discovered = _discover_review_files(parent)
    if discovered.get("major_issues") is not None or discovered.get("summary") is not None:
        return parent
    return review_dir


def _resolve_project_row(
    xlsx_path: Path,
    *,
    project_code: str,
    project_name: str,
    preferred_sheet_keyword: str,
    allow_missing: bool = False,
) -> list[str] | None:
    sheets = _read_excel_sheets(xlsx_path)
    ordered = sorted(sheets, key=lambda item: (preferred_sheet_keyword not in item[0], item[0]))
    normalized_name = _normalize_space(project_name).replace(" ", "")
    fuzzy_match: list[str] | None = None
    for _, rows in ordered:
        for row in rows:
            if project_code and project_code in row:
                return row
            if not normalized_name:
                continue
            normalized_cells = [_normalize_space(cell).replace(" ", "") for cell in row if _normalize_space(cell)]
            if any(normalized_name == cell for cell in normalized_cells):
                return row
            if fuzzy_match is None and any(normalized_name in cell for cell in normalized_cells):
                fuzzy_match = row
    if fuzzy_match is not None:
        return fuzzy_match
    if allow_missing:
        return None
    if project_code:
        raise ValueError(f"{xlsx_path.name} 中未找到工程编号 {project_code} 对应的项目行。")
    if normalized_name:
        raise ValueError(f"{xlsx_path.name} 中未找到工程名称 {project_name} 对应的项目行。")
    raise ValueError("缺少 project_code/project_name，无法从评审意见目录中定位项目。")


def _load_project_row(
    xlsx_path: Path,
    *,
    project_code: str,
    preferred_sheet_keyword: str,
    allow_missing: bool = False,
) -> list[str] | None:
    sheets = _read_excel_sheets(xlsx_path)
    ordered = sorted(sheets, key=lambda item: (preferred_sheet_keyword not in item[0], item[0]))
    for _, rows in ordered:
        for row in rows:
            if project_code in row:
                return row
    if allow_missing:
        return None
    raise ValueError(f"{xlsx_path.name} 中未找到工程编号 {project_code} 对应的项目行。")


def _build_project_summary(row: list[str] | None) -> dict[str, Any]:
    if not row:
        return {}
    if _looks_like_project_code(_cell(row, 2)):
        project_name = _cell(row, 1)
        project_code = _cell(row, 2)
        total_investment = _cell(row, 3)
        viability_estimate = _cell(row, 4)
        submitted_budget = _cell(row, 5)
        approved_budget = _cell(row, 6) or _cell(row, 7)
        project_type = _cell(row, 8)
        standard_design_diff = _cell(row, 33) or _cell(row, 34)
        return {
            "project_name": project_name,
            "project_code": project_code,
            "total_investment": total_investment,
            "viability_estimate": viability_estimate,
            "submitted_budget": submitted_budget,
            "approved_budget": approved_budget,
            "project_type": project_type,
            "standard_design_diff": standard_design_diff,
        }
    return {
        "project_name": _cell(row, 1),
        "project_code": _cell(row, 2),
        "total_investment": _cell(row, 3),
        "viability_estimate": _cell(row, 4),
        "submitted_budget": _cell(row, 5),
        "approved_budget": _cell(row, 6) or _cell(row, 7),
        "project_type": _cell(row, 8),
        "standard_design_diff": _cell(row, 33) or _cell(row, 34),
    }


def _project_name_from_major_row(row: list[str] | None, *, project_code: str) -> str:
    if row is None:
        return ""
    if _cell(row, 2) == project_code and _cell(row, 1):
        return _cell(row, 1)
    if _cell(row, 2) and not _looks_like_project_code(_cell(row, 2)):
        return _cell(row, 2)
    if _cell(row, 1) and not _looks_like_project_code(_cell(row, 1)):
        return _cell(row, 1)
    for cell in row:
        normalized = _normalize_space(cell)
        if normalized and not _looks_like_project_code(normalized):
            return normalized
    return ""


def _project_code_from_row(row: list[str] | None) -> str:
    if row is None:
        return ""
    for cell in row:
        normalized = _normalize_space(cell)
        if _looks_like_project_code(normalized):
            return normalized
    return ""


def _extract_major_issues(row: list[str] | None, *, project_code: str) -> dict[str, str]:
    if row is None:
        return {
            "technical_opinion": "",
            "technical_expert": "",
            "technical_reply": "",
            "cost_opinion": "",
            "cost_expert": "",
            "cost_reply": "",
            "execution_status": "",
        }
    if _cell(row, 2) == project_code and len(row) >= 11 and ("执行" in _cell(row, 10) or _cell(row, 10) in {"是", "否"}):
        return {
            "technical_opinion": _cell(row, 6),
            "technical_expert": "",
            "technical_reply": _cell(row, 7),
            "cost_opinion": _cell(row, 8),
            "cost_expert": "",
            "cost_reply": _cell(row, 9),
            "execution_status": _cell(row, 10),
        }
    return {
        "technical_opinion": _cell(row, 6),
        "technical_expert": _cell(row, 7),
        "technical_reply": _cell(row, 8),
        "cost_opinion": _cell(row, 9),
        "cost_expert": _cell(row, 10),
        "cost_reply": _cell(row, 11),
        "execution_status": _cell(row, 12),
    }


def _cell(row: list[str] | None, index: int) -> str:
    if row is None or index >= len(row):
        return ""
    return _normalize_space(row[index])


def _read_excel_sheets(path: Path) -> list[tuple[str, list[list[str]]]]:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return _read_xlsx_sheets(path)
    if suffix == ".xls":
        return [(path.stem, _read_xls_rows_via_excel(path))]
    raise ValueError(f"{path.name} 不是受支持的 Excel 文件。")


def _read_xlsx_sheets(path: Path) -> list[tuple[str, list[list[str]]]]:
    try:
        with zipfile.ZipFile(path) as archive:
            sheet_paths = _resolve_xlsx_sheet_paths(archive)
            shared_strings = _load_xlsx_shared_strings(archive)
            sheets: list[tuple[str, list[list[str]]]] = []
            for sheet_name, sheet_path in sheet_paths:
                sheet_root = ET.fromstring(archive.read(sheet_path))
                rows: list[list[str]] = []
                for row in sheet_root.findall("./main:sheetData/main:row", _XLSX_NS):
                    row_values: dict[int, str] = {}
                    for cell in row.findall("main:c", _XLSX_NS):
                        column_index = _xlsx_column_index(cell.get("r"))
                        if column_index <= 0:
                            continue
                        row_values[column_index] = _xlsx_cell_text(cell, shared_strings)
                    max_column = max(row_values, default=0)
                    if max_column:
                        rows.append([_normalize_space(row_values.get(index, "")) for index in range(1, max_column + 1)])
                    else:
                        rows.append([])
                sheets.append((sheet_name, rows))
            return sheets
    except (KeyError, ET.ParseError, zipfile.BadZipFile, ValueError) as exc:
        raise ValueError(f"{path.name} 不是有效的 XLSX 文件。") from exc


def _resolve_xlsx_sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.get("Id"): rel.get("Target", "")
        for rel in rels_root.findall("./pkg:Relationship", _XLSX_NS)
        if rel.get("Id")
    }
    paths: list[tuple[str, str]] = []
    for sheet in workbook_root.findall("./main:sheets/main:sheet", _XLSX_NS):
        name = sheet.get("name") or ""
        rel_id = sheet.get(f"{{{_XLSX_DOCUMENT_REL_NS}}}id")
        if not rel_id:
            continue
        target = rel_map.get(rel_id)
        if not target:
            continue
        paths.append((name, _normalize_zip_path("xl", target)))
    if not paths:
        raise ValueError("workbook 缺少工作表。")
    return paths


def _load_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in shared_root.findall("./main:si", _XLSX_NS):
        values.append("".join(node.text or "" for node in item.findall(".//main:t", _XLSX_NS)))
    return values


def _normalize_zip_path(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        target_path = PurePosixPath(target.lstrip("/"))
    else:
        target_path = PurePosixPath(base_dir) / PurePosixPath(target)
    parts: list[str] = []
    for part in target_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _xlsx_column_index(ref: str | None) -> int:
    if not ref:
        return 0
    letters = ""
    for ch in ref:
        if ch.isalpha():
            letters += ch
        else:
            break
    out = 0
    for ch in letters:
        out = out * 26 + (ord(ch.upper()) - 64)
    return out


def _xlsx_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", _XLSX_NS))
    value_node = cell.find("main:v", _XLSX_NS)
    if value_node is None or value_node.text is None:
        return ""
    text = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(text)]
        except (IndexError, ValueError):
            return text
    return text


def _infer_project_code(path: Path) -> str:
    for part in [path.name, *[parent.name for parent in path.parents]]:
        match = _PROJECT_CODE_RE.search(part)
        if match:
            return match.group(0)
    return ""


def _infer_project_name(path: Path) -> str:
    candidates = [_clean_project_name_candidate(path.stem)]
    candidates.extend(_clean_project_name_candidate(parent.name) for parent in list(path.parents)[:4])
    ranked = sorted(
        {candidate for candidate in candidates if candidate},
        key=_project_name_candidate_score,
        reverse=True,
    )
    return ranked[0] if ranked else ""


def _clean_project_name_candidate(value: str) -> str:
    text = _normalize_space(value)
    if not text:
        return ""
    for prefix in ("图纸-", "底图-"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    if text.startswith("配网工程设计评审技术要点"):
        match = re.search(r"[（(]([^()（）]+)[)）]$", text)
        if match:
            text = match.group(1)
        else:
            text = text.removeprefix("配网工程设计评审技术要点").strip("（）() -_")
    text = re.sub(r"(?<=工程)\d+$", "", text)
    if not text:
        return ""
    if text in {"评审意见", "评审技术要点", "施工图"}:
        return ""
    if text.startswith("附件"):
        return ""
    if "主要问题统计表" in text or "评审情况汇总表" in text:
        return ""
    return text.strip(" _-")


def _project_name_candidate_score(value: str) -> tuple[int, int]:
    score = len(value)
    if "工程" in value:
        score += 100
    if "10kV" in value or "20kV" in value:
        score += 20
    if any(token in value for token in ("图纸", "评审", "附件", "施工图")):
        score -= 200
    return score, len(value)


def _looks_like_project_code(value: str) -> bool:
    return bool(_PROJECT_CODE_RE.fullmatch(value or ""))


def _load_technical_point_rules(
    paths: tuple[Path, ...],
    *,
    project_name: str,
    project_code: str,
) -> dict[str, list[dict[str, Any]]]:
    rules: list[dict[str, Any]] = []
    filtered_candidates: list[dict[str, Any]] = []
    index = 0
    for path in _candidate_technical_point_paths(paths, project_name=project_name, project_code=project_code):
        sheets = _read_excel_sheets(path)
        if not _technical_points_file_matches_project(path, sheets, project_name=project_name, project_code=project_code):
            continue
        extracted = _extract_technical_point_rules(path, sheets, start_index=index + 1)
        rules.extend(extracted["review_rules"])
        filtered_candidates.extend(extracted["filtered_candidates"])
        index = len(rules)
    return {"review_rules": rules, "filtered_candidates": filtered_candidates}


def _candidate_technical_point_paths(
    paths: tuple[Path, ...],
    *,
    project_name: str,
    project_code: str,
) -> tuple[Path, ...]:
    filename_matches = tuple(
        path for path in paths if _technical_points_filename_matches_project(path, project_name=project_name, project_code=project_code)
    )
    if filename_matches:
        return filename_matches
    return paths


def _technical_points_filename_matches_project(
    path: Path,
    *,
    project_name: str,
    project_code: str,
) -> bool:
    normalized_name = _normalize_space(project_name).replace(" ", "")
    filename = path.name.replace(" ", "")
    if normalized_name and normalized_name in filename:
        return True
    if project_code and project_code in filename:
        return True
    return False


def _technical_points_file_matches_project(
    path: Path,
    sheets: list[tuple[str, list[list[str]]]],
    *,
    project_name: str,
    project_code: str,
) -> bool:
    if _technical_points_filename_matches_project(path, project_name=project_name, project_code=project_code):
        return True
    normalized_name = _normalize_space(project_name).replace(" ", "")
    haystacks: list[str] = []
    for _, rows in sheets:
        for row in rows[:12]:
            text = " ".join(cell for cell in row if cell)
            if text:
                haystacks.append(text.replace(" ", ""))
    if project_code and any(project_code in text for text in haystacks):
        return True
    if normalized_name and any(normalized_name in text for text in haystacks):
        return True
    return False


def _extract_technical_point_rules(
    path: Path,
    sheets: list[tuple[str, list[list[str]]]],
    *,
    start_index: int,
) -> dict[str, list[dict[str, Any]]]:
    review_rules: list[dict[str, Any]] = []
    filtered_candidates: list[dict[str, Any]] = []
    candidate_rules: list[dict[str, Any]] = []
    current_category = ""
    current_item = ""
    for sheet_name, rows in sheets:
        header_idx = _find_technical_points_header(rows)
        if header_idx is None:
            continue
        for row_idx, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
            raw_review_point = row[2] if len(row) > 2 else ""
            cells = [_normalize_space(cell) for cell in row]
            if not any(cells):
                continue
            if len(cells) > 0 and cells[0]:
                current_category = cells[0]
            if len(cells) > 1 and cells[1]:
                current_item = cells[1]
            review_point = cells[2] if len(cells) > 2 else ""
            applicable = cells[3] if len(cells) > 3 else ""
            if applicable != "是" or not review_point:
                continue
            is_filtered, filter_reason = _is_attachment_or_documentary_rule(review_point)
            candidate = {
                "source_type": "technical_points",
                "source_text": review_point,
                "source_text_raw": str(raw_review_point or ""),
                "reply": "",
                "scope": _classify_scope(review_point),
                "check_type": _classify_check_type(review_point),
                "keywords": _extract_keywords(review_point),
                "category": current_category,
                "review_item": current_item,
                "source_file": str(path),
                "source_sheet": sheet_name,
                "source_row": row_idx,
                "filtered_out": is_filtered,
                "filter_reason": filter_reason,
            }
            candidate_rules.append(candidate)

    next_index = start_index
    for candidate in candidate_rules:
        if candidate["filtered_out"]:
            filtered_candidates.append(candidate)
            continue
        accepted_rule = dict(candidate)
        accepted_rule["rule_id"] = f"technical_points.{next_index}"
        accepted_rule["item_no"] = next_index
        review_rules.append(accepted_rule)
        next_index += 1
    return {"review_rules": review_rules, "filtered_candidates": filtered_candidates}


def _is_attachment_or_documentary_rule(text: str) -> tuple[bool, str]:
    normalized_text = _normalize_space(text)
    for pattern in _TECHNICAL_POINT_FILTER_PATTERNS:
        if pattern.search(normalized_text):
            return True, f"matched:{pattern.pattern}"
    return False, ""


def _find_technical_points_header(rows: list[list[str]]) -> int | None:
    for idx, row in enumerate(rows):
        normalized = [_normalize_space(cell) for cell in row]
        if "评审类别" in normalized and "评审项" in normalized and "评审要点" in normalized:
            return idx
    return None


def _compute_bbox(entities: tuple[Any, ...]) -> dict[str, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for entity in entities:
        for x_key, y_key in (("gc_10", "gc_20"), ("gc_11", "gc_21")):
            sx = entity.props.get(x_key)
            sy = entity.props.get(y_key)
            if sx is None or sy is None:
                continue
            try:
                xs.append(float(sx))
                ys.append(float(sy))
            except (TypeError, ValueError):
                continue
    if not xs or not ys:
        return None
    return {
        "min_x": min(xs),
        "min_y": min(ys),
        "max_x": max(xs),
        "max_y": max(ys),
    }


def _normalize_space(text: str) -> str:
    return re.sub(r"[ \t]+", " ", str(text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def _format_value(value: object) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
