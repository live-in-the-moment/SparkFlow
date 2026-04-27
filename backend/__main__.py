from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

from .cad.errors import CadParseError, UnsupportedCadFormatError
from .cad.parse import CadParseOptions
from .core import audit_dataset, audit_file, index_dataset
from .model.build_options import model_build_options_from_dict
from .reporting.dataset_report import write_dataset_audit_report
from .reporting.rectification_checklist import write_rectification_checklist
from .review import review_audit, write_drawing_info
from .review_workflow import review_pipeline
from .rules.diffing import write_ruleset_diff_artifacts
from .server import run_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='sparkflow')
    sub = parser.add_subparsers(dest='cmd', required=True)

    audit = sub.add_parser('audit', help='审图并生成报告')
    audit.add_argument('path', type=Path, help='DWG/DXF 文件路径')
    audit.add_argument('--out', type=Path, default=Path('out'), help='输出目录')
    audit.add_argument('--ruleset', type=Path, default=None, help='规则库目录（包含 ruleset.json）')
    audit.add_argument('--dxf-backend', type=str, default='auto', choices=['ascii', 'ezdxf', 'auto'])
    audit.add_argument('--dwg-backend', type=str, default='auto', choices=['auto', 'cli', 'autocad'])
    audit.add_argument('--dwg-converter', type=str, default='')
    audit.add_argument('--dwg-timeout', type=float, default=None)
    audit.add_argument('--level', type=int, default=3, choices=[1, 2, 3], help=argparse.SUPPRESS)
    audit.add_argument('--topo-tol', type=float, default=1.0, help='连通图吸附容差（默认1.0）')
    audit.add_argument('--selection', type=str, default='auto', help='筛图策略：auto 或 list=<manifest>')
    audit.add_argument('--graph', type=str, default='electrical', choices=['electrical'])
    audit.add_argument('--wire-layer-include', action='append', default=None)
    audit.add_argument('--wire-layer-exclude', action='append', default=None)
    audit.add_argument('--wire-ltype-include', action='append', default=None)
    audit.add_argument('--wire-ltype-exclude', action='append', default=None)
    audit.add_argument('--wire-min-length', type=float, default=None)

    index = sub.add_parser('index', help='扫描目录并生成数据集索引')
    index.add_argument('dir', type=Path, help='包含 DWG/DXF/PDF 的目录')
    index.add_argument('--out', type=Path, default=Path('out'), help='输出目录')
    index.add_argument('--hash', action='store_true', help='计算 sha256（可能较慢）')

    audit_dataset_cmd = sub.add_parser('audit-dataset', help='批量审图并生成汇总报告')
    audit_dataset_cmd.add_argument('dir', type=Path, help='包含 DWG/DXF/PDF 的目录')
    audit_dataset_cmd.add_argument('--out', type=Path, default=Path('out'), help='输出目录')
    audit_dataset_cmd.add_argument('--hash', action='store_true', help='计算 sha256（可能较慢）')
    audit_dataset_cmd.add_argument('--ruleset', type=Path, default=None, help='规则库目录（包含 ruleset.json）')
    audit_dataset_cmd.add_argument('--dwg-backend', type=str, default='auto', choices=['auto', 'cli', 'autocad'])
    audit_dataset_cmd.add_argument('--dwg-converter', type=str, default='')
    audit_dataset_cmd.add_argument('--dwg-timeout', type=float, default=None)
    audit_dataset_cmd.add_argument('--dxf-backend', type=str, default='auto', choices=['ascii', 'ezdxf', 'auto'])
    audit_dataset_cmd.add_argument('--level', type=int, default=3, choices=[1, 2, 3], help=argparse.SUPPRESS)
    audit_dataset_cmd.add_argument('--topo-tol', type=float, default=1.0, help='连通图吸附容差（默认1.0）')
    audit_dataset_cmd.add_argument('--workers', type=int, default=3, help='并发 worker 数（默认3）')
    audit_dataset_cmd.add_argument('--selection', type=str, default='auto', help='筛图策略：auto 或 list=<manifest>')
    audit_dataset_cmd.add_argument('--graph', type=str, default='electrical', choices=['electrical'])
    audit_dataset_cmd.add_argument('--wire-layer-include', action='append', default=None)
    audit_dataset_cmd.add_argument('--wire-layer-exclude', action='append', default=None)
    audit_dataset_cmd.add_argument('--wire-ltype-include', action='append', default=None)
    audit_dataset_cmd.add_argument('--wire-ltype-exclude', action='append', default=None)
    audit_dataset_cmd.add_argument('--wire-min-length', type=float, default=None)

    dataset_report_cmd = sub.add_parser('dataset-report', help='基于 audit-dataset 结果生成数据集最终报告')
    dataset_report_cmd.add_argument('run_dir', type=Path, help='audit-dataset 生成的运行目录')
    dataset_report_cmd.add_argument('--ruleset', type=Path, default=None, help='规则库目录（用于提取严格规则说明）')
    dataset_report_cmd.add_argument('--out-md', type=Path, default=None, help='Markdown 输出路径')
    dataset_report_cmd.add_argument('--out-docx', type=Path, default=None, help='DOCX 输出路径')
    dataset_report_cmd.add_argument('--title', type=str, default='', help='报告标题')
    dataset_report_cmd.add_argument('--dataset-label', type=str, default='', help='数据集标签（默认取 dataset_dir 最后一级目录）')

    rectification_checklist_cmd = sub.add_parser(
        'rectification-checklist',
        help='基于现有 audit-dataset 结果生成失败图纸整改清单',
    )
    rectification_checklist_cmd.add_argument('run_dir', type=Path, help='audit-dataset 生成的运行目录')
    rectification_checklist_cmd.add_argument('--out-md', type=Path, default=None, help='Markdown 输出路径')
    rectification_checklist_cmd.add_argument('--out-docx', type=Path, default=None, help='DOCX 输出路径')
    rectification_checklist_cmd.add_argument('--out-json', type=Path, default=None, help='JSON 输出路径')
    rectification_checklist_cmd.add_argument('--title', type=str, default='', help='报告标题')
    rectification_checklist_cmd.add_argument('--dataset-label', type=str, default='', help='数据集标签（默认取 dataset_dir 最后一级目录）')

    ruleset_diff_cmd = sub.add_parser('ruleset-diff', help='比较两个规则集并输出 JSON/Markdown 比较报告')
    ruleset_diff_cmd.add_argument('left', type=Path, help='基线规则集目录或 ruleset.json')
    ruleset_diff_cmd.add_argument('right', type=Path, help='目标规则集目录或 ruleset.json')
    ruleset_diff_cmd.add_argument('--out', type=Path, default=Path('ruleset_diff.json'), help='比较报告输出路径（.json/.md 或目录）')

    drawing_info_cmd = sub.add_parser('drawing-info', help='提取图纸结构化信息并输出 JSON')
    drawing_info_cmd.add_argument('path', type=Path, help='DWG/DXF 文件路径')
    drawing_info_cmd.add_argument('--out', type=Path, required=True, help='输出 JSON 路径')
    drawing_info_cmd.add_argument('--dxf-backend', type=str, default='auto', choices=['ascii', 'ezdxf', 'auto'])
    drawing_info_cmd.add_argument('--dwg-backend', type=str, default='auto', choices=['auto', 'cli', 'autocad'])
    drawing_info_cmd.add_argument('--dwg-converter', type=str, default='')
    drawing_info_cmd.add_argument('--dwg-timeout', type=float, default=None)
    drawing_info_cmd.add_argument('--topo-tol', type=float, default=1.0, help='连通图吸附容差（默认1.0）')

    review_audit_cmd = sub.add_parser('review-audit', help='基于评审意见目录生成评审规则审查报告')
    review_audit_cmd.add_argument('path', type=Path, help='DWG/DXF 文件路径')
    review_audit_cmd.add_argument('--review-dir', type=Path, required=True, help='评审意见目录')
    review_audit_cmd.add_argument('--out', type=Path, default=Path('out'), help='输出目录')
    review_audit_cmd.add_argument('--project-code', type=str, default='', help='工程编号；默认尝试从图纸路径推断')
    review_audit_cmd.add_argument('--ruleset', type=Path, default=None, help='规则库目录（包含 ruleset.json）')
    review_audit_cmd.add_argument('--dxf-backend', type=str, default='auto', choices=['ascii', 'ezdxf', 'auto'])
    review_audit_cmd.add_argument('--dwg-backend', type=str, default='auto', choices=['auto', 'cli', 'autocad'])
    review_audit_cmd.add_argument('--dwg-converter', type=str, default='')
    review_audit_cmd.add_argument('--dwg-timeout', type=float, default=None)
    review_audit_cmd.add_argument('--level', type=int, default=3, choices=[1, 2, 3], help=argparse.SUPPRESS)
    review_audit_cmd.add_argument('--topo-tol', type=float, default=1.0, help='连通图吸附容差（默认1.0）')
    review_audit_cmd.add_argument('--selection', type=str, default='auto', help='筛图策略：auto 或 list=<manifest>')
    review_audit_cmd.add_argument('--graph', type=str, default='electrical', choices=['electrical'])
    review_audit_cmd.add_argument('--skip-sparkflow-audit', action='store_true', help='跳过通用 SparkFlow 审图，仅输出评审规则审查报告')
    review_audit_cmd.add_argument('--wire-layer-include', action='append', default=None)
    review_audit_cmd.add_argument('--wire-layer-exclude', action='append', default=None)
    review_audit_cmd.add_argument('--wire-ltype-include', action='append', default=None)
    review_audit_cmd.add_argument('--wire-ltype-exclude', action='append', default=None)
    review_audit_cmd.add_argument('--wire-min-length', type=float, default=None)

    review_pipeline_cmd = sub.add_parser('review-pipeline', help='执行 DWG/DXF 评审规则审查、图框拆分并生成整改问题清单')
    review_pipeline_cmd.add_argument('path', type=Path, help='DWG/DXF 文件路径')
    review_pipeline_cmd.add_argument('--review-dir', type=Path, required=True, help='评审意见目录')
    review_pipeline_cmd.add_argument('--out', type=Path, default=Path('out'), help='输出目录')
    review_pipeline_cmd.add_argument('--project-code', type=str, default='', help='工程编号；默认尝试从图纸路径推断')
    review_pipeline_cmd.add_argument('--ruleset', type=Path, default=None, help='规则库目录（包含 ruleset.json）')
    review_pipeline_cmd.add_argument('--dxf-backend', type=str, default='auto', choices=['ascii', 'ezdxf', 'auto'])
    review_pipeline_cmd.add_argument('--dwg-backend', type=str, default='auto', choices=['auto', 'cli', 'autocad'])
    review_pipeline_cmd.add_argument('--dwg-converter', type=str, default='')
    review_pipeline_cmd.add_argument('--dwg-timeout', type=float, default=None)
    review_pipeline_cmd.add_argument('--level', type=int, default=3, choices=[1, 2, 3], help=argparse.SUPPRESS)
    review_pipeline_cmd.add_argument('--topo-tol', type=float, default=1.0, help='连通图吸附容差（默认1.0）')
    review_pipeline_cmd.add_argument('--selection', type=str, default='auto', help='筛图策略：auto 或 list=<manifest>')
    review_pipeline_cmd.add_argument('--graph', type=str, default='electrical', choices=['electrical'])
    review_pipeline_cmd.add_argument('--skip-sparkflow-audit', action='store_true', help='跳过通用 SparkFlow 审图，仅输出评审规则审查、拆分和整改清单')
    review_pipeline_cmd.add_argument('--wire-layer-include', action='append', default=None)
    review_pipeline_cmd.add_argument('--wire-layer-exclude', action='append', default=None)
    review_pipeline_cmd.add_argument('--wire-ltype-include', action='append', default=None)
    review_pipeline_cmd.add_argument('--wire-ltype-exclude', action='append', default=None)
    review_pipeline_cmd.add_argument('--wire-min-length', type=float, default=None)

    serve_cmd = sub.add_parser('serve', help='启动 REST API 审图服务')
    serve_cmd.add_argument('--host', type=str, default='0.0.0.0', help='监听地址（默认 0.0.0.0）')
    serve_cmd.add_argument('--port', type=int, default=8600, help='监听端口（默认 8600）')

    args = parser.parse_args(argv)

    if args.cmd == 'audit':
        try:
            cmd_str = (args.dwg_converter or '').strip() or os.environ.get('SPARKFLOW_DWG2DXF_CMD', '').strip()
            dwg_cmd = _parse_dwg_converter_cmd(cmd_str)
            model_options = _build_model_options(args)
            output = audit_file(
                args.path,
                args.out,
                parse_options=CadParseOptions(
                    dwg_backend=args.dwg_backend,
                    dwg_converter_cmd=dwg_cmd,
                    dwg_timeout_sec=args.dwg_timeout,
                    dxf_backend=args.dxf_backend,
                    topology_tol=args.topo_tol,
                ),
                level=args.level,
                model_options=model_options,
                ruleset_dir=(args.ruleset if args.ruleset else None),
                selection_mode=args.selection,
                graph=args.graph,
            )
        except FileNotFoundError:
            print('文件不存在。', file=sys.stderr)
            return 2
        except UnsupportedCadFormatError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except CadParseError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print(str(output.report_json_path))
        print(str(output.report_md_path))
        if output.approved_artifact_dir is not None:
            print(str(output.approved_artifact_dir))
        return 0

    if args.cmd == 'index':
        try:
            index_path = index_dataset(args.dir, args.out, compute_sha256=bool(args.hash))
        except FileNotFoundError:
            print('目录不存在。', file=sys.stderr)
            return 2
        except NotADirectoryError:
            print('路径不是目录。', file=sys.stderr)
            return 2
        print(str(index_path))
        return 0

    if args.cmd == 'audit-dataset':
        try:
            cmd_str = (args.dwg_converter or '').strip() or os.environ.get('SPARKFLOW_DWG2DXF_CMD', '').strip()
            dwg_cmd = _parse_dwg_converter_cmd(cmd_str)
            model_options = _build_model_options(args)
            output = audit_dataset(
                args.dir,
                args.out,
                ruleset_dir=(args.ruleset if args.ruleset else None),
                compute_sha256=bool(args.hash),
                dwg_backend=args.dwg_backend,
                dwg_converter_cmd=dwg_cmd,
                dwg_timeout_sec=args.dwg_timeout,
                dxf_backend=args.dxf_backend,
                level=args.level,
                topology_tol=args.topo_tol,
                model_options=model_options,
                workers=args.workers,
                selection=args.selection,
                graph=args.graph,
            )
        except FileNotFoundError:
            print('目录不存在。', file=sys.stderr)
            return 2
        except NotADirectoryError:
            print('路径不是目录。', file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(str(output.run_dir))
        print(str(output.index_json_path))
        print(str(output.run_dir / 'dataset_selection.json'))
        print(str(output.summary_json_path))
        print(str(output.summary_md_path))
        return 0

    if args.cmd == 'dataset-report':
        try:
            artifacts = write_dataset_audit_report(
                args.run_dir,
                ruleset_dir=(args.ruleset if args.ruleset else None),
                out_md=args.out_md,
                out_docx=args.out_docx,
                title=(args.title or None),
                dataset_label=(args.dataset_label or None),
            )
        except FileNotFoundError:
            print('数据集审图运行目录或必要 JSON 不存在。', file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(str(artifacts.markdown_path))
        print(str(artifacts.docx_path))
        return 0

    if args.cmd == 'rectification-checklist':
        try:
            artifacts = write_rectification_checklist(
                args.run_dir,
                out_md=args.out_md,
                out_docx=args.out_docx,
                out_json=args.out_json,
                title=(args.title or None),
                dataset_label=(args.dataset_label or None),
            )
        except FileNotFoundError:
            print('数据集审图运行目录或必要 JSON 不存在。', file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(str(artifacts.markdown_path))
        print(str(artifacts.docx_path))
        print(str(artifacts.json_path))
        return 0

    if args.cmd == 'ruleset-diff':
        try:
            artifact_paths = write_ruleset_diff_artifacts(args.left, args.right, args.out)
        except FileNotFoundError:
            print('规则集输入不存在。', file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(str(artifact_paths.json_path))
        print(str(artifact_paths.markdown_path))
        return 0

    if args.cmd == 'drawing-info':
        try:
            cmd_str = (args.dwg_converter or '').strip() or os.environ.get('SPARKFLOW_DWG2DXF_CMD', '').strip()
            dwg_cmd = _parse_dwg_converter_cmd(cmd_str)
            output_path = write_drawing_info(
                args.path,
                args.out,
                parse_options=CadParseOptions(
                    dwg_backend=args.dwg_backend,
                    dwg_converter_cmd=dwg_cmd,
                    dwg_timeout_sec=args.dwg_timeout,
                    dxf_backend=args.dxf_backend,
                    topology_tol=args.topo_tol,
                ),
            )
        except FileNotFoundError:
            print('文件不存在。', file=sys.stderr)
            return 2
        except UnsupportedCadFormatError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except CadParseError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print(str(output_path))
        return 0

    if args.cmd == 'review-audit':
        try:
            cmd_str = (args.dwg_converter or '').strip() or os.environ.get('SPARKFLOW_DWG2DXF_CMD', '').strip()
            dwg_cmd = _parse_dwg_converter_cmd(cmd_str)
            model_options = _build_model_options(args)
            output = review_audit(
                args.path,
                args.review_dir,
                args.out,
                project_code=(args.project_code or None),
                parse_options=CadParseOptions(
                    dwg_backend=args.dwg_backend,
                    dwg_converter_cmd=dwg_cmd,
                    dwg_timeout_sec=args.dwg_timeout,
                    dxf_backend=args.dxf_backend,
                    topology_tol=args.topo_tol,
                ),
                level=args.level,
                model_options=model_options,
                ruleset_dir=(args.ruleset if args.ruleset else None),
                selection_mode=args.selection,
                graph=args.graph,
                include_sparkflow_audit=not bool(args.skip_sparkflow_audit),
            )
        except FileNotFoundError:
            print('文件或评审意见目录不存在。', file=sys.stderr)
            return 2
        except NotADirectoryError:
            print('评审意见路径不是目录。', file=sys.stderr)
            return 2
        except UnsupportedCadFormatError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except CadParseError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print(str(output.run_dir))
        print(str(output.review_report_json_path))
        print(str(output.review_report_md_path))
        print(str(output.drawing_info_json_path))
        print(str(output.review_rules_json_path))
        if output.sparkflow_report_json_path is not None:
            print(str(output.sparkflow_report_json_path))
        if output.sparkflow_report_md_path is not None:
            print(str(output.sparkflow_report_md_path))
        return 0

    if args.cmd == 'review-pipeline':
        try:
            cmd_str = (args.dwg_converter or '').strip() or os.environ.get('SPARKFLOW_DWG2DXF_CMD', '').strip()
            dwg_cmd = _parse_dwg_converter_cmd(cmd_str)
            model_options = _build_model_options(args)
            output = review_pipeline(
                args.path,
                args.review_dir,
                args.out,
                project_code=(args.project_code or None),
                parse_options=CadParseOptions(
                    dwg_backend=args.dwg_backend,
                    dwg_converter_cmd=dwg_cmd,
                    dwg_timeout_sec=args.dwg_timeout,
                    dxf_backend=args.dxf_backend,
                    topology_tol=args.topo_tol,
                ),
                level=args.level,
                model_options=model_options,
                ruleset_dir=(args.ruleset if args.ruleset else None),
                selection_mode=args.selection,
                graph=args.graph,
                include_sparkflow_audit=not bool(args.skip_sparkflow_audit),
            )
        except FileNotFoundError:
            print('文件或评审意见目录不存在。', file=sys.stderr)
            return 2
        except NotADirectoryError:
            print('评审意见路径不是目录。', file=sys.stderr)
            return 2
        except UnsupportedCadFormatError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except CadParseError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print(str(output.run_dir))
        print(str(output.rectification_checklist_md_path))
        print(str(output.rectification_checklist_json_path))
        print(str(output.split_manifest_json_path))
        print(str(output.review_report_json_path))
        return 0

    if args.cmd == 'serve':
        run_server(host=args.host, port=args.port)
        return 0

    return 2


def _build_model_options(args) -> object:
    model_cfg = {}
    if (
        args.wire_layer_include is not None
        or args.wire_layer_exclude is not None
        or args.wire_ltype_include is not None
        or args.wire_ltype_exclude is not None
        or args.wire_min_length is not None
    ):
        model_cfg['wire_filter'] = {
            'include_layers': args.wire_layer_include or [],
            'exclude_layers': args.wire_layer_exclude or [],
            'include_linetypes': args.wire_ltype_include or [],
            'exclude_linetypes': args.wire_ltype_exclude or [],
            'min_length': args.wire_min_length or 0.0,
        }
    return model_build_options_from_dict(model_cfg) if model_cfg else None


def _parse_dwg_converter_cmd(raw: str) -> list[str] | None:
    cmd_str = (raw or '').strip()
    if not cmd_str:
        return None
    unquoted = cmd_str[1:-1] if len(cmd_str) >= 2 and cmd_str[0] == '"' and cmd_str[-1] == '"' else cmd_str
    candidate = Path(unquoted)
    if candidate.exists():
        return [str(candidate)]
    parsed = shlex.split(cmd_str, posix=False)
    if len(parsed) == 1:
        token = parsed[0]
        if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
            return [token[1:-1]]
    return parsed


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
