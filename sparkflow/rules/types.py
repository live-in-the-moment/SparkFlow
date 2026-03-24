from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..contracts import Issue
from ..model.types import SystemModel


@dataclass(frozen=True)
class RuleResult:
    issues: tuple[Issue, ...]


class Rule(Protocol):
    rule_id: str

    def run(self, model: SystemModel) -> RuleResult: ...
