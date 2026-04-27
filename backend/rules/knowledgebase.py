from __future__ import annotations

import csv
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ..contracts import Severity
from .registry import build_rule, list_rule_ids
from .types import RULESET_DRAWING_TYPES, RuleBinding

_XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XLSX_DOCUMENT_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XLSX_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_XLSX_NS = {
    "main": _XLSX_MAIN_NS,
    "rel": _XLSX_DOCUMENT_REL_NS,
    "pkg": _XLSX_PACKAGE_REL_NS,
}
_RULE_TABLE_HEADERS = {"rule_id", "enabled", "severity", "params", "applies_to", "title", "clause"}
_NORMATIVE_SUMMARY_FIELDS = {"enabled", "severity", "params", "applies_to", "title", "clause"}


@dataclass(frozen=True)
class LoadedRuleConfig:
    rule_id: str
    enabled: bool
    severity: Severity | None
    params: dict[str, Any]
    applies_to: tuple[str, ...]
    title: str | None = None
    clause: str | None = None


@dataclass(frozen=True)
class LoadedRuleset:
    version: str
    rules: list[RuleBinding]
    params: dict[str, Any]
    rule_configs: tuple[LoadedRuleConfig, ...]


def load_ruleset_dir(rules_dir: Path) -> LoadedRuleset:
    rules_dir = rules_dir.resolve()
    cfg_path = rules_dir / "ruleset.json"
    if not cfg_path.exists():
        raise FileNotFoundError(str(cfg_path))

    raw = _load_ruleset_json(cfg_path)
    version = _require_non_empty_string(raw.get("version"), "ruleset.json.version")

    if "rules" in raw or "rules_table" in raw or "normative_summary" in raw:
        return _load_structured_ruleset(version=version, raw=raw, rules_dir=rules_dir)
    return _load_legacy_ruleset(version=version, raw=raw)


