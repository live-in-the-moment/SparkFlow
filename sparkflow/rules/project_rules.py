from __future__ import annotations

import re

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
    text_by_id = {text_id: str(text).replace(" ", "") for text_id, _, text in model.texts}
    text_entries = {
        text_id: (point, str(text).replace(" ", ""))
        for text_id, point, text in model.texts
    }
    device_matches: set[str] = set()
    represented_text_ids: set[str] = set()
    text_matches: set[str] = set()

    for device in model.devices:
        if _device_matches_project_key(device, key=key, aliases=aliases, text_by_id=text_by_id):
            device_matches.add(device.id)
            represented_text_ids.update(source_id for source_id in device.source_entity_ids if source_id in text_by_id)
            represented_text_ids.update(_nearby_label_text_ids(device, text_entries))

    for text_id, _, text in model.texts:
        normalized = str(text).replace(" ", "")
        if len(normalized) > 40:
            continue
        if text_id in represented_text_ids:
            continue
        if any(alias in normalized for alias in aliases):
            text_matches.add(normalized if len(normalized) <= 20 else f"{normalized}:{text_id}")

    return len(device_matches) + len(text_matches)


def _device_matches_project_key(
    device,
    *,
    key: str,
    aliases: tuple[str, ...],
    text_by_id: dict[str, str],
) -> bool:
    normalized_parts = [part.replace(" ", "") for part in (device.label or "", device.block_name or "", device.device_type or "")]
    normalized_parts.extend(text_by_id[source_id] for source_id in device.source_entity_ids if source_id in text_by_id)
    normalized_parts = [part for part in normalized_parts if part]

    if key == "distribution_transformer":
        if device.device_type != "transformer":
            return any(any(alias in part for alias in aliases) for part in normalized_parts)
        if _looks_like_current_transformer(normalized_parts):
            return False
        return True

    return any(any(alias in part for alias in aliases) for part in normalized_parts)


def _looks_like_current_transformer(normalized_parts: list[str]) -> bool:
    for part in normalized_parts:
        if "电流互感器" in part or "互感器" in part:
            return True
        if re.search(r"(^|[^A-Z])TA\d+", part, re.IGNORECASE):
            return True
        if part.upper().startswith("TA"):
            return True
    return False


def _nearby_label_text_ids(device, text_entries: dict[str, tuple[object, str]]) -> set[str]:
    if not device.label:
        return set()
    label = str(device.label).replace(" ", "").lower()
    if not label:
        return set()
    radius = max(float(device.footprint_radius or 0.0), 12.0)
    radius2 = radius * radius
    out: set[str] = set()
    for text_id, (point, normalized) in text_entries.items():
        if normalized.lower() != label:
            continue
        dx = float(point.x) - float(device.position.x)
        dy = float(point.y) - float(device.position.y)
        if dx * dx + dy * dy <= radius2:
            out.add(text_id)
    return out
