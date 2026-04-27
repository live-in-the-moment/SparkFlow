from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .cad.parse import CadParseOptions, parse_cad
from .core import audit_file
from .model.build_options import ModelBuildOptions
from .project_docs import _read_xls_rows_via_excel
from .rule_refine_llm import refine_candidate_rules
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

_ATTACHMENT_INVENTORY_RE = re.compile(r"^\s*\d+[、.．]\s*附件\s*\d+", re.IGNORECASE)
_NON_EXECUTABLE_CATEGORY_HINTS = ("形式审查",)
_NON_EXECUTABLE_ITEM_HINTS = ("齐备性",)
_DRAWING_ANCHOR_HINTS = (
    "图纸",
    "系统图",
    "示意图",
    "平断面图",
    "接线图",
    "布置图",
    "安装图",
    "走向图",
    "材料表",
    "目录",
)
_MANUAL_DOCUMENT_GENERIC_HINTS = (
    "设计文件",
    "预算文件",
    "可研批复",
    "批复文件",
    "编制依据",
    "合法有效",
    "费用性质",
    "完整规范",
    "深度",
)
_BROAD_QUESTION_HINTS = (
    "最优",
    "合理",
    "齐全",
    "完整",
    "符合要求",
)
_BOUNDARY_FILTER_REASONS = frozenset(
    {
        "low_signal_checklist",
        "manual_generic_prompt",
        "manual_document_general",
        "broad_questionnaire",
        "manual_without_anchor",
    }
)
_TECHPOINT_LLM_ENABLED_ENV = "SPARKFLOW_TECHPOINT_LLM_RECHECK_ENABLED"
_TECHPOINT_LLM_BASE_URL_ENV = "SPARKFLOW_TECHPOINT_LLM_RECHECK_BASE_URL"
_TECHPOINT_LLM_MODEL_ENV = "SPARKFLOW_TECHPOINT_LLM_RECHECK_MODEL"
_TECHPOINT_LLM_API_KEY_ENV = "SPARKFLOW_TECHPOINT_LLM_RECHECK_API_KEY"
_TECHPOINT_LLM_TIMEOUT_ENV = "SPARKFLOW_TECHPOINT_LLM_RECHECK_TIMEOUT_SEC"
_TECHPOINT_LLM_MAX_CASES_ENV = "SPARKFLOW_TECHPOINT_LLM_RECHECK_MAX_CASES"
_TECHPOINT_LLM_DEFAULT_TIMEOUT_SEC = 20.0
_TECHPOINT_LLM_DEFAULT_MAX_CASES = 20
_DOTENV_APPLIED = False


@dataclass(frozen=True)
class _TechnicalPointLlmRecheckConfig:
    requested: bool = False
    enabled: bool = False
    disabled_reason: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout_sec: float = _TECHPOINT_LLM_DEFAULT_TIMEOUT_SEC
    max_cases: int = _TECHPOINT_LLM_DEFAULT_MAX_CASES


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
    rules_doc["review_rules"] = _build_review_rules(rules_doc)
    llm_recheck_config = _resolve_technical_point_llm_recheck_config()
    technical_point_rules, technical_points_meta = _load_technical_point_rules_with_meta(
        technical_points_excels,
        project_name=resolved_project_name,
        project_code=resolved_project_code,
        llm_recheck_config=llm_recheck_config,
    )
    rules_doc["review_rules"].extend(technical_point_rules)
    rules_doc["technical_points_extraction"] = technical_points_meta
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
    rule_refine_mode: str = "heuristic",
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
    refined_rules, rule_refine_trace = refine_candidate_rules(
        [dict(item) for item in (review_rules.get("review_rules") or [])],
        mode=rule_refine_mode,
    )
    review_rules["review_rules"] = refined_rules

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
        rule_refine_trace=rule_refine_trace,
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
    rule_refine_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unique_texts = [str(item) for item in drawing_info.get("unique_texts") or []]
    review_rule_results = [_evaluate_review_rule(item, unique_texts) for item in review_rules_doc.get("review_rules") or []]
    counts = Counter(item["result"] for item in review_rule_results)
    placeholder_texts = list(drawing_info.get("placeholder_texts") or [])
    technical_points_meta = review_rules_doc.get("technical_points_extraction") or {}
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
            "technical_point_emitted_count": technical_points_meta.get("emitted_rule_count"),
            "technical_point_filtered_count": technical_points_meta.get("filtered_candidate_count"),
        },
        "technical_points_extraction": technical_points_meta,
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
        "rule_refine_trace": rule_refine_trace or {},
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
    llm_recheck_config: _TechnicalPointLlmRecheckConfig | None = None,
) -> list[dict[str, Any]]:
    rules, _ = _load_technical_point_rules_with_meta(
        paths,
        project_name=project_name,
        project_code=project_code,
        llm_recheck_config=llm_recheck_config,
    )
    return rules


