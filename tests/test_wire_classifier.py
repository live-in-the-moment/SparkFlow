from __future__ import annotations

import unittest

from sparkflow.cad.entities import CadEntity
from sparkflow.model.build_options import ModelBuildOptions, TerminalDef, TerminalTemplate, WireFilter, default_model_build_options
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

    def test_short_wire_inside_device_is_filtered_aggressively(self) -> None:
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '出 线 柜', 'gc_10': '0', 'gc_20': '0'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '-4', 'gc_20': '0', 'gc_11': '4', 'gc_21': '0'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '-30', 'gc_20': '0', 'gc_11': '-18', 'gc_21': '0'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertTrue(any(device.device_type == 'switchgear_unit' for device in model.devices))
        self.assertEqual([wire.id for wire in model.wires], ['wire:w2'])

    def test_auxiliary_diagram_wire_is_filtered_by_marker_texts(self) -> None:
        entities = (
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '0', 'gc_20': '0', 'gc_11': '90', 'gc_21': '0'}),
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '图12-5 低压综合配电箱布置图', 'gc_10': '45', 'gc_20': '12'}),
            CadEntity(entity_id='t2', kind='TEXT', props={'gc_1': '0', 'gc_10': '10', 'gc_20': '3'}),
            CadEntity(entity_id='t3', kind='TEXT', props={'gc_1': 'a', 'gc_10': '30', 'gc_20': '3'}),
            CadEntity(entity_id='t4', kind='TEXT', props={'gc_1': 'b', 'gc_10': '50', 'gc_20': '3'}),
            CadEntity(entity_id='t5', kind='TEXT', props={'gc_1': 'c', 'gc_10': '70', 'gc_20': '3'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertEqual(len(model.wires), 0)

    def test_long_table_header_wire_is_filtered_without_electrical_context(self) -> None:
        entities = [CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '0', 'gc_20': '0', 'gc_11': '120', 'gc_21': '0'})]
        headers = ('序号', '代号', '名称', '规格及型号', '数量', '单位', '备注')
        for idx, (header, x) in enumerate(zip(headers, (0, 18, 36, 54, 78, 96, 114)), start=1):
            entities.append(CadEntity(entity_id=f't{idx}', kind='TEXT', props={'gc_1': header, 'gc_10': str(x), 'gc_20': '6'}))

        model = build_system_model(tuple(entities), options=default_model_build_options())

        self.assertEqual(len(model.wires), 0)

    def test_compact_symbol_cluster_wires_are_filtered(self) -> None:
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '所用电', 'gc_10': '60', 'gc_20': '0'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '48', 'gc_20': '-8', 'gc_11': '64', 'gc_21': '-8'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '48', 'gc_20': '8', 'gc_11': '64', 'gc_21': '8'}),
            CadEntity(entity_id='w3', kind='LINE', props={'gc_10': '48', 'gc_20': '-8', 'gc_11': '48', 'gc_21': '8'}),
            CadEntity(entity_id='w4', kind='LINE', props={'gc_10': '64', 'gc_20': '-8', 'gc_11': '64', 'gc_21': '8'}),
            CadEntity(entity_id='w5', kind='LINE', props={'gc_10': '56', 'gc_20': '-8', 'gc_11': '56', 'gc_21': '8'}),
            CadEntity(entity_id='w6', kind='LINE', props={'gc_10': '10', 'gc_20': '0', 'gc_11': '40', 'gc_21': '0'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertEqual([wire.id for wire in model.wires], ['wire:w6'])

    def test_long_parallel_text_band_rows_are_filtered(self) -> None:
        entities: list[CadEntity] = []
        for idx, y in enumerate((0, 8, 16, 24, 32), start=1):
            entities.append(
                CadEntity(
                    entity_id=f'w{idx}',
                    kind='LINE',
                    props={'gc_10': '0', 'gc_20': str(y), 'gc_11': '180', 'gc_21': str(y)},
                )
            )
            for jdx, x in enumerate((10, 50, 90, 130, 170), start=1):
                entities.append(
                    CadEntity(
                        entity_id=f't{idx}_{jdx}',
                        kind='TEXT',
                        props={'gc_1': f'QF{jdx}', 'gc_10': str(x), 'gc_20': str(y)},
                    )
                )

        model = build_system_model(tuple(entities), options=default_model_build_options())

        self.assertEqual(len(model.wires), 0)

    def test_isolated_annotation_wire_is_filtered(self) -> None:
        entities = (
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '0', 'gc_20': '0', 'gc_11': '70', 'gc_21': '0'}),
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '说明：本图采用低压配电箱型式', 'gc_10': '35', 'gc_20': '10'}),
            CadEntity(entity_id='t2', kind='TEXT', props={'gc_1': '进线侧', 'gc_10': '35', 'gc_20': '-10'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertEqual(len(model.wires), 0)

    def test_narrow_symbol_ladder_cluster_is_filtered(self) -> None:
        entities = (
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '0', 'gc_20': '0', 'gc_11': '0', 'gc_21': '150'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '4', 'gc_20': '0', 'gc_11': '4', 'gc_21': '150'}),
            CadEntity(entity_id='w3', kind='LINE', props={'gc_10': '0', 'gc_20': '0', 'gc_11': '4', 'gc_21': '0'}),
            CadEntity(entity_id='w4', kind='LINE', props={'gc_10': '0', 'gc_20': '50', 'gc_11': '4', 'gc_21': '50'}),
            CadEntity(entity_id='w5', kind='LINE', props={'gc_10': '0', 'gc_20': '100', 'gc_11': '4', 'gc_21': '100'}),
            CadEntity(entity_id='w6', kind='LINE', props={'gc_10': '0', 'gc_20': '150', 'gc_11': '4', 'gc_21': '150'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertEqual(len(model.wires), 0)


if __name__ == '__main__':
    unittest.main()
