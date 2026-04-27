from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import ezdxf

from backend.cad.errors import CadParseError
from backend.cad.parse import CadParseOptions, parse_cad
from backend.model.builder import build_system_model


class DxfBackendTests(unittest.TestCase):
    def test_ascii_backend_parses_ascii_dxf(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dxf = Path(td) / "t.dxf"
            dxf.write_text(
                "0\nSECTION\n2\nENTITIES\n0\nLINE\n10\n0\n20\n0\n11\n10\n21\n0\n0\nENDSEC\n0\nEOF\n",
                encoding="utf-8",
            )

            parsed_ascii = parse_cad(dxf, options=CadParseOptions(dxf_backend="ascii"))
            parsed_ezdxf = parse_cad(dxf, options=CadParseOptions(dxf_backend="ezdxf"))
            parsed_auto = parse_cad(dxf, options=CadParseOptions(dxf_backend="auto"))

            self.assertGreater(len(parsed_ascii.entities), 0)
            self.assertGreater(len(parsed_ezdxf.entities), 0)
            self.assertGreater(len(parsed_auto.entities), 0)

            build_system_model(parsed_ascii.entities)
            build_system_model(parsed_ezdxf.entities)
            build_system_model(parsed_auto.entities)
            self.assertEqual(parsed_auto.meta.get("chosen_dxf_backend"), "ascii")

    def test_binary_dxf_requires_ezdxf_or_auto(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dxf = Path(td) / "binary.dxf"
            doc = ezdxf.new(setup=True)
            msp = doc.modelspace()
            msp.add_line((0, 0), (10, 0))
            doc.saveas(dxf, fmt="bin")

            with self.assertRaises(CadParseError):
                parse_cad(dxf, options=CadParseOptions(dxf_backend="ascii"))

            parsed_ezdxf = parse_cad(dxf, options=CadParseOptions(dxf_backend="ezdxf"))
            parsed_auto = parse_cad(dxf, options=CadParseOptions(dxf_backend="auto"))
            self.assertGreater(len(parsed_ezdxf.entities), 0)
            self.assertGreater(len(parsed_auto.entities), 0)
            build_system_model(parsed_ezdxf.entities)
            build_system_model(parsed_auto.entities)
            self.assertEqual(parsed_auto.meta.get("chosen_dxf_backend"), "ezdxf")

    def test_auto_fallback_records_reason_when_quality_is_bad(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dxf = Path(td) / "t_bad.dxf"
            dxf.write_text(
                "0\nSECTION\n2\nENTITIES\n0\nLINE\n10\nfoo\n20\nbar\n11\nbaz\n21\nqux\n0\nENDSEC\n0\nEOF\n",
                encoding="utf-8",
            )
            parsed = parse_cad(dxf, options=CadParseOptions(dxf_backend="auto"))
            self.assertEqual(parsed.meta.get("requested_dxf_backend"), "auto")
            self.assertIn(
                parsed.meta.get("auto_reason"),
                {"ascii_metrics_ok", "ascii_metrics_not_ok_and_ezdxf_failed"},
            )


if __name__ == "__main__":
    unittest.main()
