from __future__ import annotations

import json

from ..contracts import AuditReport
from .formal import build_formal_issue_details


def render_markdown_report(report: AuditReport) -> str:
    lines: list[str] = []
    formal_issue_details = build_formal_issue_details(report)
    lines.append("# SparkFlow 审图报告")
    lines.append("")
    lines.append(f"- created_at: {report.created_at}")
    lines.append(f"- input_path: {report.input_path}")
    lines.append(f"- input_sha256: {report.input_sha256}")
    lines.append(f"- parser: {report.parser}")
    lines.append(f"- rule_version: {report.rule_version}")
    lines.append(f"- passed: {str(report.passed).lower()}")
    lines.append("")
    rule_hit_notes = report.summary.get('rule_hit_notes') if isinstance(report.summary, dict) else None
    if report.summary:
        lines.append("## Summary")
        lines.append("")
        for k, v in report.summary.items():
            if k == 'rule_hit_notes':
                continue
            lines.append(f"- {k}: {_format_value(v)}")
        lines.append("")
    if isinstance(rule_hit_notes, list) and rule_hit_notes:
        lines.append("## Rule Hit Notes")
        lines.append("")
        for idx, note in enumerate(rule_hit_notes, start=1):
            lines.append(
                f"{idx}. [{note.get('severity', 'info')}] {note.get('rule_id')}: {note.get('title')}"
            )
            lines.append(f"   - count: {note.get('count')}")
            lines.append(f"   - drawing_type: {note.get('drawing_type_label')}")
            lines.append(f"   - meaning: {note.get('meaning')}")
            lines.append(f"   - grading_reason: {note.get('grading_reason')}")
        lines.append("")
    if report.artifacts:
        lines.append("## Artifacts")
        lines.append("")
        for k, v in report.artifacts.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    lines.append("## Issues")
    lines.append("")
    if not report.issues:
        lines.append("无问题。")
        lines.append("")
        return "\n".join(lines)

    for i, detail in enumerate(formal_issue_details, start=1):
        issue = detail.issue
        sev = issue.severity.value
        lines.append(f"{i}. [{sev}] {issue.rule_id}: {issue.message}")
        lines.append(f"   - article_clause_mapping: {detail.article_clause_mapping}")
        lines.append(f"   - remediation: {detail.remediation}")
        lines.append(f"   - risk_level: {detail.risk_level}")
        lines.append(f"   - confidence: {detail.confidence}")
        if issue.refs:
            for r in issue.refs:
                extra = ", ".join(f"{k}={v}" for k, v in r.extra.items()) if r.extra else ""
                src = ",".join(r.source_entity_ids) if r.source_entity_ids else ""
                suffix = " ".join(s for s in [extra, f"src={src}" if src else ""] if s)
                if suffix:
                    lines.append(f"   - {r.kind}:{r.id} {suffix}")
                else:
                    lines.append(f"   - {r.kind}:{r.id}")
    lines.append("")
    return "\n".join(lines)


def _format_value(value: object) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
