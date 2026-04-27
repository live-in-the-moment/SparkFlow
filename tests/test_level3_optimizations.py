from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import ezdxf

from backend.cad.entities import CadEntity
from backend.cad.parse import CadParseOptions, parse_cad
from backend.model.build_options import ModelBuildOptions, TerminalDef, TerminalTemplate, WireFilter
from backend.model.builder import build_system_model
from backend.model.types import Point2D


class Level3OptimizationTests(unittest.TestCase):
    def test_wire_filter_excludes_dim_and_includes_lwpolyline_segments(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.dxf"
            doc = ezdxf.new(setup=True)
            msp = doc.modelspace()
            msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "DIM"})
            msp.add_line((0, 0), (0, 10), dxfattribs={"layer": "WIRE"})
            msp.add_lwpolyline([(0, 0), (5, 0), (5, 5)], dxfattribs={"layer": "WIRE"})
            msp.add_polyline2d([(0, 0), (0, 5), (5, 5)], dxfattribs={"layer": "WIRE"})
            doc.saveas(path)

            parsed = parse_cad(path, options=CadParseOptions(dxf_backend="ezdxf"))
            model = build_system_model(
                parsed.entities,
                options=ModelBuildOptions(wire_filter=WireFilter(exclude_layers=("DIM",))),
            )

            self.assertEqual(len(model.wires), 5)

    def test_terminal_template_applies_rotation(self) -> None:
        insert = CadEntity(
            entity_id="1",
            kind="INSERT",
            props={
                "gc_10": "100",
                "gc_20": "100",
                "gc_2": "BKR",
                "gc_50": "90",
                "gc_41": "1",
                "gc_42": "1",
            },
        )
        tpl = TerminalTemplate(
            block_name="BKR",
            match_mode="equals",
            terminals=(
                TerminalDef(name="a", x=0.0, y=0.0),
                TerminalDef(name="b", x=10.0, y=0.0),
            ),
            attrib_equals=None,
        )
        model = build_system_model((insert,), options=ModelBuildOptions(terminal_templates=(tpl,)))
        self.assertEqual(len(model.devices), 1)
        dev = model.devices[0]
        self.assertEqual(len(dev.terminals), 2)
        p0 = dev.terminals[0].position
        p1 = dev.terminals[1].position
        self.assertAlmostEqual(p0.x, 100.0, places=6)
        self.assertAlmostEqual(p0.y, 100.0, places=6)
        self.assertAlmostEqual(p1.x, 100.0, places=6)
        self.assertAlmostEqual(p1.y, 110.0, places=6)


if __name__ == "__main__":
    unittest.main()
