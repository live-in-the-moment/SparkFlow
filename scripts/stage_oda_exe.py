from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    prog_files = os.environ.get("ProgramFiles", "")
    prog_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    extra_roots = [Path(r"D:\Program Files"), Path(r"D:\Program Files (x86)")]

    candidates: list[Path] = []
    for base in [*(Path(x) for x in (prog_files, prog_files_x86) if x), *extra_roots]:
        b = base
        candidates.append(b / "ODA" / "ODAFileConverter 27.1.0" / "ODAFileConverter.exe")
        candidates.append(b / "ODA" / "ODAFileConverter" / "ODAFileConverter.exe")

    found: Path | None = None
    for c in candidates:
        if c.exists():
            found = c
            break

    if found is None:
        for base in [*(Path(x) for x in (prog_files, prog_files_x86) if x), *extra_roots]:
            b = base / "ODA"
            if not b.exists():
                continue
            for p in b.rglob("ODAFileConverter.exe"):
                found = p
                break
            if found is not None:
                break

    if found is None:
        print("NOT_FOUND", file=sys.stderr)
        return 2

    out_dir = Path("out") / "oda"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst_app = out_dir / "ODAFileConverter"
    if dst_app.exists():
        shutil.rmtree(dst_app, ignore_errors=True)
    shutil.copytree(found.parent, dst_app, dirs_exist_ok=True)
    dst = dst_app / found.name
    print(str(dst.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
