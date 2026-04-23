from __future__ import annotations

from ..contracts import Issue, ObjectRef, Severity
from ..model.types import SystemModel
from ..project_docs import (
    project_document_aliases,
    project_document_display_name,
    project_document_mentions,
    project_document_note_exists,
)
from .types import RuleResult


class ProjectQuantityConsistencyRule:
    def __init__(self, *, key: str, severity: str = "error") -> None:
        self._key = key
        self._severity = Severity(severity)

    @property
    def rule_id(self) -> str:
        return f"project.{self._key}.count_mismatch"

    def run(self, model: SystemModel) -> RuleResult:
        context = model.project_documents
        if context is None:
            return RuleResult(issues=())
        expected = context.expected_counts.get(self._key)
        if expected is None:
            return RuleResult(issues=())
        actual = _count_drawing_occurrences(model, self._key)
        if actual == int(round(expected)):
            return RuleResult(issues=())
        display_name = project_document_display_name(self._key)
        issue = Issue(
            rule_id=self.rule_id,
            severity=self._severity,
            message=f"{display_name}数量与工程附件不一致：期望 {int(round(expected))}，图纸识别 {actual}。",
            refs=(
                ObjectRef(
                    kind="project_document",
                    id=self._key,
                    extra={
                        "display_name": display_name,
                        "expected": int(round(expected)),
                        "actual": actual,
                        "project_root": context.project_root,
                    },
                ),
            ),
        )
        return RuleResult(issues=(issue,))


class ProjectPresenceRule:
    def __init__(self, *, key: str, severity: str = "warning") -> None:
        self._key = key
        self._severity = Severity(severity)

    @property
    def rule_id(self) -> str:
        return f"project.{self._key}.missing_presence"

    def run(self, model: SystemModel) -> RuleResult:
        context = model.project_documents
        if context is None or not project_document_mentions(context, self._key):
            return RuleResult(issues=())
        if _count_drawing_occurrences(model, self._key) > 0:
            return RuleResult(issues=())
        display_name = project_document_display_name(self._key)
        issue = Issue(
            rule_id=self.rule_id,
            severity=self._severity,
            message=f"工程附件提到{display_name}，但图纸中未发现对应体现或安装位置信息。",
            refs=(ObjectRef(kind="project_document", id=self._key, extra={"display_name": display_name}),),
        )
        return RuleResult(issues=(issue,))


class ProjectQuantityNoteRule:
    def __init__(self, *, key: str, severity: str = "warning") -> None:
        self._key = key
        self._severity = Severity(severity)

    @property
    def rule_id(self) -> str:
        return f"project.{self._key}.missing_quantity_note"

    def run(self, model: SystemModel) -> RuleResult:
        context = model.project_documents
        if context is None or not project_document_mentions(context, self._key):
            return RuleResult(issues=())
        if project_document_note_exists(context, self._key):
            return RuleResult(issues=())
        display_name = project_document_display_name(self._key)
        issue = Issue(
            rule_id=self.rule_id,
            severity=self._severity,
            message=f"工程附件中未发现{display_name}的工程量说明或等价说明条目。",
            refs=(ObjectRef(kind="project_document", id=self._key, extra={"display_name": display_name}),),
        )
        return RuleResult(issues=(issue,))


def _count_drawing_occurrences(model: SystemModel, key: str) -> int:
    aliases = tuple(alias.replace(" ", "") for alias in project_document_aliases(key))
    if not aliases:
        return 0
    device_matches: set[str] = set()
    text_matches: set[str] = set()

    if key == "distribution_transformer":
        for device in model.devices:
            if device.device_type == "transformer":
                device_matches.add(device.id)

    for device in model.devices:
        parts = [device.label or "", device.block_name or "", device.device_type or ""]
        normalized = "".join(part.replace(" ", "") for part in parts)
        if normalized and any(alias in normalized for alias in aliases):
            device_matches.add(device.id)

    for text_id, _, text in model.texts:
        normalized = str(text).replace(" ", "")
        if len(normalized) > 40:
            continue
        if any(alias in normalized for alias in aliases):
            text_matches.add(normalized if len(normalized) <= 20 else f"{normalized}:{text_id}")

    if device_matches:
        return len(device_matches)
    return len(text_matches)
