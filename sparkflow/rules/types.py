from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..contracts import Issue, Severity
from ..model.types import SystemModel

RULESET_DRAWING_TYPES = (
    'single_line',
    'electrical_schematic',
    'layout_or_installation',
    'general_supported_electrical',
    'other',
)


@dataclass(frozen=True)
class RuleResult:
    issues: tuple[Issue, ...]


class Rule(Protocol):
    rule_id: str

    def run(self, model: SystemModel) -> RuleResult: ...


@dataclass(frozen=True)
class RuleBinding:
    rule: Rule
    rule_id: str
    severity_override: Severity | None = None
    applies_to: tuple[str, ...] = ()

    def applies_to_drawing_type(self, drawing_type: str | None) -> bool:
        if drawing_type is None or not self.applies_to:
            return True
        return drawing_type in self.applies_to
