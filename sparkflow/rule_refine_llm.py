from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

_MANUAL_ONLY_HINTS = (
    "设计说明书",
    "预算",
    "可研",
    "控制线",
    "物探报告",
    "材料清册",
    "预算书",
    "反事故措施",
    "危大清单",
    "带电作业位置照片",
    "勘察费",
    "甲供设备",
    "附件",
)


@dataclass(frozen=True)
class RuleRefineSettings:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout_sec: float = 20.0
    retries: int = 2
    max_tokens: int = 700
    batch_size: int = 8
    enabled: bool = False


def load_rule_refine_settings() -> RuleRefineSettings:
    env = _load_env_file(Path.cwd() / ".env")
    api_key = (os.environ.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY") or "").strip()
    base_url = (os.environ.get("OPENAI_BASE_URL") or env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
    model = (os.environ.get("OPENAI_MODEL") or env.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
    timeout_sec = _safe_float(os.environ.get("SPARKFLOW_RULE_REFINE_TIMEOUT_SEC"), 20.0)
    retries = _safe_int(os.environ.get("SPARKFLOW_RULE_REFINE_RETRIES"), 2)
    max_tokens = _safe_int(os.environ.get("SPARKFLOW_RULE_REFINE_MAX_TOKENS"), 700)
    batch_size = _safe_int(os.environ.get("SPARKFLOW_RULE_REFINE_BATCH_SIZE"), 8)
    return RuleRefineSettings(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model=model,
        timeout_sec=max(5.0, timeout_sec),
        retries=max(0, retries),
        max_tokens=max(200, max_tokens),
        batch_size=max(1, batch_size),
        enabled=bool(api_key and model),
    )


def refine_candidate_rules(
    candidate_rules: list[dict[str, Any]],
    *,
    mode: str = "heuristic",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started_at = time.time()
    settings = load_rule_refine_settings()
    normalized_candidates = [_build_candidate(rule) for rule in candidate_rules]
    trace: dict[str, Any] = {
        "mode_requested": mode,
        "mode_effective": mode,
        "settings": {
            "llm_enabled": settings.enabled,
            "base_url": settings.base_url,
            "model": settings.model,
            "timeout_sec": settings.timeout_sec,
            "retries": settings.retries,
            "max_tokens": settings.max_tokens,
            "batch_size": settings.batch_size,
        },
        "batches": [],
        "stats": {"keep": 0, "manual": 0, "discard": 0},
        "failures": [],
        "duration_sec": 0.0,
    }
    if mode == "off":
        decisions = [_heuristic_decide(item) | {"decision": "keep", "reason": "rule_refine=off"} for item in normalized_candidates]
    elif mode == "heuristic":
        decisions = [_heuristic_decide(item) for item in normalized_candidates]
    else:
        decisions, llm_failures, batches = _llm_or_fallback(normalized_candidates, settings=settings)
        trace["batches"] = batches
        trace["failures"] = llm_failures
        if llm_failures and not settings.enabled:
            trace["mode_effective"] = "heuristic_fallback"
    for decision in decisions:
        trace["stats"][decision["decision"]] = trace["stats"].get(decision["decision"], 0) + 1
    kept_rules: list[dict[str, Any]] = []
    for rule, decision in zip(candidate_rules, decisions):
        enriched = {
            **rule,
            "raw_text": decision["raw_text"],
            "normalized_text": decision["normalized_rule_text"],
            "refine_decision": decision["decision"],
            "refine_reason": decision["reason"],
        }
        if decision["decision"] == "discard":
            continue
        if decision["decision"] == "manual":
            enriched["scope"] = "manual"
            enriched["check_type"] = "manual_review"
            enriched["keywords"] = []
        kept_rules.append(enriched)
    trace["decisions"] = decisions
    trace["duration_sec"] = round(time.time() - started_at, 3)
    return kept_rules, trace


def _llm_or_fallback(
    candidates: list[dict[str, Any]],
    *,
    settings: RuleRefineSettings,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    if not settings.enabled:
        return ([_heuristic_decide(item) for item in candidates], ["OPENAI_API_KEY/OPENAI_MODEL 未配置，回退为 heuristic。"], [])
    decisions: list[dict[str, Any]] = []
    failures: list[str] = []
    batch_traces: list[dict[str, Any]] = []
    for idx in range(0, len(candidates), settings.batch_size):
        batch = candidates[idx : idx + settings.batch_size]
        try:
            batch_decisions = _request_llm_batch(batch, settings=settings)
            if len(batch_decisions) != len(batch):
                raise ValueError("LLM 返回数量与请求不一致")
            batch_traces.append({"batch_index": idx // settings.batch_size, "size": len(batch), "status": "ok"})
            decisions.extend(batch_decisions)
        except Exception as exc:
            reason = f"batch {idx // settings.batch_size} failed: {exc}"
            failures.append(reason)
            batch_traces.append({"batch_index": idx // settings.batch_size, "size": len(batch), "status": "fallback", "reason": str(exc)})
            decisions.extend([_heuristic_decide(item) for item in batch])
    return decisions, failures, batch_traces


def _request_llm_batch(batch: list[dict[str, Any]], *, settings: RuleRefineSettings) -> list[dict[str, Any]]:
    payload = {
        "model": settings.model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "你是审图规则归一化助手。只返回 JSON。decision 仅允许 keep/manual/discard。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "对每条候选规则做二次判别",
                        "output_schema": {
                            "items": [{"rule_id": "str", "decision": "keep|manual|discard", "reason": "str", "normalized_rule_text": "str"}]
                        },
                        "candidates": batch,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "max_tokens": settings.max_tokens,
        "temperature": 0,
    }
    body = json.dumps(payload).encode("utf-8")
    url = f"{settings.base_url}/chat/completions"
    last_exc: Exception | None = None
    for _ in range(settings.retries + 1):
        try:
            req = request.Request(
                url=url,
                data=body,
                headers={
                    "Authorization": f"Bearer {settings.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with request.urlopen(req, timeout=settings.timeout_sec) as resp:
                content = resp.read().decode("utf-8")
            data = json.loads(content)
            message_content = data["choices"][0]["message"]["content"]
            parsed = json.loads(message_content)
            items = parsed.get("items") or []
            by_rule_id = {str(item.get("rule_id")): item for item in items}
            outputs: list[dict[str, Any]] = []
            for candidate in batch:
                found = by_rule_id.get(candidate["rule_id"]) or {}
                decision = str(found.get("decision") or "").strip().lower()
                if decision not in {"keep", "manual", "discard"}:
                    decision = _heuristic_decide(candidate)["decision"]
                outputs.append(
                    {
                        "rule_id": candidate["rule_id"],
                        "decision": decision,
                        "reason": str(found.get("reason") or "llm未给出原因，已回落规则推断。"),
                        "raw_text": candidate["raw_text"],
                        "normalized_rule_text": str(found.get("normalized_rule_text") or candidate["normalized_rule_text"]),
                    }
                )
            return outputs
        except (TimeoutError, error.URLError, KeyError, ValueError, json.JSONDecodeError) as exc:
            last_exc = exc
            continue
    raise RuntimeError(f"LLM refine request failed: {last_exc}")


def _build_candidate(rule: dict[str, Any]) -> dict[str, Any]:
    raw = str(rule.get("source_text") or "")
    normalized = _normalize_space(raw)
    return {
        "rule_id": str(rule.get("rule_id") or ""),
        "raw_text": raw,
        "normalized_rule_text": normalized,
        "source_type": str(rule.get("source_type") or ""),
        "scope": str(rule.get("scope") or ""),
        "check_type": str(rule.get("check_type") or ""),
        "keywords": [str(item) for item in rule.get("keywords") or []],
    }


def _heuristic_decide(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = str(candidate.get("normalized_rule_text") or "")
    if not normalized:
        decision = "discard"
        reason = "规则文本为空或不可解析。"
    elif any(hint in normalized for hint in _MANUAL_ONLY_HINTS):
        decision = "manual"
        reason = "规则依赖说明书/预算等附件，保留人工复核。"
    else:
        decision = "keep"
        reason = "规则可在图纸文本层面继续自动审查。"
    return {
        "rule_id": candidate["rule_id"],
        "decision": decision,
        "reason": reason,
        "raw_text": str(candidate.get("raw_text") or ""),
        "normalized_rule_text": normalized,
    }


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip()) if value is not None and str(value).strip() else default
    except ValueError:
        return default


def _safe_float(value: str | None, default: float) -> float:
    try:
        return float(str(value).strip()) if value is not None and str(value).strip() else default
    except ValueError:
        return default


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            loaded[key] = value
    return loaded
