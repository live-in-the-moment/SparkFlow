from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from backend.__main__ import _parse_dwg_converter_cmd, main


class MainCliTests(unittest.TestCase):
    def test_parse_dwg_converter_cmd_keeps_existing_exe_path_with_spaces_as_single_token(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            exe = Path(td) / 'ODA File Converter.exe'
            exe.write_text('stub', encoding='utf-8')

            parsed = _parse_dwg_converter_cmd(str(exe))

            self.assertEqual(parsed, [str(exe)])

    def test_parse_dwg_converter_cmd_splits_wrapper_command(self) -> None:
        parsed = _parse_dwg_converter_cmd(
            '"python" scripts/oda_dwg2dxf.py --oda-exe "D:\\Program Files\\ODA\\ODAFileConverter.exe" {in} {out}'
        )

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed[0], '"python"')
        self.assertIn('scripts/oda_dwg2dxf.py', parsed)
        self.assertIn('{in}', parsed)
        self.assertIn('{out}', parsed)

    def test_audit_command_returns_validation_error_for_malformed_structured_ruleset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / '电气图.dxf'
            ruleset_dir = root / 'ruleset'
            out = root / 'out'
            ruleset_dir.mkdir(parents=True, exist_ok=True)
            dxf.write_text(_DXF_OK, encoding='utf-8')
            (ruleset_dir / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'invalid_ruleset_v1',
                        'rules': [
                            {
                                'rule_id': 'wire.floating_endpoints',
                                'enabled': 'yes',
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(
                    ['audit', str(dxf), '--out', str(out), '--ruleset', str(ruleset_dir), '--dxf-backend', 'ascii']
                )

            self.assertEqual(exit_code, 2)
            self.assertIn('ruleset.json.rules[0].enabled', stderr.getvalue())

    def test_audit_command_accepts_table_backed_ruleset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / '电气图.dxf'
            ruleset_dir = root / 'ruleset'
            out = root / 'out'
            ruleset_dir.mkdir(parents=True, exist_ok=True)
            dxf.write_text(_DXF_FLOATING, encoding='utf-8')
            (ruleset_dir / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'table_ruleset_cli_v1',
                        'rules_table': 'rules.tsv',
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            (ruleset_dir / 'rules.tsv').write_text(
                'rule_id\tenabled\tseverity\tparams\tapplies_to\n'
                'wire.floating_endpoints\ttrue\twarning\t{"tol": 0.001}\telectrical_schematic\n',
                encoding='utf-8',
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(
                    ['audit', str(dxf), '--out', str(out), '--ruleset', str(ruleset_dir), '--dxf-backend', 'ascii']
                )

            self.assertEqual(exit_code, 0)
            report_json_path = Path(stdout.getvalue().splitlines()[0])
            report_md_path = Path(stdout.getvalue().splitlines()[1])
            report = json.loads(report_json_path.read_text(encoding='utf-8'))
            self.assertEqual(report['rule_version'], 'table_ruleset_cli_v1')
            self.assertTrue(report['passed'])
            self.assertTrue(report['issues'])
            self.assertTrue(all(issue['severity'] == 'warning' for issue in report['issues']))
            rendered_md = report_md_path.read_text(encoding='utf-8')
            self.assertIn('article_clause_mapping', rendered_md)
            self.assertIn('risk_level', rendered_md)
            self.assertIn('confidence', rendered_md)
            self.assertEqual(stderr.getvalue(), '')

    def test_audit_command_accepts_xlsx_backed_ruleset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / '电气图.dxf'
            ruleset_dir = root / 'ruleset'
            out = root / 'out'
            dxf.write_text(_DXF_FLOATING, encoding='utf-8')
            _write_xlsx_ruleset(
                ruleset_dir,
                version='xlsx_ruleset_cli_v1',
                rules=[
                    {
                        'rule_id': 'wire.floating_endpoints',
                        'enabled': True,
                        'severity': 'warning',
                        'params': {'tol': 0.001},
                        'applies_to': ['electrical_schematic'],
                        'title': '导线端点完整性',
                        'clause': 'GB 50303-2015 6.1.1',
                    }
                ],
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(
                    ['audit', str(dxf), '--out', str(out), '--ruleset', str(ruleset_dir), '--dxf-backend', 'ascii']
                )

            self.assertEqual(exit_code, 0)
            report_json_path = Path(stdout.getvalue().splitlines()[0])
            report = json.loads(report_json_path.read_text(encoding='utf-8'))
            self.assertEqual(report['rule_version'], 'xlsx_ruleset_cli_v1')
            self.assertTrue(report['passed'])
            self.assertTrue(report['issues'])
            self.assertTrue(all(issue['severity'] == 'warning' for issue in report['issues']))
            self.assertEqual(stderr.getvalue(), '')

    def test_ruleset_diff_command_writes_json_and_markdown_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            left = root / 'left'
            right = root / 'right'
            out = root / 'artifacts' / 'ruleset_diff.json'
            left.mkdir(parents=True, exist_ok=True)
            right.mkdir(parents=True, exist_ok=True)
            (left / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'left_ruleset_v1',
                        'rules': [
                            {
                                'rule_id': 'wire.floating_endpoints',
                                'enabled': True,
                                'severity': 'warning',
                                'params': {'tol': 0.25},
                                'applies_to': ['single_line'],
                                'title': '旧导线端点标题',
                                'clause': 'GB 50000-2010 3.2.1',
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            (right / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'right_ruleset_v2',
                        'normative_summary': 'normative_summary.md',
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            (right / 'normative_summary.md').write_text(
                '# SparkFlow Normative Summary\n\n'
                '## wire.floating_endpoints\n'
                '- title: 新导线端点标题\n'
                '- clause: GB 50000-2020 5.4.2\n'
                '- enabled: false\n'
                '- severity: error\n'
                '- params: {"tol": 0.5}\n'
                '- applies_to: electrical_schematic\n',
                encoding='utf-8',
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(['ruleset-diff', str(left), str(right), '--out', str(out)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue().splitlines(), [str(out), str(out.with_suffix('.md'))])
            self.assertEqual(stderr.getvalue(), '')
            artifact = json.loads(out.read_text(encoding='utf-8'))
            self.assertTrue(artifact['summary']['version_changed'])
            self.assertEqual(artifact['summary']['changed_rule_count'], 1)
            self.assertEqual(artifact['summary']['enabled_changed'], 1)
            self.assertEqual(artifact['summary']['severity_changed'], 1)
            self.assertEqual(artifact['summary']['params_changed'], 1)
            self.assertEqual(artifact['summary']['applies_to_changed'], 1)
            self.assertEqual(artifact['summary']['title_changed'], 1)
            self.assertEqual(artifact['summary']['clause_changed'], 1)
            self.assertEqual(artifact['rules'][0]['rule_id'], 'wire.floating_endpoints')
            markdown = out.with_suffix('.md').read_text(encoding='utf-8')
            self.assertIn('SparkFlow Ruleset Comparison Report', markdown)
            self.assertIn('wire.floating_endpoints', markdown)
            self.assertIn('title:', markdown)
            self.assertIn('clause:', markdown)


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


def _write_xlsx_ruleset(ruleset_dir: Path, *, version: str, rules: list[dict[str, object]]) -> None:
    ruleset_dir.mkdir(parents=True, exist_ok=True)
    (ruleset_dir / 'ruleset.json').write_text(
        json.dumps(
            {
                'version': version,
                'rules_table': 'rules.xlsx',
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    _write_xlsx_table(ruleset_dir / 'rules.xlsx', rules)


def _write_xlsx_table(table_path: Path, rules: list[dict[str, object]]) -> None:
    headers = ['rule_id', 'enabled', 'severity', 'params', 'applies_to', 'title', 'clause']
    rows = [headers]
    for rule in rules:
        rows.append(
            [
                str(rule['rule_id']),
                'true' if rule.get('enabled', True) else 'false',
                str(rule.get('severity', '') or ''),
                json.dumps(rule.get('params', {}), ensure_ascii=False),
                '|'.join(rule.get('applies_to', [])),
                str(rule.get('title', '') or ''),
                str(rule.get('clause', '') or ''),
            ]
        )

    with zipfile.ZipFile(table_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            '[Content_Types].xml',
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '</Types>'
            ),
        )
        archive.writestr(
            '_rels/.rels',
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="xl/workbook.xml"/>'
                '</Relationships>'
            ),
        )
        archive.writestr(
            'xl/workbook.xml',
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="rules" sheetId="1" r:id="rId1"/></sheets>'
                '</workbook>'
            ),
        )
        archive.writestr(
            'xl/_rels/workbook.xml.rels',
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/>'
                '</Relationships>'
            ),
        )
        archive.writestr('xl/worksheets/sheet1.xml', _render_xlsx_sheet(rows))


def _render_xlsx_sheet(rows: list[list[str]]) -> str:
    rendered_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            cell_ref = f'{_xlsx_column_name(column_index)}{row_index}'
            cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{xml_escape(value)}</t></is></c>')
        rendered_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(rendered_rows)}</sheetData>'
        '</worksheet>'
    )


def _xlsx_column_name(index: int) -> str:
    name = ''
    value = index
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        name = chr(ord('A') + remainder) + name
    return name


if __name__ == '__main__':
    unittest.main()
