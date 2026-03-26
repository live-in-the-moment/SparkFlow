from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sparkflow.core import audit_file


class AuditTests(unittest.TestCase):
    def test_audit_pass_generates_approved_artifact_and_new_graph_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / '一次系统图.dxf'
            out = root / 'out'
            dxf.write_text(_DXF_OK, encoding='utf-8')

            result = audit_file(dxf, out)
            self.assertTrue(result.report_json_path.exists())
            self.assertTrue(result.report_md_path.exists())
            self.assertIsNotNone(result.approved_artifact_dir)
            assert result.approved_artifact_dir is not None
            self.assertTrue((result.report_json_path.parent / 'selection.json').exists())
            self.assertTrue((result.report_json_path.parent / 'connectivity.json').exists())
            self.assertTrue((result.report_json_path.parent / 'electrical.json').exists())
            self.assertTrue((result.report_json_path.parent / 'debug_overlay.svg').exists())
            self.assertTrue((result.approved_artifact_dir / dxf.name).exists())

            report = json.loads(result.report_json_path.read_text(encoding='utf-8'))
            self.assertTrue(report['passed'])
            self.assertEqual(report['summary']['classification']['drawing_class'], 'supported_electrical')
            self.assertTrue(report['summary']['connectivity']['enabled'])
            self.assertTrue(report['summary']['electrical']['enabled'])

    def test_audit_fail_no_approved_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / '主接线.dxf'
            out = root / 'out'
            dxf.write_text(_DXF_FLOATING, encoding='utf-8')

            result = audit_file(dxf, out)
            self.assertTrue(result.report_json_path.exists())
            report = json.loads(result.report_json_path.read_text(encoding='utf-8'))
            self.assertFalse(report['passed'])
            self.assertIsNone(result.approved_artifact_dir)

    def test_audit_dwg_without_converter_still_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dwg = root / '电气图.dwg'
            out = root / 'out'
            dwg.write_bytes(b'')

            result = audit_file(dwg, out, level=3)
            self.assertTrue(result.report_json_path.exists())
            self.assertTrue(result.report_md_path.exists())
            self.assertIsNone(result.approved_artifact_dir)

            report = json.loads(result.report_json_path.read_text(encoding='utf-8'))
            self.assertFalse(report['passed'])
            self.assertEqual(report['issues'][0]['rule_id'], 'cad.parse_failed')

    def test_audit_380v_dwg_without_converter_still_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dwg = root / '380V.dwg'
            out = root / 'out'
            dwg.write_bytes(b'')

            result = audit_file(dwg, out, level=3)
            self.assertTrue(result.report_json_path.exists())
            self.assertTrue(result.report_md_path.exists())
            self.assertIsNone(result.approved_artifact_dir)

            report = json.loads(result.report_json_path.read_text(encoding='utf-8'))
            self.assertFalse(report['passed'])
            self.assertEqual(report['issues'][0]['rule_id'], 'cad.parse_failed')


_DXF_OK = """0
SECTION
2
ENTITIES
0
LINE
10
0
20
0
11
10
21
0
0
LINE
10
10
20
0
11
10
21
10
0
LINE
10
10
20
10
11
0
21
0
0
INSERT
10
0
20
0
2
BKR1
0
TEXT
10
0
20
0
1
DEV1
0
ENDSEC
0
EOF
"""

_DXF_FLOATING = """0
SECTION
2
ENTITIES
0
LINE
10
0
20
0
11
10
21
0
0
ENDSEC
0
EOF
"""


if __name__ == '__main__':
    unittest.main()
