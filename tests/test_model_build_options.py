from __future__ import annotations

import unittest

from sparkflow.model.build_options import default_model_build_options, merge_model_build_options, model_build_options_from_dict


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


if __name__ == '__main__':
    unittest.main()