def _load_technical_point_rules_with_meta(
    paths: tuple[Path, ...],
    *,
    project_name: str,
    project_code: str,
    llm_recheck_config: _TechnicalPointLlmRecheckConfig | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resolved_llm_config = llm_recheck_config or _resolve_technical_point_llm_recheck_config()
    rules: list[dict[str, Any]] = []
    filtered_by_reason: Counter[str] = Counter()
    filtered_examples: list[dict[str, Any]] = []
    candidate_count = 0
    applicable_count = 0
    workbook_count = 0
    matched_workbook_count = 0
    llm_boundary_candidate_count = 0
    llm_requested_count = 0
    llm_accepted_count = 0
    llm_rejected_count = 0
    llm_skipped_due_limit_count = 0
    llm_errors: list[str] = []
    index = 0
    for path in _candidate_technical_point_paths(paths, project_name=project_name, project_code=project_code):
        workbook_count += 1
        sheets = _read_excel_sheets(path)
        if not _technical_points_file_matches_project(path, sheets, project_name=project_name, project_code=project_code):
            continue
        matched_workbook_count += 1
        file_rules, file_meta = _extract_technical_point_rules(
            path,
            sheets,
            start_index=index + 1,
            llm_recheck_config=resolved_llm_config,
        )
        rules.extend(file_rules)
        index = len(rules)
        candidate_count += int(file_meta.get("candidate_count") or 0)
        applicable_count += int(file_meta.get("applicable_count") or 0)
        filtered_by_reason.update(file_meta.get("filtered_by_reason") or {})
        for item in file_meta.get("filtered_examples") or []:
            if len(filtered_examples) >= 20:
                break
            filtered_examples.append(item)
        llm_meta = file_meta.get("llm_recheck") or {}
        llm_boundary_candidate_count += int(llm_meta.get("boundary_candidate_count") or 0)
        llm_requested_count += int(llm_meta.get("requested_count") or 0)
        llm_accepted_count += int(llm_meta.get("accepted_count") or 0)
        llm_rejected_count += int(llm_meta.get("rejected_count") or 0)
        llm_skipped_due_limit_count += int(llm_meta.get("skipped_due_limit_count") or 0)
        llm_error = _normalize_space(str(llm_meta.get("error") or ""))
        if llm_error and llm_error not in llm_errors and len(llm_errors) < 3:
            llm_errors.append(llm_error)
    filtered_count = int(sum(filtered_by_reason.values()))
    return rules, {
        "workbook_count": workbook_count,
        "matched_workbook_count": matched_workbook_count,
        "candidate_count": candidate_count,
        "applicable_candidate_count": applicable_count,
        "emitted_rule_count": len(rules),
        "filtered_candidate_count": filtered_count,
        "filtered_by_reason": dict(filtered_by_reason),
        "filtered_examples": filtered_examples,
        "llm_recheck": {
            "requested": bool(resolved_llm_config.requested),
            "enabled": bool(resolved_llm_config.enabled),
            "disabled_reason": resolved_llm_config.disabled_reason,
            "base_url": resolved_llm_config.base_url,
            "model": resolved_llm_config.model,
            "boundary_candidate_count": llm_boundary_candidate_count,
            "requested_count": llm_requested_count,
            "accepted_count": llm_accepted_count,
            "rejected_count": llm_rejected_count,
            "skipped_due_limit_count": llm_skipped_due_limit_count,
            "errors": llm_errors,
        },
    }


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
    llm_recheck_config: _TechnicalPointLlmRecheckConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    emitted_candidates: list[dict[str, Any]] = []
    boundary_candidates: list[dict[str, Any]] = []
    filtered_by_reason: Counter[str] = Counter()
    filtered_examples: list[dict[str, Any]] = []
    candidate_count = 0
    applicable_count = 0
    current_category = ""
    current_item = ""
    current_candidate_index = 0
    for sheet_index, (sheet_name, rows) in enumerate(sheets):
        header_idx = _find_technical_points_header(rows)
        if header_idx is None:
            continue
        for row_idx, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
            cells = [_normalize_space(cell) for cell in row]
            if not any(cells):
                continue
            if len(cells) > 0 and cells[0]:
                current_category = cells[0]
            if len(cells) > 1 and cells[1]:
                current_item = cells[1]
            review_point = cells[2] if len(cells) > 2 else ""
            applicable = cells[3] if len(cells) > 3 else ""
            if review_point:
                candidate_count += 1
            if applicable != "是" or not review_point:
                continue
            applicable_count += 1
            current_candidate_index += 1
            candidate_id = f"tp_{path.stem}_{sheet_index}_{row_idx}_{current_candidate_index}"
            candidate = {
                "candidate_id": candidate_id,
                "source_text": review_point,
                "category": current_category,
                "review_item": current_item,
                "source_file": str(path),
                "source_sheet": sheet_name,
                "row_index": row_idx,
                "order_key": (sheet_index, row_idx, current_candidate_index),
            }
            should_emit, filter_reason, allow_boundary_recheck = _should_emit_technical_point_rule(
                review_point,
                category=current_category,
                review_item=current_item,
            )
            if not should_emit:
                filtered_by_reason[filter_reason] += 1
                if len(filtered_examples) < 20:
                    filtered_examples.append(
                        {
                            "candidate_id": candidate_id,
                            "reason": filter_reason,
                            "source_text": review_point,
                            "category": current_category,
                            "review_item": current_item,
                            "source_file": str(path),
                            "source_sheet": sheet_name,
                            "row_index": row_idx,
                        }
                    )
                if allow_boundary_recheck:
                    boundary_candidates.append({**candidate, "initial_filter_reason": filter_reason})
                continue
            emitted_candidates.append(candidate)

    llm_meta = {
        "boundary_candidate_count": len(boundary_candidates),
        "requested_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "skipped_due_limit_count": 0,
        "error": "",
    }
    accepted_boundary_ids: set[str] = set()
    llm_decisions: dict[str, dict[str, Any]] = {}
    if llm_recheck_config.enabled and boundary_candidates:
        llm_result = _llm_recheck_boundary_candidates(boundary_candidates, llm_recheck_config)
        llm_meta["requested_count"] = int(llm_result.get("requested_count") or 0)
        llm_meta["accepted_count"] = int(llm_result.get("accepted_count") or 0)
        llm_meta["rejected_count"] = int(llm_result.get("rejected_count") or 0)
        llm_meta["skipped_due_limit_count"] = int(llm_result.get("skipped_due_limit_count") or 0)
        llm_meta["error"] = _normalize_space(str(llm_result.get("error") or ""))
        llm_decisions = llm_result.get("decisions") or {}
        accepted_boundary_ids = {
            str(item)
            for item in llm_result.get("accepted_ids") or []
            if str(item).strip()
        }
        if accepted_boundary_ids:
            for candidate in boundary_candidates:
                if candidate["candidate_id"] not in accepted_boundary_ids:
                    continue
                initial_reason = str(candidate.get("initial_filter_reason") or "")
                if initial_reason in filtered_by_reason:
                    filtered_by_reason[initial_reason] -= 1
                    if filtered_by_reason[initial_reason] <= 0:
                        del filtered_by_reason[initial_reason]
                decision = llm_decisions.get(candidate["candidate_id"]) or {}
                candidate_with_decision = dict(candidate)
                candidate_with_decision["llm_recheck"] = {
                    "accepted": True,
                    "reason": _normalize_space(str(decision.get("reason") or "")),
                    "confidence": _normalize_confidence(decision.get("confidence")),
                }
                emitted_candidates.append(candidate_with_decision)

    if accepted_boundary_ids:
        filtered_examples = [
            item for item in filtered_examples if str(item.get("candidate_id") or "") not in accepted_boundary_ids
        ]
    filtered_examples = [
        {key: value for key, value in item.items() if key != "candidate_id"}
        for item in filtered_examples[:20]
    ]

    emitted_candidates.sort(key=lambda item: item.get("order_key") or (0, 0, 0))
    rules: list[dict[str, Any]] = []
    next_index = start_index
    for candidate in emitted_candidates:
        source_text = str(candidate.get("source_text") or "")
        rule = {
            "rule_id": f"technical_points.{next_index}",
            "source_type": "technical_points",
            "item_no": next_index,
            "source_text": source_text,
            "reply": "",
            "scope": _classify_scope(source_text),
            "check_type": _classify_check_type(source_text),
            "keywords": _extract_keywords(source_text),
            "category": candidate.get("category") or "",
            "review_item": candidate.get("review_item") or "",
            "source_file": candidate.get("source_file") or str(path),
            "source_sheet": candidate.get("source_sheet") or "",
        }
        llm_recheck_detail = candidate.get("llm_recheck")
        if isinstance(llm_recheck_detail, dict):
            rule["llm_recheck"] = llm_recheck_detail
        rules.append(rule)
        next_index += 1

    return rules, {
        "candidate_count": candidate_count,
        "applicable_count": applicable_count,
        "filtered_by_reason": dict(filtered_by_reason),
        "filtered_examples": filtered_examples,
        "llm_recheck": llm_meta,
    }


def _should_emit_technical_point_rule(
    review_point: str,
    *,
    category: str,
    review_item: str,
) -> tuple[bool, str, bool]:
    normalized_point = _normalize_space(review_point)
    normalized_category = _normalize_space(category)
    normalized_item = _normalize_space(review_item)
    if _is_attachment_inventory_rule(normalized_point):
        return False, "attachment_inventory", False
    if _is_document_completeness_rule(normalized_point, category=normalized_category, review_item=normalized_item):
        return False, "document_completeness", False
    keywords = _extract_keywords(normalized_point)
    has_explicit_anchor = _has_explicit_target_anchor(normalized_point)
    if _classify_scope(normalized_point) == "manual":
        if _is_generic_yes_no_prompt(normalized_point) and not has_explicit_anchor:
            return False, "manual_generic_prompt", True
        if _is_manual_document_general_prompt(normalized_point):
            return False, "manual_document_general", True
        if _is_broad_questionnaire_prompt(normalized_point):
            return False, "broad_questionnaire", True
        if not _has_drawing_anchor(normalized_point) and not has_explicit_anchor:
            return False, "manual_without_anchor", True
        return True, "", False
    if _is_broad_questionnaire_prompt(normalized_point):
        return False, "broad_questionnaire", True
    if keywords:
        return True, "", False
    if _has_drawing_anchor(normalized_point):
        return True, "", False
    return False, "low_signal_checklist", True


def _is_attachment_inventory_rule(text: str) -> bool:
    normalized = _normalize_space(text)
    if not normalized:
        return False
    if _ATTACHMENT_INVENTORY_RE.search(normalized):
        return True
    return False


def _is_document_completeness_rule(text: str, *, category: str, review_item: str) -> bool:
    normalized = _normalize_space(text)
    if any(hint in category for hint in _NON_EXECUTABLE_CATEGORY_HINTS):
        if any(hint in review_item for hint in _NON_EXECUTABLE_ITEM_HINTS):
            return True
        if "附件" in normalized:
            return True
    return False


def _is_generic_yes_no_prompt(text: str) -> bool:
    normalized = _normalize_space(text)
    normalized = re.sub(r"^\d+[、.．]\s*", "", normalized)
    return normalized.startswith("是否")


def _is_manual_document_general_prompt(text: str) -> bool:
    normalized = _strip_leading_item_no(text)
    if _has_explicit_target_anchor(normalized):
        return False
    if not any(hint in normalized for hint in _MANUAL_DOCUMENT_GENERIC_HINTS):
        return False
    return "是否" in normalized or any(hint in normalized for hint in _BROAD_QUESTION_HINTS)


def _is_broad_questionnaire_prompt(text: str) -> bool:
    normalized = _strip_leading_item_no(text)
    if _has_explicit_target_anchor(normalized):
        return False
    broad_hit_count = sum(1 for hint in _BROAD_QUESTION_HINTS if hint in normalized)
    if normalized.count("是否") >= 2:
        return True
    if "是否" in normalized and broad_hit_count >= 1:
        return True
    return broad_hit_count >= 2


def _strip_leading_item_no(text: str) -> str:
    return re.sub(r"^\s*\d+[、.．]\s*", "", _normalize_space(text))


def _has_explicit_target_anchor(text: str) -> bool:
    normalized = _normalize_space(text)
    if not normalized:
        return False
    if re.search(r"图\s*[A-Z]?\d+", normalized, re.IGNORECASE):
        return True
    if re.search(r"(?:说明书|设计说明书)\s*\d+(?:\.\d+){1,3}", normalized):
        return True
    if re.search(r"第\s*\d+\s*(?:章|节|条)", normalized):
        return True
    if re.search(r"\d+(?:\.\d+){1,3}", normalized):
        return True
    return False


def _has_drawing_anchor(text: str) -> bool:
    normalized = _normalize_space(text)
    if re.search(r"图\s*\d+", normalized):
        return True
    return any(hint in normalized for hint in _DRAWING_ANCHOR_HINTS)


def _normalize_confidence(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0:
        return 0.0
    if numeric > 1:
        return 1.0
    return numeric


def _resolve_technical_point_llm_recheck_config(
    env: Mapping[str, str] | None = None,
) -> _TechnicalPointLlmRecheckConfig:
    if env is None:
        _apply_dotenv()
        env = os.environ
    requested = _env_truthy(env.get(_TECHPOINT_LLM_ENABLED_ENV))
    base_url = str(env.get(_TECHPOINT_LLM_BASE_URL_ENV) or "").strip().rstrip("/")
    model = str(env.get(_TECHPOINT_LLM_MODEL_ENV) or "").strip()
    api_key = str(env.get(_TECHPOINT_LLM_API_KEY_ENV) or "").strip()
    timeout_sec = _env_float(env.get(_TECHPOINT_LLM_TIMEOUT_ENV), _TECHPOINT_LLM_DEFAULT_TIMEOUT_SEC)
    max_cases = _env_int(env.get(_TECHPOINT_LLM_MAX_CASES_ENV), _TECHPOINT_LLM_DEFAULT_MAX_CASES)
    if not requested:
        return _TechnicalPointLlmRecheckConfig(
            requested=False,
            enabled=False,
            disabled_reason="disabled_by_default",
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_sec=timeout_sec,
            max_cases=max_cases,
        )
    missing: list[str] = []
    if not base_url:
        missing.append("base_url")
    if not model:
        missing.append("model")
    if not api_key:
        missing.append("api_key")
    if missing:
        return _TechnicalPointLlmRecheckConfig(
            requested=True,
            enabled=False,
            disabled_reason=f"missing_config:{','.join(missing)}",
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_sec=timeout_sec,
            max_cases=max_cases,
        )
    return _TechnicalPointLlmRecheckConfig(
        requested=True,
        enabled=True,
        disabled_reason="",
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_sec=timeout_sec,
        max_cases=max_cases,
    )


def _apply_dotenv() -> None:
    global _DOTENV_APPLIED
    if _DOTENV_APPLIED:
        return
    for path in _candidate_dotenv_paths():
        if path.exists() and path.is_file():
            _merge_dotenv_file(path)
    _DOTENV_APPLIED = True


def _candidate_dotenv_paths() -> tuple[Path, ...]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent):
        candidate = (base / ".env").resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        paths.append(candidate)
    return tuple(paths)


def _merge_dotenv_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _parse_dotenv_value(value)


def _parse_dotenv_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _env_truthy(value: object) -> bool:
    normalized = _normalize_space(str(value or "")).lower()
    return normalized in {"1", "true", "yes", "on"}


def _env_float(value: object, default: float) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return default
    return parsed if parsed > 0 else default


def _env_int(value: object, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return default
    return parsed if parsed > 0 else default


def _llm_recheck_boundary_candidates(
    candidates: list[dict[str, Any]],
    config: _TechnicalPointLlmRecheckConfig,
) -> dict[str, Any]:
    limited_candidates = candidates[: config.max_cases]
    requested_count = len(limited_candidates)
    skipped_due_limit_count = max(0, len(candidates) - requested_count)
    if not limited_candidates:
        return {
            "requested_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "skipped_due_limit_count": skipped_due_limit_count,
            "accepted_ids": [],
            "decisions": {},
            "error": "",
        }
    try:
        response = _call_openai_compatible_chat_completion(
            base_url=config.base_url,
            model=config.model,
            api_key=config.api_key,
            timeout_sec=config.timeout_sec,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是配网施工图评审规则整理助手。"
                        "任务是判断技术要点文本是否属于应保留的核心评审规则。"
                        "只保留可执行、边界明确、对本专业图纸评审有直接约束的信息。"
                        "附件清单、资料齐备性、泛化问句、预算/可研完整性检查通常应拒绝。"
                        "只输出 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "判断每条候选技术要点是否应保留为核心评审规则",
                            "output_schema": {
                                "decisions": [
                                    {
                                        "candidate_id": "string",
                                        "keep": True,
                                        "reason": "string",
                                        "confidence": 0.0,
                                    }
                                ]
                            },
                            "candidates": [
                                {
                                    "candidate_id": item["candidate_id"],
                                    "category": item.get("category") or "",
                                    "review_item": item.get("review_item") or "",
                                    "source_text": item.get("source_text") or "",
                                    "initial_filter_reason": item.get("initial_filter_reason") or "",
                                }
                                for item in limited_candidates
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        decisions = _parse_llm_recheck_response(response)
    except Exception as exc:
        return {
            "requested_count": requested_count,
            "accepted_count": 0,
            "rejected_count": 0,
            "skipped_due_limit_count": skipped_due_limit_count,
            "accepted_ids": [],
            "decisions": {},
            "error": f"{type(exc).__name__}: {exc}",
        }
    accepted_ids = [candidate_id for candidate_id, item in decisions.items() if bool(item.get("keep"))]
    return {
        "requested_count": requested_count,
        "accepted_count": len(accepted_ids),
        "rejected_count": max(0, requested_count - len(accepted_ids)),
        "skipped_due_limit_count": skipped_due_limit_count,
        "accepted_ids": accepted_ids,
        "decisions": decisions,
        "error": "",
    }


def _call_openai_compatible_chat_completion(
    *,
    base_url: str,
    model: str,
    api_key: str,
    timeout_sec: float,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": messages,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url=f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"http_{exc.code}: {detail}") from exc
    return json.loads(body)


def _parse_llm_recheck_response(response: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    content = _extract_chat_completion_content(response)
    payload = _parse_json_object_from_text(content)
    decisions: dict[str, dict[str, Any]] = {}
    for item in payload.get("decisions") or []:
        if not isinstance(item, Mapping):
            continue
        candidate_id = _normalize_space(str(item.get("candidate_id") or ""))
        if not candidate_id:
            continue
        decisions[candidate_id] = {
            "keep": bool(item.get("keep")),
            "reason": _normalize_space(str(item.get("reason") or "")),
            "confidence": _normalize_confidence(item.get("confidence")),
        }
    return decisions


def _extract_chat_completion_content(response: Mapping[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("missing choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, Mapping):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        if parts:
            return "\n".join(parts)
    raise ValueError("missing message content")


def _parse_json_object_from_text(text: str) -> dict[str, Any]:
    normalized = _normalize_space(text)
    if not normalized:
        raise ValueError("empty llm response")
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("llm response is not a json object")
    return payload


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
