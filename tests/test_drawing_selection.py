from __future__ import annotations

import unittest
from pathlib import Path

from sparkflow.model.selection import classify_drawing


class DrawingSelectionTests(unittest.TestCase):
    def test_keyword_based_selection(self) -> None:
        self.assertEqual(classify_drawing(Path('配电部分CAD/低压开关柜DK-1/主接线.dwg')).drawing_class, 'supported_electrical')
        self.assertEqual(classify_drawing(Path('配电部分CAD/低压综合配电箱/DP-4/电气图-DP-4.dwg')).drawing_class, 'supported_electrical')
        self.assertEqual(classify_drawing(Path('配电部分CAD/低压开关柜DK-1/平面.dwg')).drawing_class, 'geometry_only')
        self.assertEqual(classify_drawing(Path('架空CAD图纸/Chapter20 (380220V金具及绝缘子).dwg')).drawing_class, 'unsupported')

    def test_text_feature_can_demote_parent_dir_match_to_geometry_only(self) -> None:
        selection = classify_drawing(
            Path('电缆CAD图纸/国网低压典设第24章A模块2017-8-18.dwg'),
            texts=['平面图', '电缆直埋穿保护管敷设断面图', '混凝土', '回填土', '排管'],
        )
        self.assertEqual(selection.drawing_class, 'geometry_only')
        self.assertIn('text_geometry', selection.reason)

    def test_text_feature_can_promote_unsupported_path_to_electrical(self) -> None:
        selection = classify_drawing(
            Path('misc/unknown_plan.dxf'),
            texts=['10kV母线I段', '1#主变', '断路器', '所用电'],
        )
        self.assertEqual(selection.drawing_class, 'supported_electrical')
        self.assertIn('text_electrical', selection.reason)

    def test_text_supported_keyword_can_promote_unsupported_path_to_electrical(self) -> None:
        selection = classify_drawing(
            Path('misc/unknown_plan.dxf'),
            texts=['三相380V，60kVA'],
        )
        self.assertEqual(selection.drawing_class, 'supported_electrical')
        self.assertIn('text_supported_keyword', selection.reason)

    def test_real_sample_paths_if_present(self) -> None:
        root = Path('image') / '国家电网公司380220V配电网工程典型设计（2018年版）_1772430671059'
        if not root.exists():
            self.skipTest('sample root missing')
        supported = root / '配电部分CAD' / '电缆分支箱' / '电缆分支箱DF-2' / '一次系统图.dwg'
        geometry = root / '配电部分CAD' / '低压开关柜DK-1' / '平面.dwg'
        if supported.exists():
            self.assertEqual(classify_drawing(supported).drawing_class, 'supported_electrical')
        if geometry.exists():
            self.assertEqual(classify_drawing(geometry).drawing_class, 'geometry_only')


if __name__ == '__main__':
    unittest.main()