def write_minimal_ruleset_dir(rules_dir: Path) -> None:
    rules_dir = rules_dir.resolve()
    rules_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = rules_dir / "ruleset.json"
    cfg_path.write_text(
        json.dumps(
            {
                "version": "example_ruleset_v1",
                "model": {},
                "rules": [
                    {
                        "rule_id": rule_id,
                        "enabled": True,
                        "params": {},
                    }
                    for rule_id in list_rule_ids()
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_ruleset_json(cfg_path: Path) -> dict[str, Any]:
    # Accept both plain UTF-8 and UTF-8 with BOM because rulesets may be
    # authored by editors that prepend a BOM on Windows.
    raw = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("ruleset.json 必须是对象。")
    return raw


def _load_structured_ruleset(*, version: str, raw: dict[str, Any], rules_dir: Path) -> LoadedRuleset:
    if "enabled_rules" in raw or "params" in raw:
        raise ValueError("ruleset.json 不能同时包含 rules 与 legacy enabled_rules/params。")

    model = raw.get("model", {})
    if model is None:
        model = {}
    if not isinstance(model, dict):
        raise ValueError("ruleset.json.model 必须是对象。")

    rules_raw = _load_structured_rule_rows(raw=raw, rules_dir=rules_dir)

    known_rule_ids = set(list_rule_ids())
    seen_rule_ids: set[str] = set()
    rule_configs: list[LoadedRuleConfig] = []
    rule_bindings: list[RuleBinding] = []
    params: dict[str, Any] = {}

    for prefix, item in rules_raw:
        if not isinstance(item, dict):
            raise ValueError(f"{prefix} 必须是对象。")

        rule_id = _require_non_empty_string(item.get("rule_id"), f"{prefix}.rule_id")
        if rule_id not in known_rule_ids:
            raise ValueError(f"{prefix}.rule_id 包含未知规则：{rule_id}")
        if rule_id in seen_rule_ids:
            raise ValueError(f"{prefix}.rule_id 重复：{rule_id}")
        seen_rule_ids.add(rule_id)

        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"{prefix}.enabled 必须是布尔值。")

        severity_raw = item.get("severity")
        severity = _parse_optional_severity(severity_raw, f"{prefix}.severity")

        rule_params = item.get("params", {})
        if rule_params is None:
            rule_params = {}
        if not isinstance(rule_params, dict):
            raise ValueError(f"{prefix}.params 必须是对象。")
        if severity is not None and "severity" in rule_params:
            raise ValueError(f"{prefix} 不能同时设置 severity 和 params.severity。")

        applies_to = _parse_applies_to(item, f"{prefix}.applies_to")
        title = _parse_optional_text_field(item.get("title"), f"{prefix}.title")
        clause = _parse_optional_text_field(item.get("clause"), f"{prefix}.clause")
        config = LoadedRuleConfig(
            rule_id=rule_id,
            enabled=enabled,
            severity=severity,
            params=dict(rule_params),
            applies_to=applies_to,
            title=title,
            clause=clause,
        )
        rule_configs.append(config)

        merged_params = dict(rule_params)
        if severity is not None:
            merged_params["severity"] = severity.value
        params[rule_id] = merged_params

        if not enabled:
            continue
        try:
            rule_bindings.append(
                RuleBinding(
                    rule=build_rule(rule_id, rule_params),
                    rule_id=rule_id,
                    severity_override=severity,
                    applies_to=applies_to,
                )
            )
        except KeyError as exc:
            raise ValueError(f"{prefix}.rule_id 包含未知规则：{rule_id}") from exc

    if model:
        params["_model"] = dict(model)

    return LoadedRuleset(
        version=version.strip(),
        rules=rule_bindings,
        params=params,
        rule_configs=tuple(rule_configs),
    )


def _load_legacy_ruleset(*, version: str, raw: dict[str, Any]) -> LoadedRuleset:
    enabled = raw.get("enabled_rules")
    if enabled is None:
        enabled_ids = list_rule_ids()
    else:
        if not isinstance(enabled, list) or not all(isinstance(x, str) for x in enabled):
            raise ValueError("ruleset.json.enabled_rules 必须是字符串数组。")
        enabled_ids = list(enabled)

    params = raw.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError("ruleset.json.params 必须是对象。")

    rules: list[RuleBinding] = []
    configs: list[LoadedRuleConfig] = []
    normalized_params: dict[str, Any] = {}
    if "_model" in params:
        model = params.get("_model")
        if model is not None and not isinstance(model, dict):
            raise ValueError("ruleset.json.params._model 必须是对象。")
        if model is not None:
            normalized_params["_model"] = dict(model)

    for rid in enabled_ids:
        rule_params = params.get(rid, None)
        if rule_params is None:
            rule_params = {}
        if not isinstance(rule_params, dict):
            raise ValueError(f"ruleset.json.params.{rid} 必须是对象。")
        try:
            rules.append(RuleBinding(rule=build_rule(rid, rule_params), rule_id=rid))
        except KeyError as exc:
            raise ValueError(f"ruleset.json.enabled_rules 包含未知规则：{rid}") from exc
        normalized_params[rid] = dict(rule_params)
        configs.append(
            LoadedRuleConfig(
                rule_id=rid,
                enabled=True,
                severity=None,
                params=dict(rule_params),
                applies_to=(),
            )
        )

    return LoadedRuleset(
        version=version.strip(),
        rules=rules,
        params=normalized_params,
        rule_configs=tuple(configs),
    )


def _load_structured_rule_rows(*, raw: dict[str, Any], rules_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    has_inline_rules = "rules" in raw
    has_table_rules = "rules_table" in raw
    has_normative_summary = "normative_summary" in raw
    source_count = sum(1 for enabled in (has_inline_rules, has_table_rules, has_normative_summary) if enabled)
    if source_count > 1:
        raise ValueError("ruleset.json 不能同时包含 rules、rules_table 与 normative_summary。")
    if has_inline_rules:
        rules_raw = raw.get("rules")
        if not isinstance(rules_raw, list):
            raise ValueError("ruleset.json.rules 必须是数组。")
        return [(f"ruleset.json.rules[{index}]", item) for index, item in enumerate(rules_raw)]
    if has_table_rules:
        table_path = _resolve_rules_table_path(raw.get("rules_table"), rules_dir)
        return _load_rules_table(table_path)
    if has_normative_summary:
        summary_path = _resolve_normative_summary_path(raw.get("normative_summary"), rules_dir)
        return _load_normative_summary(summary_path)
    raise ValueError("ruleset.json 必须包含 rules、rules_table 或 normative_summary。")


def _resolve_rules_table_path(value: Any, rules_dir: Path) -> Path:
    path_text = _require_non_empty_string(value, "ruleset.json.rules_table")
    table_path = Path(path_text)
    if not table_path.is_absolute():
        table_path = rules_dir / table_path
    table_path = table_path.resolve()
    if not table_path.exists():
        raise FileNotFoundError(str(table_path))
    if table_path.is_dir():
        raise ValueError("ruleset.json.rules_table 必须指向 CSV、TSV 或 XLSX 文件。")
    if table_path.suffix.lower() not in {".csv", ".tsv", ".tab", ".xlsx"}:
        raise ValueError("ruleset.json.rules_table 必须指向 .csv、.tsv 或 .xlsx 文件。")
    return table_path


def _resolve_normative_summary_path(value: Any, rules_dir: Path) -> Path:
    path_text = _require_non_empty_string(value, "ruleset.json.normative_summary")
    summary_path = Path(path_text)
    if not summary_path.is_absolute():
        summary_path = rules_dir / summary_path
    summary_path = summary_path.resolve()
    if not summary_path.exists():
        raise FileNotFoundError(str(summary_path))
    if summary_path.is_dir():
        raise ValueError("ruleset.json.normative_summary 必须指向 Markdown 文件。")
    if summary_path.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("ruleset.json.normative_summary 必须指向 .md 文件。")
    return summary_path


def _load_rules_table(table_path: Path) -> list[tuple[str, dict[str, Any]]]:
    rows = _read_xlsx_table_rows(table_path) if table_path.suffix.lower() == ".xlsx" else _read_delimited_table_rows(table_path)
    return _load_rules_table_rows(table_path, rows)


def _read_delimited_table_rows(table_path: Path) -> list[list[str]]:
    delimiter = "\t" if table_path.suffix.lower() in {".tsv", ".tab"} else ","
    with table_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [[cell or "" for cell in row] for row in csv.reader(handle, delimiter=delimiter)]


def _read_xlsx_table_rows(table_path: Path) -> list[list[str]]:
    try:
        with zipfile.ZipFile(table_path) as archive:
            sheet_path = _resolve_xlsx_sheet_path(archive)
            shared_strings = _load_xlsx_shared_strings(archive)
            sheet_root = ET.fromstring(archive.read(sheet_path))
    except (KeyError, ET.ParseError, zipfile.BadZipFile, ValueError) as exc:
        raise ValueError(f"{table_path.name} 不是有效的 XLSX 规则表。") from exc

    rows: list[list[str]] = []
    for row in sheet_root.findall("./main:sheetData/main:row", _XLSX_NS):
        row_values: dict[int, str] = {}
        for cell in row.findall("main:c", _XLSX_NS):
            column_index = _xlsx_column_index(cell.get("r"))
            if column_index <= 0:
                continue
            row_values[column_index] = _xlsx_cell_text(cell, shared_strings)
        max_column = max(row_values, default=0)
        rows.append([row_values.get(index, "") for index in range(1, max_column + 1)] if max_column else [])
    return rows


def _resolve_xlsx_sheet_path(archive: zipfile.ZipFile) -> str:
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    first_sheet = workbook_root.find("./main:sheets/main:sheet", _XLSX_NS)
    if first_sheet is None:
        raise ValueError("workbook 缺少工作表。")
    rel_id = first_sheet.get(f"{{{_XLSX_DOCUMENT_REL_NS}}}id")
    if not rel_id:
        raise ValueError("workbook 缺少工作表关系。")

    rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.get("Id"): rel.get("Target", "")
        for rel in rels_root.findall("./pkg:Relationship", _XLSX_NS)
        if rel.get("Id")
    }
    target = rel_map.get(rel_id)
    if not target:
        raise ValueError("无法解析 XLSX 工作表路径。")
    return _normalize_zip_path("xl", target)


def _load_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in shared_root.findall("./main:si", _XLSX_NS):
        text = "".join(node.text or "" for node in item.findall(".//main:t", _XLSX_NS))
        values.append(text)
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


def _xlsx_column_index(cell_ref: str | None) -> int:
    if not cell_ref:
        return 0
    match = re.match(r"[A-Za-z]+", cell_ref)
    if match is None:
        return 0
    index = 0
    for char in match.group(0).upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def _xlsx_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", _XLSX_NS))

    value_node = cell.find("main:v", _XLSX_NS)
    raw_value = "" if value_node is None or value_node.text is None else value_node.text
    if cell_type == "s":
        if not raw_value:
            return ""
        index = int(raw_value)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    if cell_type == "b":
        return "true" if raw_value == "1" else "false"
    return raw_value


def _load_rules_table_rows(table_path: Path, rows: list[list[str]]) -> list[tuple[str, dict[str, Any]]]:
    if not rows:
        raise ValueError(f"{table_path.name} 必须包含表头。")

    fieldnames = rows[0]
    if not fieldnames or not any(cell.strip() for cell in fieldnames):
        raise ValueError(f"{table_path.name} 必须包含表头。")

    normalized_headers = [_normalize_table_header(name, table_path=table_path) for name in fieldnames]
    if len(set(normalized_headers)) != len(normalized_headers):
        raise ValueError(f"{table_path.name} 表头不能重复。")
    unknown_headers = [name for name in normalized_headers if name not in _RULE_TABLE_HEADERS]
    if unknown_headers:
        joined = ", ".join(unknown_headers)
        raise ValueError(f"{table_path.name} 包含未知列：{joined}。")
    if "rule_id" not in normalized_headers:
        raise ValueError(f"{table_path.name} 缺少必填列：rule_id。")

    items: list[tuple[str, dict[str, Any]]] = []
    column_count = len(normalized_headers)
    for row_number, row_values in enumerate(rows[1:], start=2):
        prefix = f"{table_path.name}[row {row_number}]"
        extra_values = row_values[column_count:]
        if any(value.strip() for value in extra_values):
            raise ValueError(f"{prefix} 列数超过表头定义。")
        padded_values = list(row_values[:column_count]) + [""] * max(0, column_count - len(row_values))
        normalized_row = {header: padded_values[index].strip() for index, header in enumerate(normalized_headers)}
        if all(not value for value in normalized_row.values()):
            continue

        item: dict[str, Any] = {"rule_id": normalized_row.get("rule_id", "")}
        enabled_raw = normalized_row.get("enabled", "")
        if enabled_raw:
            item["enabled"] = _parse_table_bool(enabled_raw, f"{prefix}.enabled")
        severity_raw = normalized_row.get("severity", "")
        if severity_raw:
            item["severity"] = severity_raw
        params_raw = normalized_row.get("params", "")
        if params_raw:
            item["params"] = _parse_table_params(params_raw, f"{prefix}.params")
        applies_to_raw = normalized_row.get("applies_to", "")
        if applies_to_raw:
            item["applies_to"] = _parse_table_applies_to(applies_to_raw, f"{prefix}.applies_to")
        title_raw = normalized_row.get("title", "")
        if title_raw:
            item["title"] = title_raw
        clause_raw = normalized_row.get("clause", "")
        if clause_raw:
            item["clause"] = clause_raw
        items.append((prefix, item))
    return items


def _load_normative_summary(summary_path: Path) -> list[tuple[str, dict[str, Any]]]:
    lines = summary_path.read_text(encoding="utf-8-sig").splitlines()
    items: list[tuple[str, dict[str, Any]]] = []
    current_prefix: str | None = None
    current_item: dict[str, Any] | None = None

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("# "):
            continue
        if stripped.startswith("## "):
            if current_prefix is not None and current_item is not None:
                items.append((current_prefix, current_item))
            rule_id = stripped[3:].strip()
            if not rule_id:
                raise ValueError(f"{summary_path.name}[line {line_number}] 缺少规则标题。")
            current_prefix = f"{summary_path.name}[{rule_id}]"
            current_item = {"rule_id": rule_id}
            continue
        if stripped.startswith("- "):
            if current_item is None or current_prefix is None:
                raise ValueError(f"{summary_path.name}[line {line_number}] 字段必须位于规则标题之后。")
            key, value = _parse_normative_summary_field(
                value=stripped[2:],
                summary_path=summary_path,
                line_number=line_number,
            )
            if key in current_item:
                raise ValueError(f"{summary_path.name}[line {line_number}] {key} 不能重复。")
            field_path = f"{current_prefix}.{key}"
            if key == "enabled":
                current_item[key] = _parse_table_bool(value, field_path)
            elif key == "severity":
                current_item[key] = value
            elif key == "params":
                current_item[key] = _parse_table_params(value, field_path)
            elif key == "applies_to":
                current_item[key] = _parse_table_applies_to(value, field_path)
            else:
                current_item[key] = value
            continue
        raise ValueError(f"{summary_path.name}[line {line_number}] 仅支持 ## <rule_id> 标题和 - key: value 字段。")

    if current_prefix is not None and current_item is not None:
        items.append((current_prefix, current_item))
    if not items:
        raise ValueError(f"{summary_path.name} 至少需要一个 ## <rule_id> 规则段落。")
    return items


def _parse_normative_summary_field(*, summary_path: Path, line_number: int, value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError(f"{summary_path.name}[line {line_number}] 字段必须为 key: value 形式。")
    key, raw_field_value = value.split(":", 1)
    normalized_key = key.strip()
    if not normalized_key:
        raise ValueError(f"{summary_path.name}[line {line_number}] 字段名不能为空。")
    if normalized_key not in _NORMATIVE_SUMMARY_FIELDS:
        allowed = ", ".join(sorted(_NORMATIVE_SUMMARY_FIELDS))
        raise ValueError(f"{summary_path.name}[line {line_number}] 仅支持以下字段：{allowed}。")
    normalized_value = raw_field_value.strip()
    if not normalized_value:
        raise ValueError(f"{summary_path.name}[line {line_number}] {normalized_key} 不能为空。")
    return normalized_key, normalized_value


def _normalize_table_header(value: str, *, table_path: Path) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{table_path.name} 表头包含空列名。")
    return normalized


def _parse_table_bool(value: str, path: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError(f"{path} 必须是布尔值（true/false）。")


def _parse_table_params(value: str, path: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} 必须是 JSON 对象字符串。") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} 必须是 JSON 对象字符串。")
    return parsed


def _parse_table_applies_to(value: str, path: str) -> list[str]:
    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} 必须是 drawing_type 列表或 JSON 数组。") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"{path} 必须是 drawing_type 列表或 JSON 数组。")
        return parsed
    delimiter = "|" if "|" in value else ","
    return [token.strip() for token in value.split(delimiter)]


def _require_non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} 必须是非空字符串。")
    return value.strip()


def _parse_optional_text_field(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _require_non_empty_string(value, path)


def _parse_optional_severity(value: Any, path: str) -> Severity | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{path} 必须是字符串。")
    try:
        return Severity(value.strip())
    except ValueError as exc:
        choices = ", ".join(severity.value for severity in Severity)
        raise ValueError(f"{path} 必须是以下值之一：{choices}。") from exc


def _parse_applies_to(item: dict[str, Any], path: str) -> tuple[str, ...]:
    if "applies_to" not in item:
        return ()
    applies_to = item.get("applies_to")
    if not isinstance(applies_to, list):
        raise ValueError(f"{path} 必须是字符串数组。")
    if not applies_to:
        raise ValueError(f"{path} 不能为空；如需适用于全部图纸类型，请省略该字段。")

    normalized: list[str] = []
    for index, value in enumerate(applies_to):
        entry_path = f"{path}[{index}]"
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{entry_path} 必须是非空字符串。")
        drawing_type = value.strip()
        if drawing_type not in RULESET_DRAWING_TYPES:
            allowed = ", ".join(RULESET_DRAWING_TYPES)
            raise ValueError(f"{entry_path} 必须是以下值之一：{allowed}。")
        if drawing_type not in normalized:
            normalized.append(drawing_type)
    return tuple(normalized)
