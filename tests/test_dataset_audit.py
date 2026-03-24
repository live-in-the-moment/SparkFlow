from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sparkflow.core import audit_dataset


class DatasetAuditTests(unittest.TestCase):
    def test_audit_dataset_counts_processed_skipped_and_unprocessed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dataset = root / 'dataset'
            out = root / 'out'
            ruleset = root / 'ruleset'
            dataset.mkdir(parents=True, exist_ok=True)
            ruleset.mkdir(parents=True, exist_ok=True)

            (ruleset / 'ruleset.json').write_text(
                json.dumps({'version': 't1', 'enabled_rules': [], 'params': {}}, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )

            (dataset / '一次系统图.dxf').write_text(_DXF_OK, encoding='utf-8')
            (dataset / '平面.dwg').write_bytes(b'')
            (dataset / 'x.pdf').write_bytes(b'%PDF-1.4\n%')

            output = audit_dataset(
                dataset,
                out,
                ruleset_dir=ruleset,
                compute_sha256=False,
                dwg_backend='cli',
                dwg_converter_cmd=None,
                dwg_timeout_sec=None,
                dxf_backend='ascii',
                workers=3,
                selection='auto',
                graph='electrical',
            )

            self.assertTrue(output.index_json_path.exists())
            self.assertTrue(output.summary_json_path.exists())
            self.assertTrue((output.run_dir / 'dataset_selection.json').exists())

            summary = json.loads(output.summary_json_path.read_text(encoding='utf-8'))
            self.assertEqual(summary['counts']['passed'], 1)
            self.assertEqual(summary['counts']['failed'], 0)
            self.assertEqual(summary['counts']['skipped'], 1)
            self.assertEqual(summary['counts']['unprocessed'], 1)


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
ENDSEC
0
EOF
"""


if __name__ == '__main__':
    unittest.main()
