from __future__ import annotations

import hashlib
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .cad.errors import CadParseError, UnsupportedCadFormatError
from .cad.parse import CadParseOptions, parse_cad
from .contracts import AuditOutput, AuditReport, DatasetAuditOutput, Issue, ObjectRef, Severity
from .dataset import DatasetIndex, scan_dataset
from .model.build_options import (
    ModelBuildOptions,
    default_model_build_options,
    merge_model_build_options,
    model_build_options_from_dict,
)
from .model.builder import build_system_model
from .model.connectivity import ConnectivityBuildOptions, build_connectivity
from .model.electrical import build_electrical_graph
from .model.selection import resolve_selection, selection_texts_from_entities
from .model.types import DrawingSelection, SystemModel
from .reporting.debug_svg import write_debug_svg
from .reporting.docx_report import write_docx_report
from .reporting.markdown import render_markdown_report
from .reporting.serialize import serialize_report
from .rules.engine import RuleEngine
from .rules.knowledgebase import load_ruleset_dir
from .rules.ruleset import default_ruleset, rule_version
from .util import sha256_file


@dataclass(frozen=True)
class _FileAuditResult:
    rel_path: str
    status: str
    selection: DrawingSelection | None
    report: AuditReport
    report_json_path: Path
    report_md_path: Path
    approved_artifact_dir: Path | None
    elapsed_sec: float


def audit_file(
    input_path: Path,
    out_dir: Path,
    *,
    parse_options: CadParseOptions | None = None,
    level: int = 3,
    model_options: ModelBuildOptions | None = None,
    ruleset_dir: Path | None = None,
    selection_mode: str = 'auto',
    graph: str = 'electrical',
) -> AuditOutput:
    input_path = input_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    input_sha256 = sha256_file(input_path)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    rules, rules_ver, resolved_model_options = _resolve_rules_and_model_options(
        ruleset_dir=ruleset_dir,
        level=level,
        model_options=model_options,
    )
    result = _audit_single_path(
        input_path=input_path,
        rel_path=input_path.name,
        out_dir=run_dir,
        input_sha256=input_sha256,
        parse_options=parse_options,
        level=level,
        model_options=resolved_model_options,
        rules=rules,
        rules_ver=rules_ver,
        selection_mode=selection_mode,
        graph=graph,
        write_approved=True,
    )
    return AuditOutput(
        report_json_path=result.report_json_path,
        report_md_path=result.report_md_path,
        approved_artifact_dir=result.approved_artifact_dir,
    )


