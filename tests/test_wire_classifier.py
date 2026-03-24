from __future__ import annotations

import unittest

from sparkflow.cad.entities import CadEntity
from sparkflow.model.build_options import ModelBuildOptions, TerminalDef, TerminalTemplate, WireFilter
from sparkflow.model.builder import build_system_model


class WireClassifierTests(unittest.TestCase):
    def test_internal_symbol_wire_is_filtered(self) -> None:
        entities = (
            CadEntity(
                entity_id='ins1',
                kind='INSERT',
                props={'gc_10': '0', 'gc_20': '0', 'gc_2': 'BKR1'},
            ),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '-1', 'gc_20': '0', 'gc_11': '1', 'gc_21': '0'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '10', 'gc_20': '0', 'gc_11': '20', 'gc_21': '0'}),
        )
        options = ModelBuildOptions(
            wire_filter=WireFilter(min_length=0.1, exclude_internal_device_wires=True, device_radius_padding=2.0),
            terminal_templates=(
                TerminalTemplate(
                    block_name='BKR*',
                    match_mode='glob',
                    terminals=(
                        TerminalDef(name='line_in', x=-10.0, y=0.0),
                        TerminalDef(name='line_out', x=10.0, y=0.0),
                    ),
                ),
            ),
        )

        model = build_system_model(entities, options=options)

        self.assertEqual(len(model.devices), 1)
        self.assertEqual(len(model.wires), 1)
        self.assertEqual(model.wires[0].id, 'wire:w2')

    def test_text_dense_table_wire_is_filtered(self) -> None:
        entities = [
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '0', 'gc_20': '0', 'gc_11': '40', 'gc_21': '0'}),
        ]
        for idx, x in enumerate((0, 10, 20, 30, 40), start=1):
            entities.append(CadEntity(entity_id=f't{idx}', kind='TEXT', props={'gc_1': f'T{idx}', 'gc_10': str(x), 'gc_20': '5'}))
        options = ModelBuildOptions(
            wire_filter=WireFilter(
                min_length=0.1,
                exclude_text_dense_wires=True,
                text_density_radius=18.0,
                text_density_threshold=4,
                text_dense_max_length=60.0,
            )
        )
        model = build_system_model(tuple(entities), options=options)
        self.assertEqual(len(model.wires), 0)


if __name__ == '__main__':
    unittest.main()
