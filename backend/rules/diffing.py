from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .knowledgebase import LoadedRuleConfig, LoadedRuleset, load_ruleset_dir
from .registry import list_rule_ids
from .types import RULESET_DRAWING_TYPES


@dataclass(frozen=True)
class _RuleSnapshot:
    enabled: bool
    severity: str | None
    params: dict[str, Any]
    applies_to: tuple[str, ...]
    title: str | None
    clause: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "severity": self.severity,
            "params": self.params,
            "applies_to": list(self.applies_to),
            "title": self.title,
            "clause": self.clause,
        }


@dataclass(frozen=True)
class RulesetDiffArtifactPaths:
    json_path: Path
    markdown_path: Path


def build_ruleset_diff(left_input: Path, right_input: Path) -> dict[str, Any]:
    left_root, left_ruleset = _load_ruleset_input(left_input)
    right_root, right_ruleset = _load_ruleset_input(right_input)

    left_snapshots = _build_snapshot_map(left_ruleset)
    right_snapshots = _build_snapshot_map(right_ruleset)

    rules: list[dict[str, Any]] = []
    enabled_changed = 0
    severity_changed = 0
    params_changed = 0
    applies_to_changed = 0
    title_changed = 0
    clause_changed = 0

    for rule_id in list_rule_ids():
        before = left_snapshots[rule_id]
        after = right_snapshots[rule_id]
        changes: dict[str, dict[str, Any]] = {}
        if before.enabled != after.enabled:
            enabled_changed += 1
            changes["enabled"] = {"from": before.enabled, "to": after.enabled}
        if before.severity != after.severity:
            severity_changed += 1
            changes["severity"] = {"from": before.severity, "to": after.severity}
        if before.params != after.params:
            params_changed += 1
            changes["params"] = {"from": before.params, "to": after.params}
        if before.applies_to != after.applies_to:
            applies_to_changed += 1
            changes["applies_to"] = {"from": list(before.applies_to), "to": list(after.applies_to)}
        if before.title != after.title:
            title_changed += 1
            changes["title"] = {"from": before.title, "to": after.title}
        if before.clause != after.clause:
            clause_changed += 1
            changes["clause"] = {"from": before.clause, "to": after.clause}
        if not changes:
            continue
        rules.append(
            {
                "rule_id": rule_id,
                "from": before.as_dict(),
                "to": after.as_dict(),
                "changes": changes,
            }
        )

    return {
        "report_kind": "ruleset_comparison_report",
        "report_format_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "left": {
            "path": str(left_root),
            "version": left_ruleset.version,
            "rule_count": len(left_ruleset.rule_configs),
        },
        "right": {
            "path": str(right_root),
            "version": right_ruleset.version,
            "rule_count": len(right_ruleset.rule_configs),
        },
        "summary": {
            "changed_rule_count": len(rules),
            "enabled_changed": enabled_changed,
            "severity_changed": severity_changed,
            "params_changed": params_changed,
            "applies_to_changed": applies_to_changed,
            "title_changed": title_changed,
            "clause_changed": clause_changed,
            "version_changed": left_ruleset.version != right_ruleset.version,
        },
        "rules": rules,
    }


def write_ruleset_diff_artifacts(left_input: Path, right_input: Path, output_path: Path) -> RulesetDiffArtifactPaths:
    artifact = build_ruleset_diff(left_input, right_input)
    json_path, markdown_path = _resolve_output_paths(output_path.resolve())
    json_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_ruleset_diff_markdown(artifact), encoding="utf-8")
    return RulesetDiffArtifactPaths(json_path=json_path, markdown_path=markdown_path)


def write_ruleset_diff_artifact(left_input: Path, right_input: Path, output_path: Path) -> Path:
    return write_ruleset_diff_artifacts(left_input, right_input, output_path).json_path


def render_ruleset_diff_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact["summary"]
    lines = [
        "# SparkFlow Ruleset Comparison Report",
        "",
        f"- generated_at: {artifact['generated_at']}",
        f"- left: {artifact['left']['version']} ({artifact['left']['path']})",
        f"- right: {artifact['right']['version']} ({artifact['right']['path']})",
        "",
        "## Summary",
        "",
        f"- version_changed: {summary['version_changed']}",
        f"- changed_rule_count: {summary['changed_rule_count']}",
        f"- enabled_changed: {summary['enabled_changed']}",
        f"- severity_changed: {summary['severity_changed']}",
        f"- params_changed: {summary['params_changed']}",
        f"- applies_to_changed: {summary['applies_to_changed']}",
        f"- title_changed: {summary['title_changed']}",
        f"- clause_changed: {summary['clause_changed']}",
        "",
        "## Rule Changes",
        "",
    ]
    if not artifact["rules"]:
        lines.append("No rule changes detected.")
        return "\n".join(lines) + "\n"

    for rule in artifact["rules"]:
        lines.append(f"### {rule['rule_id']}")
        for field_name in ("enabled", "severity", "params", "applies_to", "title", "clause"):
            change = rule["changes"].get(field_name)
            if change is None:
                continue
            lines.append(
                f"- {field_name}: {_format_markdown_value(change['from'])} -> {_format_markdown_value(change['to'])}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _load_ruleset_input(path: Path) -> tuple[Path, LoadedRuleset]:
    root = _resolve_ruleset_root(path)
    return root, load_ruleset_dir(root)


def _resolve_ruleset_root(path: Path) -> Path:
    candidate = path.resolve()
    if not candidate.exists():
        raise FileNotFoundError(str(candidate))
    if candidate.is_dir():
        return candidate
    if candidate.name == "ruleset.json":
        return candidate.parent.resolve()
    raise ValueError("规则集比较输入必须是规则集目录或 ruleset.json 文件。")


def _build_snapshot_map(loaded: LoadedRuleset) -> dict[str, _RuleSnapshot]:
    snapshots = {rule_id: _RuleSnapshot(False, None, {}, (), None, None) for rule_id in list_rule_ids()}
    for config in loaded.rule_configs:
        snapshots[config.rule_id] = _snapshot_from_config(config)
    return snapshots


def _snapshot_from_config(config: LoadedRuleConfig) -> _RuleSnapshot:
    applies_to = tuple(drawing_type for drawing_type in RULESET_DRAWING_TYPES if drawing_type in config.applies_to)
    return _RuleSnapshot(
        enabled=bool(config.enabled),
        severity=(config.severity.value if config.severity is not None else None),
        params=_canonicalize_value(config.params),
        applies_to=applies_to,
        title=config.title,
        clause=config.clause,
    )


def _resolve_output_paths(output_path: Path) -> tuple[Path, Path]:
    suffix = output_path.suffix.lower()
    if suffix == ".json":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path, output_path.with_suffix(".md")
    if suffix == ".md":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path.with_suffix(".json"), output_path

    output_path.mkdir(parents=True, exist_ok=True)
    return output_path / "ruleset_diff.json", output_path / "ruleset_diff.md"


def _format_markdown_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _canonicalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize_value(item) for item in value]
    return value
