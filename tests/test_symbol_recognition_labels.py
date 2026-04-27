from __future__ import annotations

import unittest

from backend.model.build_options import DeviceTemplate, ModelBuildOptions, WireFilter
from backend.model.builder import build_system_model
from backend.cad.entities import CadEntity


class SymbolRecognitionLabelTests(unittest.TestCase):
    def test_insert_can_match_label_glob_with_cad_control_codes(self) -> None:
        entities = (
            CadEntity(entity_id='ins1', kind='INSERT', props={'gc_10': '0', 'gc_20': '0', 'gc_2': 'A$C22066BF2'}),
            CadEntity(entity_id='txt1', kind='TEXT', props={'gc_1': '\\T1;1QF', 'gc_10': '1', 'gc_20': '0'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '-10', 'gc_20': '0', 'gc_11': '-2', 'gc_21': '0'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '2', 'gc_20': '0', 'gc_11': '10', 'gc_21': '0'}),
        )
        options = ModelBuildOptions(
            wire_filter=WireFilter(min_length=0.1),
            device_templates=(
                DeviceTemplate(
                    device_type='breaker',
                    block_name='A$C22066BF2',
                    match_mode='equals',
                    label_globs=('*QF*',),
                    footprint_radius=8.0,
                    min_terminals=2,
                    max_terminals=2,
                    text_group_radius=6.0,
                ),
            ),
        )
        model = build_system_model(entities, options=options)
        self.assertEqual(len(model.devices), 1)
        self.assertEqual(model.devices[0].device_type, 'breaker')
        self.assertEqual(model.devices[0].label, '1QF')
        self.assertEqual(len(model.devices[0].terminals), 2)


if __name__ == '__main__':
    unittest.main()
