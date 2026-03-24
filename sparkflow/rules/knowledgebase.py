from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .registry import build_rule, list_rule_ids
from .types import Rule


@dataclass(frozen=True)
class LoadedRuleset:
    version: str
    rules: list[Rule]
    params: dict[str, Any]


def load_ruleset_dir(rules_dir: Path) -> LoadedRuleset:
    rules_dir = rules_dir.resolve()
    cfg_path = rules_dir / "ruleset.json"
    if not cfg_path.exists():
        raise FileNotFoundError(str(cfg_path))

    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("ruleset.json 不是对象。")

    version = raw.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("ruleset.json 缺少 version。")

    enabled = raw.get("enabled_rules")
    if enabled is None:
        enabled_ids = list_rule_ids()
    else:
        if not isinstance(enabled, list) or not all(isinstance(x, str) for x in enabled):
            raise ValueError("ruleset.json 的 enabled_rules 必须是字符串数组。")
        enabled_ids = list(enabled)

    params = raw.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError("ruleset.json 的 params 必须是对象。")

    rules: list[Rule] = []
    for rid in enabled_ids:
        p = params.get(rid, None)
        if p is None:
            p = {}
        if not isinstance(p, dict):
            raise ValueError(f"ruleset.json 的 params[{rid}] 必须是对象。")
        try:
            rules.append(build_rule(rid, p))
        except KeyError as e:
            raise ValueError(f"未知规则：{rid}") from e

    return LoadedRuleset(version=version.strip(), rules=rules, params=params)


def write_minimal_ruleset_dir(rules_dir: Path) -> None:
    rules_dir = rules_dir.resolve()
    rules_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = rules_dir / "ruleset.json"
    cfg_path.write_text(
        json.dumps(
            {
                "version": "example_ruleset_v1",
                "enabled_rules": list_rule_ids(),
                "params": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