def index_dataset(dataset_dir: Path, out_dir: Path, *, compute_sha256: bool) -> Path:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    idx = scan_dataset(dataset_dir, compute_sha256=compute_sha256)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    index_path = run_dir / 'dataset_index.json'
    index_path.write_text(
        json.dumps(_serialize_dataset_index(idx), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return index_path


def audit_dataset(
    dataset_dir: Path,
    out_dir: Path,
    *,
    ruleset_dir: Path | None,
    compute_sha256: bool,
    dwg_backend: str | None,
    dwg_converter_cmd: list[str] | None,
    dwg_timeout_sec: float | None,
    dxf_backend: str | None,
    level: int = 3,
    topology_tol: float | None = None,
    model_options: ModelBuildOptions | None = None,
    workers: int = 3,
    selection: str = 'auto',
    graph: str = 'electrical',
) -> DatasetAuditOutput:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    idx = scan_dataset(dataset_dir, compute_sha256=compute_sha256)
    rules, rules_ver, resolved_model_options = _resolve_rules_and_model_options(
        ruleset_dir=ruleset_dir,
        level=level,
        model_options=model_options,
    )

    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    index_json_path = run_dir / 'dataset_index.json'
    index_json_path.write_text(
        json.dumps(_serialize_dataset_index(idx), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    summary = {
        'created_at': AuditReport.now_iso(),
        'dataset_dir': idx.root_dir,
        'rule_version': rules_ver,
        'counts': {'passed': 0, 'failed': 0, 'skipped': 0, 'unprocessed': 0},
        'selection_counts': {'supported_electrical': 0, 'geometry_only': 0, 'unsupported': 0},
        'issues_by_rule': {},
        'failures': [],
        'unprocessed': [],
        'timing': {'elapsed_sec': 0.0, 'avg_file_sec': 0.0, 'file_count': len(idx.entries)},
    }

    dataset_selection: list[dict[str, object]] = []
    start = time.perf_counter()
    parse_options = CadParseOptions(
        dwg_backend=dwg_backend,
        dwg_converter_cmd=dwg_converter_cmd,
        dwg_timeout_sec=dwg_timeout_sec,
        dxf_backend=dxf_backend,
        topology_tol=topology_tol,
    )

    future_map = {}
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        for entry in idx.entries:
            rel = entry.rel_path
            abs_path = Path(entry.abs_path)
            file_out_dir = _dataset_file_out_dir(run_dir, rel)
            file_out_dir.mkdir(parents=True, exist_ok=True)

            if entry.ext.lower() == 'pdf':
                summary['counts']['unprocessed'] += 1
                _write_unprocessed(file_out_dir, entry, reason='PDF 暂不解析。')
                summary['unprocessed'].append({'rel_path': rel, 'reason': 'PDF 暂不解析。'})
                continue

            future = executor.submit(
                _audit_single_path,
                input_path=abs_path,
                rel_path=rel,
                out_dir=file_out_dir,
                input_sha256=entry.sha256 or sha256_file(abs_path),
                parse_options=_file_parse_options(parse_options, file_out_dir),
                level=level,
                model_options=resolved_model_options,
                rules=rules,
                rules_ver=rules_ver,
                selection_mode=selection,
                graph=graph,
                write_approved=True,
            )
            future_map[future] = entry

        for future in as_completed(future_map):
            entry = future_map[future]
            result = future.result()
            dataset_selection.append(
                {
                    'rel_path': entry.rel_path,
                    'drawing_class': result.selection.drawing_class if result.selection else 'unknown',
                    'reason': result.selection.reason if result.selection else 'unknown',
                    'eligible_for_electrical': bool(result.selection.eligible_for_electrical) if result.selection else False,
                    'status': result.status,
                    'elapsed_sec': round(result.elapsed_sec, 6),
                }
            )
            if result.selection is not None:
                key = result.selection.drawing_class
                summary['selection_counts'][key] = summary['selection_counts'].get(key, 0) + 1
            summary['counts'][result.status] = summary['counts'].get(result.status, 0) + 1
            if result.status in {'failed', 'unprocessed'}:
                summary['failures'].append(
                    {
                        'rel_path': result.rel_path,
                        'status': result.status,
                        'passed': result.report.passed,
                    }
                )
            for issue in result.report.issues:
                summary['issues_by_rule'][issue.rule_id] = summary['issues_by_rule'].get(issue.rule_id, 0) + 1
            if result.status == 'unprocessed':
                first_issue = result.report.issues[0].message if result.report.issues else 'unknown'
                summary['unprocessed'].append({'rel_path': result.rel_path, 'reason': first_issue})

    elapsed = time.perf_counter() - start
    summary['timing']['elapsed_sec'] = round(elapsed, 6)
    cad_count = max(1, len(dataset_selection))
    summary['timing']['avg_file_sec'] = round(elapsed / cad_count, 6)

    dataset_selection.sort(key=lambda item: str(item.get('rel_path')))
    dataset_selection_path = run_dir / 'dataset_selection.json'
    dataset_selection_path.write_text(json.dumps(dataset_selection, ensure_ascii=False, indent=2), encoding='utf-8')

    summary_json_path = run_dir / 'dataset_summary.json'
    summary_md_path = run_dir / 'dataset_summary.md'
    summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    summary_md_path.write_text(_render_dataset_summary_md(summary), encoding='utf-8')

    return DatasetAuditOutput(
        run_dir=run_dir,
        index_json_path=index_json_path,
        summary_json_path=summary_json_path,
        summary_md_path=summary_md_path,
    )


def _resolve_rules_and_model_options(
    *,
    ruleset_dir: Path | None,
    level: int,
    model_options: ModelBuildOptions | None,
) -> tuple[list, str, ModelBuildOptions | None]:
    base_model_options = default_model_build_options() if level >= 3 else None
    rules = default_ruleset()
    rules_ver = rule_version()
    if ruleset_dir is not None:
        loaded = load_ruleset_dir(ruleset_dir)
        rules = loaded.rules
        rules_ver = loaded.version
        ruleset_model_options = model_build_options_from_dict(loaded.params.get('_model'))
        base_model_options = merge_model_build_options(base_model_options, ruleset_model_options)
    resolved_model_options = merge_model_build_options(base_model_options, model_options)
    return rules, rules_ver, resolved_model_options


def _audit_single_path(
    *,
    input_path: Path,
    rel_path: str,
    out_dir: Path,
    input_sha256: str,
    parse_options: CadParseOptions | None,
    level: int,
    model_options: ModelBuildOptions | None,
    rules: list,
    rules_ver: str,
    selection_mode: str,
    graph: str,
    write_approved: bool,
) -> _FileAuditResult:
    started = time.perf_counter()
    parsed = None
    selection = resolve_selection(input_path, rel_path=rel_path, mode=selection_mode)
    if _selection_needs_text_refinement(selection_mode, selection):
        parsed = parse_cad(input_path, options=parse_options)
        selection = resolve_selection(
            input_path,
            rel_path=rel_path,
            mode=selection_mode,
            texts=selection_texts_from_entities(parsed.entities),
        )
    selection_payload = {
        'drawing_class': selection.drawing_class,
        'reason': selection.reason,
        'eligible_for_electrical': selection.eligible_for_electrical,
    }
    selection_json_path = out_dir / 'selection.json'
    selection_json_path.write_text(json.dumps(selection_payload, ensure_ascii=False, indent=2), encoding='utf-8')

    report_json_path = out_dir / 'report.json'
    report_md_path = out_dir / 'report.md'
    artifacts: dict[str, str] = {'selection_json': 'selection.json', 'report_docx': 'report.docx'}
    approved_dir: Path | None = None

    if graph != 'electrical':
        raise ValueError(f'仅支持 electrical graph：{graph}')

    try:
        if not selection.eligible_for_electrical:
            summary = _build_skip_summary(selection)
            if parsed is not None and parsed.meta:
                summary['parse'] = parsed.meta
            report = AuditReport(
                created_at=AuditReport.now_iso(),
                input_path=str(input_path),
                input_sha256=input_sha256,
                parser=parsed.parser_id if parsed is not None else 'skipped',
                rule_version=rules_ver,
                issues=(),
                summary=summary,
                artifacts=artifacts,
            )
            status = 'skipped'
        else:
            if parsed is None:
                parsed = parse_cad(input_path, options=parse_options)
            model = _attach_selection(build_system_model(parsed.entities, options=model_options), selection)
            if level >= 3:
                tol = 1.0
                if parse_options is not None and parse_options.topology_tol is not None:
                    tol = float(parse_options.topology_tol)
                model = build_connectivity(model, options=ConnectivityBuildOptions(tol=tol))
                model = build_electrical_graph(model)
                artifacts['connectivity_json'] = 'connectivity.json'
                artifacts['electrical_json'] = 'electrical.json'
                artifacts['debug_svg'] = 'debug_overlay.svg'
                (out_dir / 'connectivity.json').write_text(
                    json.dumps(_serialize_connectivity(model), ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
                (out_dir / 'electrical.json').write_text(
                    json.dumps(_serialize_electrical(model), ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )
                write_debug_svg(model, out_dir / 'debug_overlay.svg', title=rel_path)
            summary = _build_summary(model, selection)
            if parsed.meta:
                summary['parse'] = parsed.meta
            engine = RuleEngine(rules)
            issues = tuple(engine.run(model))
            report = AuditReport(
                created_at=AuditReport.now_iso(),
                input_path=str(input_path),
                input_sha256=input_sha256,
                parser=parsed.parser_id,
                rule_version=rules_ver,
                issues=issues,
                summary=summary,
                artifacts=artifacts,
            )
            status = 'passed' if report.passed else 'failed'
    except (CadParseError, UnsupportedCadFormatError) as exc:
        report = AuditReport(
            created_at=AuditReport.now_iso(),
            input_path=str(input_path),
            input_sha256=input_sha256,
            parser='unprocessed',
            rule_version=rules_ver,
            issues=(
                Issue(
                    rule_id='cad.parse_failed',
                    severity=Severity.ERROR,
                    message=str(exc),
                    refs=(
                        ObjectRef(
                            kind='file',
                            id=str(input_path),
                            extra={'reason': str(exc), 'level': int(level)},
                        ),
                    ),
                ),
            ),
            summary=_build_failure_summary(selection, str(exc)),
            artifacts=artifacts,
        )
        status = 'unprocessed'
    except Exception as exc:  # pragma: no cover - defensive batch isolation
        report = AuditReport(
            created_at=AuditReport.now_iso(),
            input_path=str(input_path),
            input_sha256=input_sha256,
            parser='unprocessed',
            rule_version=rules_ver,
            issues=(
                Issue(
                    rule_id='audit.internal_error',
                    severity=Severity.ERROR,
                    message=str(exc),
                    refs=(ObjectRef(kind='file', id=str(input_path)),),
                ),
            ),
            summary=_build_failure_summary(selection, str(exc)),
            artifacts=artifacts,
        )
        status = 'unprocessed'

    report_json_path.write_text(json.dumps(serialize_report(report), ensure_ascii=False, indent=2), encoding='utf-8')
    report_md_path.write_text(render_markdown_report(report), encoding='utf-8')
    write_docx_report(report, out_dir / 'report.docx')

    if write_approved and selection.eligible_for_electrical and report.passed:
        approved_dir = out_dir / 'approved'
        approved_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, approved_dir / input_path.name)
        (approved_dir / 'approval.json').write_text(
            json.dumps(
                {
                    'created_at': report.created_at,
                    'input_sha256': report.input_sha256,
                    'input_path': report.input_path,
                    'rule_version': report.rule_version,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding='utf-8',
        )

    elapsed_sec = time.perf_counter() - started
    return _FileAuditResult(
        rel_path=rel_path,
        status=status,
        selection=selection,
        report=report,
        report_json_path=report_json_path,
        report_md_path=report_md_path,
        approved_artifact_dir=approved_dir,
        elapsed_sec=elapsed_sec,
    )


def _selection_needs_text_refinement(selection_mode: str, selection: DrawingSelection) -> bool:
    mode = (selection_mode or 'auto').strip()
    if mode != 'auto':
        return False
    if selection.drawing_class == 'geometry_only':
        return False
    return selection.reason in {
        'matched_parent_dir:电缆CAD图纸',
        'matched_supported_keyword:380v',
        'no_supported_keyword_match',
    }

def _attach_selection(model: SystemModel, selection: DrawingSelection) -> SystemModel:
    return SystemModel(
        wires=model.wires,
        devices=model.devices,
        texts=model.texts,
        entity_index=model.entity_index,
        selection=selection,
        unresolved=model.unresolved,
        connectivity=model.connectivity,
        electrical=model.electrical,
    )


def _build_skip_summary(selection: DrawingSelection) -> dict:
    return {
        'classification': {
            'drawing_class': selection.drawing_class,
            'reason': selection.reason,
            'eligible_for_electrical': selection.eligible_for_electrical,
        },
        'connectivity': {'enabled': False, 'reason': 'drawing_not_eligible'},
        'electrical': {'enabled': False, 'reason': 'drawing_not_eligible'},
    }


def _build_failure_summary(selection: DrawingSelection, reason: str) -> dict:
    base = _build_skip_summary(selection)
    base['connectivity'] = {'enabled': False, 'reason': reason}
    base['electrical'] = {'enabled': False, 'reason': reason}
    return base


def _build_summary(model: SystemModel, selection: DrawingSelection) -> dict:
    out = {
        'classification': {
            'drawing_class': selection.drawing_class,
            'reason': selection.reason,
            'eligible_for_electrical': selection.eligible_for_electrical,
        },
        'connectivity': _connectivity_summary(model),
        'electrical': _electrical_summary(model),
    }
    return out


def _connectivity_summary(model: SystemModel) -> dict:
    connectivity = model.connectivity
    if connectivity is None:
        return {'enabled': False}
    return {
        'enabled': True,
        'tol': connectivity.tol,
        'wire_count': len(model.wires),
        'node_count': len(connectivity.nodes),
        'edge_count': len(connectivity.edges),
        'junction_count': len(connectivity.junctions),
        'terminal_anchor_count': len(connectivity.terminal_anchors),
    }


def _electrical_summary(model: SystemModel) -> dict:
    electrical = model.electrical
    if electrical is None:
        return {'enabled': False}
    component_types: dict[str, int] = {}
    for component in electrical.components:
        component_types[component.type] = component_types.get(component.type, 0) + 1
    return {
        'enabled': True,
        'component_count': len(electrical.components),
        'component_types': dict(sorted(component_types.items(), key=lambda item: (-item[1], item[0]))),
        'terminal_count': len(electrical.terminals),
        'net_count': len(electrical.nets),
        'relation_count': len(electrical.relations),
        'unresolved_count': len(electrical.unresolved),
    }


def _serialize_dataset_index(idx: DatasetIndex) -> dict:
    return {
        'root_dir': idx.root_dir,
        'entries': [
            {
                'rel_path': entry.rel_path,
                'abs_path': entry.abs_path,
                'ext': entry.ext,
                'size_bytes': entry.size_bytes,
                'mtime_epoch': entry.mtime_epoch,
                'sha256': entry.sha256,
            }
            for entry in idx.entries
        ],
    }


def _serialize_connectivity(model: SystemModel) -> dict:
    connectivity = model.connectivity
    if connectivity is None:
        return {}
    return {
        'tol': connectivity.tol,
        'nodes': [{'id': idx, 'x': point.x, 'y': point.y} for idx, point in enumerate(connectivity.nodes)],
        'edges': [
            {'a': edge.a, 'b': edge.b, 'source_entity_ids': list(edge.source_entity_ids)}
            for edge in connectivity.edges
        ],
        'junctions': list(connectivity.junctions),
        'terminal_anchors': dict(sorted(connectivity.terminal_anchors.items())),
    }


def _serialize_electrical(model: SystemModel) -> dict:
    electrical = model.electrical
    if electrical is None:
        return {}
    return {
        'components': [
            {
                'id': component.id,
                'type': component.type,
                'label': component.label,
                'source_entity_ids': list(component.source_entity_ids),
                'terminal_ids': list(component.terminal_ids),
            }
            for component in electrical.components
        ],
        'terminals': [
            {
                'id': terminal.id,
                'component_id': terminal.component_id,
                'role': terminal.role,
                'x': terminal.x,
                'y': terminal.y,
                'node_id': terminal.node_id,
            }
            for terminal in electrical.terminals
        ],
        'nets': [
            {'id': net.id, 'terminal_ids': list(net.terminal_ids), 'node_ids': list(net.node_ids)}
            for net in electrical.nets
        ],
        'relations': [
            {
                'id': relation.id,
                'type': relation.type,
                'from_terminal_id': relation.from_terminal_id,
                'to_terminal_id': relation.to_terminal_id,
                'state': relation.state,
            }
            for relation in electrical.relations
        ],
        'unresolved': [
            {
                'kind': item.kind,
                'source_entity_ids': list(item.source_entity_ids),
                'reason': item.reason,
                'extra': item.extra,
            }
            for item in electrical.unresolved
        ],
    }


def _dataset_file_out_dir(run_dir: Path, rel_path: str) -> Path:
    path = Path(*rel_path.split('/'))
    token = hashlib.sha1(rel_path.encode('utf-8')).hexdigest()[:8]
    return run_dir / 'files' / path.parent / f'{path.stem}__{token}'


def _file_parse_options(parse_options: CadParseOptions | None, file_out_dir: Path) -> CadParseOptions | None:
    if parse_options is None:
        return None
    return CadParseOptions(
        dwg_backend=parse_options.dwg_backend,
        dwg_converter_cmd=parse_options.dwg_converter_cmd,
        dwg_work_dir=(file_out_dir / '_dwg_work'),
        dwg_timeout_sec=parse_options.dwg_timeout_sec,
        dxf_backend=parse_options.dxf_backend,
        topology_tol=parse_options.topology_tol,
    )


def _write_unprocessed(out_dir: Path, entry, *, reason: str) -> None:
    (out_dir / 'unprocessed.json').write_text(
        json.dumps(
            {
                'rel_path': entry.rel_path,
                'abs_path': entry.abs_path,
                'ext': entry.ext,
                'reason': reason,
                'sha256': entry.sha256,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )


def _render_dataset_summary_md(summary: dict) -> str:
    lines: list[str] = []
    lines.append('# SparkFlow 数据集电气审图汇总')
    lines.append('')
    lines.append(f"- created_at: {summary.get('created_at')}")
    lines.append(f"- dataset_dir: {summary.get('dataset_dir')}")
    lines.append(f"- rule_version: {summary.get('rule_version')}")
    lines.append('')
    counts = summary.get('counts', {})
    lines.append('## Counts')
    lines.append('')
    for key in ('passed', 'failed', 'skipped', 'unprocessed'):
        lines.append(f"- {key}: {counts.get(key, 0)}")
    lines.append('')
    lines.append('## Selection')
    lines.append('')
    for key, value in sorted((summary.get('selection_counts') or {}).items()):
        lines.append(f'- {key}: {value}')
    lines.append('')
    lines.append('## Timing')
    lines.append('')
    timing = summary.get('timing', {})
    lines.append(f"- elapsed_sec: {timing.get('elapsed_sec', 0)}")
    lines.append(f"- avg_file_sec: {timing.get('avg_file_sec', 0)}")
    lines.append('')
    lines.append('## Issues By Rule')
    lines.append('')
    issues_by_rule = summary.get('issues_by_rule', {})
    if not issues_by_rule:
        lines.append('无。')
    else:
        for rule_id, count in sorted(issues_by_rule.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f'- {rule_id}: {count}')
    lines.append('')
    lines.append('## Failures')
    lines.append('')
    failures = summary.get('failures', [])
    if not failures:
        lines.append('无。')
    else:
        for item in failures[:200]:
            lines.append(f"- {item.get('rel_path')}: {item.get('status')}")
    lines.append('')
    return '\n'.join(lines)
