from __future__ import annotations

from ..contracts import AuditReport


def serialize_report(report: AuditReport) -> dict:
    return {
        "created_at": report.created_at,
        "input_path": report.input_path,
        "input_sha256": report.input_sha256,
        "parser": report.parser,
        "rule_version": report.rule_version,
        "passed": report.passed,
        "summary": report.summary,
        "artifacts": report.artifacts,
        "issues": [
            {
                "rule_id": i.rule_id,
                "severity": i.severity.value,
                "message": i.message,
                "refs": [
                    {
                        "kind": r.kind,
                        "id": r.id,
                        "source_entity_ids": list(r.source_entity_ids),
                        "extra": r.extra,
                    }
                    for r in i.refs
                ],
            }
            for i in report.issues
        ],
    }
