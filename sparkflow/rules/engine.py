from __future__ import annotations

from ..contracts import Issue
from ..model.types import SystemModel
from .types import Rule


class RuleEngine:
    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    def run(self, model: SystemModel) -> list[Issue]:
        issues: list[Issue] = []
        for r in self._rules:
            res = r.run(model)
            issues.extend(res.issues)
        return issues
