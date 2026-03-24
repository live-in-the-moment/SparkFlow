from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sparkflow.core import audit_dataset


def main() -> int:
    root = Path('image') / '国家电网公司380220V配电网工程典型设计（2018年版）_1772430671059'
    oda_exe = Path('out') / 'oda' / 'ODAFileConverter' / 'ODAFileConverter.exe'
    converter_script = (Path(__file__).resolve().parent / 'oda_dwg2dxf.py').resolve()
    if not oda_exe.exists():
        raise SystemExit(f'ODAFileConverter.exe 不存在：{oda_exe}')
    if not root.exists():
        raise SystemExit(f'测试目录不存在：{root}')
    if not converter_script.exists():
        raise SystemExit(f'ODA 转换脚本不存在：{converter_script}')

    os.environ['SPARKFLOW_DWG2DXF_CMD'] = (
        f'"{sys.executable}" "{converter_script}" --oda-exe "{oda_exe.resolve()}" {{in}} {{out}}'
    )
    output = audit_dataset(
        root,
        Path('out_electrical_dataset'),
        ruleset_dir=None,
        compute_sha256=False,
        dwg_backend='cli',
        dwg_converter_cmd=None,
        dwg_timeout_sec=300.0,
        dxf_backend='auto',
        level=3,
        topology_tol=1.0,
        model_options=None,
        workers=3,
        selection='auto',
        graph='electrical',
    )
    print(str(output.run_dir))
    print(str(output.index_json_path))
    print(str(output.run_dir / 'dataset_selection.json'))
    print(str(output.summary_json_path))
    print(str(output.summary_md_path))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
