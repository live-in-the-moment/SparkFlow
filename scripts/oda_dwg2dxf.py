from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="oda_dwg2dxf")
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--oda-exe", type=str, default="")
    ap.add_argument("--outver", type=str, default="ACAD2018")
    ap.add_argument("--audit", type=int, default=1, choices=[0, 1])
    ap.add_argument("--recursive", type=int, default=0, choices=[0, 1])
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args(argv)

    oda = (args.oda_exe or "").strip() or os.environ.get("ODA_FILE_CONVERTER_EXE", "").strip() or "ODAFileConverter"
    oda = _resolve_oda_exe(oda)

    src_dir = Path(tempfile.mkdtemp(prefix="sparkflow_oda_in_"))
    dst_dir = Path(tempfile.mkdtemp(prefix="sparkflow_oda_out_"))
    try:
        inp = args.input.resolve()
        if not inp.exists():
            raise FileNotFoundError(str(inp))
        dst = args.output.resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)

        local_inp = src_dir / "input.dwg"
        shutil.copy2(inp, local_inp)

        cmd = [
            oda,
            str(src_dir),
            str(dst_dir),
            args.outver,
            "DXF",
            str(args.recursive),
            str(args.audit),
            local_inp.name,
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(Path(oda).parent if Path(oda).exists() else Path.cwd()),
            capture_output=True,
            text=True,
            check=False,
            timeout=args.timeout,
        )
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "").strip()
            detail = f": {msg}" if msg else ""
            raise RuntimeError(f"ODAFileConverter 失败（exit={proc.returncode}）{detail}")

        produced = dst_dir / "input.dxf"
        if not produced.exists():
            produced_candidates = [
                p for p in dst_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".dxf"
            ]
            if produced_candidates:
                exact = [p for p in produced_candidates if p.name.lower() == "input.dxf"]
                produced = exact[0] if exact else produced_candidates[0]
            else:
                msg = (proc.stderr or proc.stdout or "").strip()
                detail = f"；converter_output={msg}" if msg else ""
                raise RuntimeError(f"ODAFileConverter 未生成任何 DXF{detail}")

        shutil.copy2(produced, dst)
        if dst.stat().st_size <= 0:
            raise RuntimeError("生成的 DXF 为空文件")
        return 0
    finally:
        shutil.rmtree(src_dir, ignore_errors=True)
        shutil.rmtree(dst_dir, ignore_errors=True)

def _resolve_oda_exe(s: str) -> str:
    p = Path(s)
    if p.exists() and p.is_dir():
        candidates = [
            p / "ODAFileConverter.exe",
            p / "ODAFileConverter",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        exes = sorted(p.glob("*.exe"))
        for c in exes:
            if "ODAFileConverter" in c.name:
                return str(c)
        return s
    return s


if __name__ == "__main__":
    raise SystemExit(main())
