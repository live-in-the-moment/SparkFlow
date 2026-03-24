from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_oda_test")
    ap.add_argument("dwg", type=Path)
    args = ap.parse_args(argv)

    exe = Path("out") / "oda" / "ODAFileConverter" / "ODAFileConverter.exe"
    if not exe.exists():
        raise SystemExit("ODAFileConverter.exe 不存在，请先运行 scripts\\stage_oda_exe.py")

    base = Path("out") / "oda_test"
    in_dir = base / "in"
    out_dir = base / "out"
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    src = args.dwg.resolve()
    if not src.exists():
        raise SystemExit("DWG 不存在")

    shutil.copy2(src, in_dir / "input.dwg")

    cmd = [
        str(exe),
        str(in_dir.resolve()),
        str(out_dir.resolve()),
        "ACAD2018",
        "DXF",
        "0",
        "1",
        "input.dwg",
    ]

    proc = subprocess.run(cmd, cwd=str(exe.parent), capture_output=True, text=True, check=False)
    print("returncode=", proc.returncode)
    if proc.stdout:
        print("stdout:")
        print(proc.stdout)
    if proc.stderr:
        print("stderr:")
        print(proc.stderr)

    files = [p for p in out_dir.rglob("*") if p.is_file()]
    print("output_files=", len(files))
    for p in files[:200]:
        print(str(p.relative_to(base)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
