from __future__ import annotations

from ..contracts import AuditReport


def render_markdown_report(report: AuditReport) -> str:
    lines: list[str] = []
    lines.append("# SparkFlow 审图报告")
    lines.append("")
    lines.append(f"- created_at: {report.created_at}")
    lines.append(f"- input_path: {report.input_path}")
    lines.append(f"- input_sha256: {report.input_sha256}")
    lines.append(f"- parser: {report.parser}")
    lines.append(f"- rule_version: {report.rule_version}")
    lines.append(f"- passed: {str(report.passed).lower()}")
    lines.append("")
    if report.summary:
        lines.append("## Summary")
        lines.append("")
        for k, v in report.summary.items():
            lines.append(f"- {k}: {v}")
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

    for i, issue in enumerate(report.issues, start=1):
        sev = issue.severity.value
        lines.append(f"{i}. [{sev}] {issue.rule_id}: {issue.message}")
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
