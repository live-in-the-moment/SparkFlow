from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ObjectRef:
    kind: str
    id: str
    source_entity_ids: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Issue:
    rule_id: str
    severity: Severity
    message: str
    refs: tuple[ObjectRef, ...] = ()


@dataclass(frozen=True)
class AuditReport:
    created_at: str
    input_path: str
    input_sha256: str
    parser: str
    rule_version: str
    issues: tuple[Issue, ...]
    summary: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(i.severity != Severity.ERROR for i in self.issues)

    @staticmethod
    def now_iso() -> str:
        return datetime.now().astimezone().isoformat()


@dataclass(frozen=True)
class AuditOutput:
    report_json_path: Path
    report_md_path: Path
    approved_artifact_dir: Path | None


@dataclass(frozen=True)
class DatasetAuditOutput:
    run_dir: Path
    index_json_path: Path
    summary_json_path: Path
    summary_md_path: Path
