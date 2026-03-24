from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sparkflow.cad.parse import CadParseOptions
from sparkflow.core import audit_file


def main() -> int:
    root = Path("image") / "111" / "架空CAD图纸"
    matches = sorted(root.glob("Chapter20*.dxf"))
    if not matches:
        raise FileNotFoundError(str(root / "Chapter20*.dxf"))
    p = matches[0]
    out = audit_file(p, Path("out_chapter20"), parse_options=CadParseOptions(dxf_backend="auto", topology_tol=1.0))
    print(str(out.report_json_path))
    print(str(out.report_md_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
