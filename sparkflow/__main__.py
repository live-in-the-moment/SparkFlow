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

    args = parser.parse_args(argv)

    if args.cmd == 'audit':
        try:
            cmd_str = (args.dwg_converter or '').strip() or os.environ.get('SPARKFLOW_DWG2DXF_CMD', '').strip()
            dwg_cmd = shlex.split(cmd_str, posix=False) if cmd_str else None
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
            dwg_cmd = shlex.split(cmd_str, posix=False) if cmd_str else None
            model_options = _build_model_options(args)
            outp = audit_dataset(
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
        print(str(outp.run_dir))
        print(str(outp.index_json_path))
        print(str(outp.run_dir / 'dataset_selection.json'))
        print(str(outp.summary_json_path))
        print(str(outp.summary_md_path))
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


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
