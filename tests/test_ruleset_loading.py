from __future__ import annotations

import csv
import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from sparkflow.core import audit_file
from sparkflow.rules.diffing import build_ruleset_diff
from sparkflow.rules.knowledgebase import load_ruleset_dir
from sparkflow.rules.registry import list_rule_ids


class RulesetLoadingTests(unittest.TestCase):
    def test_repository_example_rulesets_are_semantically_aligned(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        rules_root = repo_root / 'rulesets'
        loaded = {
            name: load_ruleset_dir(rules_root / name)
            for name in ('example', 'example_table', 'example_xlsx', 'example_normative')
        }

        baseline = _normalize_loaded_ruleset(loaded['example'])
        for name in ('example_table', 'example_xlsx', 'example_normative'):
            with self.subTest(name=name):
                self.assertEqual(_normalize_loaded_ruleset(loaded[name]), baseline)

    def test_legacy_ruleset_still_loads_with_params_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ruleset_dir = Path(td)
            (ruleset_dir / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'legacy_ruleset_v1',
                        'enabled_rules': ['wire.floating_endpoints', 'device.missing_label'],
                        'params': {
                            'wire.floating_endpoints': {'tol': 0.25},
                            '_model': {'wire_filter': {'min_length': 1.0}},
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )

            loaded = load_ruleset_dir(ruleset_dir)

            self.assertEqual(loaded.version, 'legacy_ruleset_v1')
            self.assertEqual([binding.rule_id for binding in loaded.rules], ['wire.floating_endpoints', 'device.missing_label'])
            self.assertEqual(loaded.rule_configs[0].params['tol'], 0.25)
            self.assertEqual(loaded.params['_model']['wire_filter']['min_length'], 1.0)

    def test_structured_ruleset_supports_rule_controls_for_existing_rules(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ruleset_dir = Path(td)
            configured_rule_ids = list_rule_ids()[:10]
            rules = []
            for index, rule_id in enumerate(configured_rule_ids):
                entry = {'rule_id': rule_id, 'enabled': True, 'params': {}}
                if rule_id == 'wire.floating_endpoints':
                    entry['severity'] = 'warning'
                    entry['params'] = {'tol': 0.5}
                    entry['applies_to'] = ['single_line']
                if index == 1:
                    entry['enabled'] = False
                rules.append(entry)

            (ruleset_dir / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'structured_ruleset_v1',
                        'model': {'wire_filter': {'min_length': 0.5}},
                        'rules': rules,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )

            loaded = load_ruleset_dir(ruleset_dir)
            binding_by_id = {binding.rule_id: binding for binding in loaded.rules}

            self.assertEqual(loaded.version, 'structured_ruleset_v1')
            self.assertEqual(len(loaded.rule_configs), 10)
            self.assertEqual(sum(1 for config in loaded.rule_configs if config.enabled), 9)
            self.assertEqual(binding_by_id['wire.floating_endpoints'].severity_override.value, 'warning')
            self.assertEqual(binding_by_id['wire.floating_endpoints'].applies_to, ('single_line',))
            self.assertNotIn(configured_rule_ids[1], binding_by_id)
            self.assertEqual(loaded.params['_model']['wire_filter']['min_length'], 0.5)

    def test_structured_ruleset_validation_errors_include_field_paths(self) -> None:
        cases = (
            (
                {'version': 'bad_enabled', 'rules': [{'rule_id': 'wire.floating_endpoints', 'enabled': 'yes'}]},
                'ruleset.json.rules[0].enabled',
            ),
            (
                {'version': 'bad_severity', 'rules': [{'rule_id': 'wire.floating_endpoints', 'severity': 'critical'}]},
                'ruleset.json.rules[0].severity',
            ),
            (
                {'version': 'bad_applies_to', 'rules': [{'rule_id': 'wire.floating_endpoints', 'applies_to': ['diagram']}]},
                'ruleset.json.rules[0].applies_to[0]',
            ),
        )

        for payload, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as td:
                ruleset_dir = Path(td)
                (ruleset_dir / 'ruleset.json').write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding='utf-8',
                )

                with self.assertRaisesRegex(ValueError, re.escape(expected)):
                    load_ruleset_dir(ruleset_dir)

    def test_structured_ruleset_applies_to_can_skip_a_rule_for_other_drawing_types(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / '一次系统图.dxf'
            out = root / 'out'
            ruleset_dir = root / 'ruleset'
            ruleset_dir.mkdir(parents=True, exist_ok=True)
            dxf.write_text(_DXF_FLOATING, encoding='utf-8')
            (ruleset_dir / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'structured_applies_to_v1',
                        'rules': [
                            {
                                'rule_id': 'wire.floating_endpoints',
                                'enabled': True,
                                'params': {'tol': 0.001},
                                'applies_to': ['electrical_schematic'],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )

            baseline = audit_file(dxf, out / 'baseline')
            configured = audit_file(dxf, out / 'configured', ruleset_dir=ruleset_dir)
            baseline_report = json.loads(baseline.report_json_path.read_text(encoding='utf-8'))
            configured_report = json.loads(configured.report_json_path.read_text(encoding='utf-8'))

            self.assertFalse(baseline_report['passed'])
            self.assertEqual(baseline_report['issues'][0]['rule_id'], 'wire.floating_endpoints')
            self.assertTrue(configured_report['passed'])
            self.assertEqual(configured_report['issues'], [])

    def test_structured_ruleset_severity_override_changes_audit_result(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / '电气图.dxf'
            out = root / 'out'
            ruleset_dir = root / 'ruleset'
            ruleset_dir.mkdir(parents=True, exist_ok=True)
            dxf.write_text(_DXF_FLOATING, encoding='utf-8')
            (ruleset_dir / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'structured_severity_v1',
                        'rules': [
                            {
                                'rule_id': 'wire.floating_endpoints',
                                'enabled': True,
                                'severity': 'warning',
                                'params': {'tol': 0.001},
                                'applies_to': ['electrical_schematic'],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )

            baseline = audit_file(dxf, out / 'baseline')
            configured = audit_file(dxf, out / 'configured', ruleset_dir=ruleset_dir)
            baseline_report = json.loads(baseline.report_json_path.read_text(encoding='utf-8'))
            configured_report = json.loads(configured.report_json_path.read_text(encoding='utf-8'))

            self.assertFalse(baseline_report['passed'])
            self.assertTrue(all(issue['severity'] == 'error' for issue in baseline_report['issues']))
            self.assertTrue(configured_report['passed'])
            self.assertTrue(configured_report['issues'])
            self.assertTrue(all(issue['severity'] == 'warning' for issue in configured_report['issues']))

    def test_structured_ruleset_supports_csv_and_tsv_table_entries(self) -> None:
        cases = (
            ('rules.csv', ','),
            ('rules.tsv', '\t'),
        )

        for table_name, delimiter in cases:
            with self.subTest(table_name=table_name), tempfile.TemporaryDirectory() as td:
                ruleset_dir = Path(td)
                _write_table_ruleset(
                    ruleset_dir,
                    version='table_ruleset_v1',
                    table_name=table_name,
                    delimiter=delimiter,
                    model={'wire_filter': {'min_length': 0.5}},
                    rules=[
                        {
                            'rule_id': 'wire.floating_endpoints',
                            'enabled': True,
                            'severity': 'warning',
                            'params': {'tol': 0.5},
                            'applies_to': ['single_line', 'electrical_schematic'],
                        },
                        {
                            'rule_id': 'device.missing_label',
                            'enabled': False,
                            'params': {'radius': 8.0},
                        },
                    ],
                )

                loaded = load_ruleset_dir(ruleset_dir)
                binding_by_id = {binding.rule_id: binding for binding in loaded.rules}

                self.assertEqual(loaded.version, 'table_ruleset_v1')
                self.assertEqual(len(loaded.rule_configs), 2)
                self.assertEqual(binding_by_id['wire.floating_endpoints'].severity_override.value, 'warning')
                self.assertEqual(binding_by_id['wire.floating_endpoints'].applies_to, ('single_line', 'electrical_schematic'))
                self.assertNotIn('device.missing_label', binding_by_id)
                self.assertEqual(loaded.params['device.missing_label']['radius'], 8.0)
                self.assertEqual(loaded.params['_model']['wire_filter']['min_length'], 0.5)

    def test_structured_ruleset_supports_xlsx_table_entries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ruleset_dir = Path(td)
            _write_xlsx_ruleset(
                ruleset_dir,
                version='table_ruleset_xlsx_v1',
                model={'wire_filter': {'min_length': 0.75}},
                rules=[
                    {
                        'rule_id': 'wire.floating_endpoints',
                        'enabled': True,
                        'severity': 'warning',
                        'params': {'tol': 0.5},
                        'applies_to': ['single_line', 'electrical_schematic'],
                        'title': '导线端点完整性',
                        'clause': 'GB 50303-2015 6.1.1',
                    },
                    {
                        'rule_id': 'device.missing_label',
                        'enabled': False,
                        'params': {'radius': 8.0},
                        'title': '设备标签完整性',
                        'clause': 'GB 50303-2015 6.1.2',
                    },
                ],
            )

            loaded = load_ruleset_dir(ruleset_dir)
            binding_by_id = {binding.rule_id: binding for binding in loaded.rules}
            config_by_id = {config.rule_id: config for config in loaded.rule_configs}

            self.assertEqual(loaded.version, 'table_ruleset_xlsx_v1')
            self.assertEqual(len(loaded.rule_configs), 2)
            self.assertEqual(binding_by_id['wire.floating_endpoints'].severity_override.value, 'warning')
            self.assertEqual(binding_by_id['wire.floating_endpoints'].applies_to, ('single_line', 'electrical_schematic'))
            self.assertEqual(config_by_id['wire.floating_endpoints'].title, '导线端点完整性')
            self.assertEqual(config_by_id['wire.floating_endpoints'].clause, 'GB 50303-2015 6.1.1')
            self.assertEqual(config_by_id['device.missing_label'].title, '设备标签完整性')
            self.assertNotIn('device.missing_label', binding_by_id)
            self.assertEqual(loaded.params['device.missing_label']['radius'], 8.0)
            self.assertEqual(loaded.params['_model']['wire_filter']['min_length'], 0.75)

    def test_structured_ruleset_table_validation_errors_include_row_and_field(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ruleset_dir = Path(td)
            ruleset_dir.mkdir(parents=True, exist_ok=True)
            (ruleset_dir / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'bad_table_ruleset_v1',
                        'rules_table': 'rules.tsv',
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            (ruleset_dir / 'rules.tsv').write_text(
                'rule_id\tenabled\tseverity\tparams\tapplies_to\n'
                'wire.floating_endpoints\tmaybe\t\t{}\t\n',
                encoding='utf-8',
            )

            with self.assertRaisesRegex(ValueError, re.escape('rules.tsv[row 2].enabled')):
                load_ruleset_dir(ruleset_dir)

    def test_structured_ruleset_supports_normative_summary_import(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ruleset_dir = Path(td)
            ruleset_dir.mkdir(parents=True, exist_ok=True)
            (ruleset_dir / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'normative_summary_v1',
                        'model': {'wire_filter': {'min_length': 0.5}},
                        'normative_summary': 'normative_summary.md',
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            (ruleset_dir / 'normative_summary.md').write_text(
                '# SparkFlow Normative Summary\n\n'
                '## wire.floating_endpoints\n'
                '- title: 导线端点完整性\n'
                '- clause: GB 50303-2015 6.1.1\n'
                '- enabled: true\n'
                '- severity: warning\n'
                '- params: {"tol": 0.5}\n'
                '- applies_to: single_line|electrical_schematic\n\n'
                '## device.missing_label\n'
                '- title: 设备标签完整性\n'
                '- clause: GB 50303-2015 6.1.2\n'
                '- enabled: false\n'
                '- params: {"radius": 8.0}\n'
                '- applies_to: electrical_schematic\n',
                encoding='utf-8',
            )

            loaded = load_ruleset_dir(ruleset_dir)
            binding_by_id = {binding.rule_id: binding for binding in loaded.rules}
            config_by_id = {config.rule_id: config for config in loaded.rule_configs}

            self.assertEqual(loaded.version, 'normative_summary_v1')
            self.assertEqual(len(loaded.rule_configs), 2)
            self.assertEqual(binding_by_id['wire.floating_endpoints'].severity_override.value, 'warning')
            self.assertEqual(binding_by_id['wire.floating_endpoints'].applies_to, ('single_line', 'electrical_schematic'))
            self.assertEqual(config_by_id['wire.floating_endpoints'].title, '导线端点完整性')
            self.assertEqual(config_by_id['wire.floating_endpoints'].clause, 'GB 50303-2015 6.1.1')
            self.assertEqual(config_by_id['device.missing_label'].title, '设备标签完整性')
            self.assertEqual(config_by_id['device.missing_label'].clause, 'GB 50303-2015 6.1.2')
            self.assertNotIn('device.missing_label', binding_by_id)
            self.assertEqual(loaded.params['_model']['wire_filter']['min_length'], 0.5)

    def test_ruleset_diff_reports_field_level_and_metadata_changes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            left_dir = root / 'left'
            right_dir = root / 'right'
            _write_xlsx_ruleset(
                left_dir,
                version='ruleset_left_v1',
                rules=[
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
            )
            right_dir.mkdir(parents=True, exist_ok=True)
            (right_dir / 'ruleset.json').write_text(
                json.dumps(
                    {
                        'version': 'ruleset_right_v2',
                        'normative_summary': 'normative_summary.md',
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            (right_dir / 'normative_summary.md').write_text(
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

            diff = build_ruleset_diff(left_dir, right_dir)

            self.assertTrue(diff['summary']['version_changed'])
            self.assertEqual(diff['summary']['changed_rule_count'], 1)
            self.assertEqual(diff['summary']['enabled_changed'], 1)
            self.assertEqual(diff['summary']['severity_changed'], 1)
            self.assertEqual(diff['summary']['params_changed'], 1)
            self.assertEqual(diff['summary']['applies_to_changed'], 1)
            self.assertEqual(diff['summary']['title_changed'], 1)
            self.assertEqual(diff['summary']['clause_changed'], 1)
            self.assertEqual(diff['rules'][0]['rule_id'], 'wire.floating_endpoints')
            self.assertEqual(diff['rules'][0]['changes']['enabled']['from'], True)
            self.assertEqual(diff['rules'][0]['changes']['enabled']['to'], False)
            self.assertEqual(diff['rules'][0]['changes']['severity']['to'], 'error')
            self.assertEqual(diff['rules'][0]['changes']['params']['to'], {'tol': 0.5})
            self.assertEqual(diff['rules'][0]['changes']['applies_to']['to'], ['electrical_schematic'])
            self.assertEqual(diff['rules'][0]['changes']['title']['from'], '旧导线端点标题')
            self.assertEqual(diff['rules'][0]['changes']['title']['to'], '新导线端点标题')
            self.assertEqual(diff['rules'][0]['changes']['clause']['to'], 'GB 50000-2020 5.4.2')

    def test_json_and_table_rulesets_drive_equivalent_audit_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / '电气图.dxf'
            out = root / 'out'
            json_ruleset_dir = root / 'json_ruleset'
            table_ruleset_dir = root / 'table_ruleset'
            dxf.write_text(_DXF_FLOATING, encoding='utf-8')
            rules = [
                {
                    'rule_id': 'wire.floating_endpoints',
                    'enabled': True,
                    'severity': 'warning',
                    'params': {'tol': 0.001},
                    'applies_to': ['electrical_schematic'],
                }
            ]
            _write_json_ruleset(
                json_ruleset_dir,
                {
                    'version': 'equivalent_ruleset_v1',
                    'rules': rules,
                },
            )
            _write_table_ruleset(table_ruleset_dir, version='equivalent_ruleset_v1', rules=rules)

            json_output = audit_file(dxf, out / 'json', ruleset_dir=json_ruleset_dir)
            table_output = audit_file(dxf, out / 'table', ruleset_dir=table_ruleset_dir)
            json_report = json.loads(json_output.report_json_path.read_text(encoding='utf-8'))
            table_report = json.loads(table_output.report_json_path.read_text(encoding='utf-8'))

            self.assertEqual(json_report['rule_version'], table_report['rule_version'])
            self.assertEqual(json_report['passed'], table_report['passed'])
            self.assertEqual(json_report['issues'], table_report['issues'])
            self.assertEqual(json_report['summary']['classification'], table_report['summary']['classification'])


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


def _write_json_ruleset(ruleset_dir: Path, payload: dict[str, object]) -> None:
    ruleset_dir.mkdir(parents=True, exist_ok=True)
    (ruleset_dir / 'ruleset.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _normalize_loaded_ruleset(loaded) -> dict[str, object]:
    return {
        'params': loaded.params,
        'rules': [
            {
                'rule_id': config.rule_id,
                'enabled': config.enabled,
                'severity': (config.severity.value if config.severity is not None else None),
                'params': config.params,
                'applies_to': list(config.applies_to),
                'title': config.title,
                'clause': config.clause,
            }
            for config in loaded.rule_configs
        ],
    }


def _write_table_ruleset(
    ruleset_dir: Path,
    *,
    version: str,
    rules: list[dict[str, object]],
    table_name: str = 'rules.tsv',
    delimiter: str = '\t',
    model: dict[str, object] | None = None,
) -> None:
    ruleset_dir.mkdir(parents=True, exist_ok=True)
    (ruleset_dir / 'ruleset.json').write_text(
        json.dumps(
            {
                'version': version,
                'model': model or {},
                'rules_table': table_name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    with (ruleset_dir / table_name).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=['rule_id', 'enabled', 'severity', 'params', 'applies_to', 'title', 'clause'],
            delimiter=delimiter,
        )
        writer.writeheader()
        for rule in rules:
            writer.writerow(
                {
                    'rule_id': str(rule['rule_id']),
                    'enabled': 'true' if rule.get('enabled', True) else 'false',
                    'severity': rule.get('severity', '') or '',
                    'params': json.dumps(rule.get('params', {}), ensure_ascii=False),
                    'applies_to': '|'.join(rule.get('applies_to', [])),
                    'title': rule.get('title', '') or '',
                    'clause': rule.get('clause', '') or '',
                }
            )


def _write_xlsx_ruleset(
    ruleset_dir: Path,
    *,
    version: str,
    rules: list[dict[str, object]],
    table_name: str = 'rules.xlsx',
    model: dict[str, object] | None = None,
) -> None:
    ruleset_dir.mkdir(parents=True, exist_ok=True)
    (ruleset_dir / 'ruleset.json').write_text(
        json.dumps(
            {
                'version': version,
                'model': model or {},
                'rules_table': table_name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    _write_xlsx_table(ruleset_dir / table_name, rules)


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
            cells.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{xml_escape(value)}</t></is></c>'
            )
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
