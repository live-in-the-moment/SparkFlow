from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.core import audit_file


class Level3TopologyTests(unittest.TestCase):
    def test_level3_writes_connectivity_and_electrical_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / '一次系统图.dxf'
            out = root / 'out'

            dxf.write_text(
                '0\nSECTION\n2\nENTITIES\n'
                '0\nINSERT\n10\n0\n20\n0\n2\nDEV\n'
                '0\nLINE\n10\n0\n20\n0\n11\n10\n21\n0\n'
                '0\nENDSEC\n0\nEOF\n',
                encoding='utf-8',
            )

            result = audit_file(dxf, out, level=3)
            connectivity_path = result.report_json_path.parent / 'connectivity.json'
            electrical_path = result.report_json_path.parent / 'electrical.json'
            debug_svg_path = result.report_json_path.parent / 'debug_overlay.svg'
            self.assertTrue(connectivity_path.exists())
            self.assertTrue(electrical_path.exists())
            self.assertTrue(debug_svg_path.exists())

            report = json.loads(result.report_json_path.read_text(encoding='utf-8'))
            self.assertEqual(report['summary']['classification']['drawing_class'], 'supported_electrical')
            self.assertTrue(report['summary']['connectivity']['enabled'])
            self.assertTrue(report['summary']['electrical']['enabled'])
            self.assertIn('connectivity_json', report['artifacts'])
            self.assertIn('electrical_json', report['artifacts'])
            self.assertIn('debug_svg', report['artifacts'])


if __name__ == '__main__':
    unittest.main()
