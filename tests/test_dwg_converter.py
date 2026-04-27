from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.cad.dwg_converter import DwgConvertOptions, convert_dwg_to_dxf
from backend.cad.errors import CadParseError


class DwgConverterTests(unittest.TestCase):
    def test_cli_converter_supports_in_out_template(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dwg = root / "a.dwg"
            dwg.write_bytes(b"x")
            work_dir = root / "w"

            seen_cmd: list[str] = []

            def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
                nonlocal seen_cmd
                seen_cmd = list(cmd)
                out_path = Path(seen_cmd[4])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with mock.patch("subprocess.run", side_effect=fake_run):
                dxf = convert_dwg_to_dxf(
                    dwg,
                    options=DwgConvertOptions(
                        converter_cmd=["tool", "-i", "{in}", "-o", "{out}"],
                        work_dir=work_dir,
                    ),
                )

            self.assertTrue(dxf.exists())
            self.assertIn(str(dwg), seen_cmd)
            self.assertIn(str(work_dir / "a.dxf"), seen_cmd)

    def test_cli_converter_timeout_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dwg = root / "a.dwg"
            dwg.write_bytes(b"x")

            def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=1.0)

            with mock.patch("subprocess.run", side_effect=fake_run):
                with self.assertRaises(CadParseError):
                    convert_dwg_to_dxf(
                        dwg,
                        options=DwgConvertOptions(converter_cmd=["tool"], timeout_sec=1.0),
                    )

    def test_oda_file_converter_path_is_invoked_with_directory_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dwg = root / "sample.dwg"
            dwg.write_bytes(b"x")
            work_dir = root / "work"
            seen_cmd: list[str] = []

            def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
                nonlocal seen_cmd
                seen_cmd = list(cmd)
                dst_dir = Path(cmd[2])
                (dst_dir / "input.dxf").write_text("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with mock.patch("subprocess.run", side_effect=fake_run):
                dxf = convert_dwg_to_dxf(
                    dwg,
                    options=DwgConvertOptions(
                        converter_cmd=[r"D:\Program Files\ODA\ODAFileConverter.exe"],
                        work_dir=work_dir,
                        timeout_sec=60.0,
                    ),
                )

            self.assertTrue(dxf.exists())
            self.assertTrue(Path(seen_cmd[1]).name.startswith("sparkflow_oda_"))
            self.assertTrue(Path(seen_cmd[2]).name.startswith("sparkflow_oda_"))
            self.assertEqual(seen_cmd[3], "ACAD2018")
            self.assertEqual(seen_cmd[4], "DXF")
            self.assertEqual(seen_cmd[5], "0")
            self.assertEqual(seen_cmd[6], "1")
            self.assertEqual(seen_cmd[7], "input.dwg")


if __name__ == "__main__":
    unittest.main()
