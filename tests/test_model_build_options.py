from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.model.build_options import (
    builtin_device_templates,
    default_model_build_options,
    default_terminal_templates,
    load_catalog_model_build_options,
    merge_model_build_options,
    model_build_options_from_dict,
)


class ModelBuildOptionsTests(unittest.TestCase):
    def test_partial_wire_filter_override_preserves_default_filters(self) -> None:
        base = default_model_build_options()
        override = model_build_options_from_dict({'wire_filter': {'min_length': 0.0}})

        merged = merge_model_build_options(base, override)

        assert merged is not None
        assert merged.wire_filter is not None
        self.assertEqual(merged.wire_filter.min_length, 0.0)
        self.assertIn('中心线', merged.wire_filter.exclude_layers)
        self.assertTrue(merged.wire_filter.exclude_internal_device_wires)
        self.assertTrue(merged.wire_filter.exclude_text_dense_wires)

    def test_catalog_loader_ignores_legacy_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            catalog_dir = Path(td)
            (catalog_dir / 'wire_filter.json').write_text(
                json.dumps(
                    {
                        'wire_filter': {
                            'exclude_layers': ['DIM', '中心线'],
                            'min_length': 0.5,
                            'exclude_closed_polylines': True,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            (catalog_dir / 'device_templates.json').write_text(
                json.dumps(
                    {
                        'device_templates': [
                            {
                                'device_type': 'breaker',
                                'block_name': 'BKR*',
                                'match_mode': 'glob',
                                'text_keywords': ['断路器'],
                                'terminals': [
                                    {'name': 'line_in', 'x': -10.0, 'y': 0.0},
                                    {'name': 'line_out', 'x': 10.0, 'y': 0.0},
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            (catalog_dir / 'legacy_defaults.json').write_text(
                json.dumps(
                    {
                        'wire_filter': {
                            'min_length': 999.0,
                        },
                        'device_templates': [
                            {
                                'device_type': 'legacy_component',
                                'text_keywords': ['旧模板'],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )

            loaded = load_catalog_model_build_options(catalog_dir)

            assert loaded is not None
            assert loaded.wire_filter is not None
            self.assertEqual(loaded.wire_filter.min_length, 0.5)
            self.assertEqual(tuple(item.device_type for item in loaded.device_templates), ('breaker',))

    def test_catalog_loader_accepts_utf8_bom_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            catalog_dir = Path(td)
            (catalog_dir / 'wire_filter.json').write_text(
                json.dumps(
                    {
                        'wire_filter': {
                            'exclude_layers': ['DIM', '中心线'],
                            'min_length': 0.25,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8-sig',
            )
            (catalog_dir / 'device_templates.json').write_text(
                json.dumps(
                    {
                        'device_templates': [
                            {
                                'device_type': 'breaker',
                                'block_name': 'BKR*',
                                'match_mode': 'glob',
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8-sig',
            )

            loaded = load_catalog_model_build_options(catalog_dir)

            assert loaded is not None
            assert loaded.wire_filter is not None
            self.assertEqual(loaded.wire_filter.min_length, 0.25)
            self.assertEqual(tuple(item.block_name for item in loaded.device_templates), ('BKR*',))

    def test_embedded_device_template_fallback_stays_in_parity_with_repo_catalog(self) -> None:
        catalog_payload = json.loads(
            (Path(__file__).resolve().parents[1] / "catalog" / "device_templates.json").read_text(encoding="utf-8-sig")
        )
        expected = model_build_options_from_dict(catalog_payload)

        with patch("backend.model.build_options.load_catalog_model_build_options", return_value=None):
            fallback_devices = builtin_device_templates()
            fallback_terminals = default_terminal_templates()

        self.assertTrue(fallback_devices)
        self.assertTrue(fallback_terminals)
        self.assertEqual(fallback_devices, expected.device_templates)
        self.assertEqual(fallback_terminals, expected.terminal_templates)


if __name__ == '__main__':
    unittest.main()
