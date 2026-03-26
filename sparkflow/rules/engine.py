from __future__ import annotations

from collections.abc import Sequence

from ..contracts import Issue
from ..model.types import SystemModel
from .types import Rule, RuleBinding


class RuleEngine:
    def __init__(self, rules: Sequence[Rule | RuleBinding]) -> None:
        self._rules = [self._normalize_rule(rule) for rule in rules]

    def run(self, model: SystemModel, *, drawing_type: str | None = None) -> list[Issue]:
        issues: list[Issue] = []
        for binding in self._rules:
            if not binding.applies_to_drawing_type(drawing_type):
                continue
            res = binding.rule.run(model)
            if binding.severity_override is None:
                issues.extend(res.issues)
                continue
            issues.extend(
                Issue(
                    rule_id=issue.rule_id,
                    severity=binding.severity_override,
                    message=issue.message,
                    refs=issue.refs,
                )
                for issue in res.issues
            )
        return issues

    def _normalize_rule(self, rule: Rule | RuleBinding) -> RuleBinding:
        if isinstance(rule, RuleBinding):
            return rule
        return RuleBinding(rule=rule, rule_id=rule.rule_id)
