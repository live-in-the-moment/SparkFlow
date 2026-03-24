from __future__ import annotations

import unittest

from sparkflow.cad.entities import CadEntity
from sparkflow.model.build_options import DeviceTemplate, ModelBuildOptions, TerminalDef, WireFilter
from sparkflow.model.builder import build_system_model


class SymbolRecognitionTests(unittest.TestCase):
    def test_text_keyword_recognition_creates_breaker_with_terminals(self) -> None:
        entities = (
            CadEntity(entity_id='1', kind='TEXT', props={'gc_1': '隔离开关', 'gc_10': '0', 'gc_20': '0'}),
            CadEntity(entity_id='2', kind='LINE', props={'gc_10': '-10', 'gc_20': '0', 'gc_11': '-2', 'gc_21': '0'}),
            CadEntity(entity_id='3', kind='LINE', props={'gc_10': '2', 'gc_20': '0', 'gc_11': '10', 'gc_21': '0'}),
        )
        options = ModelBuildOptions(
            wire_filter=WireFilter(min_length=0.5),
            device_templates=(
                DeviceTemplate(
                    device_type='breaker',
                    text_keywords=('隔离开关',),
                    terminals=(
                        TerminalDef(name='line_in', x=0.0, y=0.0),
                        TerminalDef(name='line_out', x=0.0, y=0.0),
                    ),
                    footprint_radius=6.0,
                    min_terminals=2,
                    max_terminals=2,
                    text_group_radius=6.0,
                ),
            ),
        )

        model = build_system_model(entities, options=options)

        self.assertEqual(len(model.devices), 1)
        device = model.devices[0]
        self.assertEqual(device.device_type, 'breaker')
        self.assertEqual(len(device.terminals), 2)
        self.assertEqual(len(model.wires), 2)

    def test_terminal_inference_prefers_wire_endpoints_over_projected_midpoints(self) -> None:
        entities = (
            CadEntity(entity_id='ins1', kind='INSERT', props={'gc_10': '0', 'gc_20': '0', 'gc_2': 'A$C22066BF2'}),
            CadEntity(entity_id='lbl1', kind='TEXT', props={'gc_1': '1QF', 'gc_10': '1', 'gc_20': '0'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '0', 'gc_20': '-12', 'gc_11': '0', 'gc_21': '-4'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '0', 'gc_20': '4', 'gc_11': '0', 'gc_21': '12'}),
        )
        options = ModelBuildOptions(
            wire_filter=WireFilter(min_length=0.1),
            device_templates=(
                DeviceTemplate(
                    device_type='breaker',
                    block_name='A$C22066BF2',
                    match_mode='equals',
                    label_globs=('*QF*',),
                    footprint_radius=15.0,
                    min_terminals=2,
                    max_terminals=2,
                    text_group_radius=6.0,
                    terminal_layout='vertical',
                ),
            ),
        )
        model = build_system_model(entities, options=options)
        self.assertEqual(len(model.devices), 1)
        terminals = model.devices[0].terminals
        self.assertEqual([(round(t.position.x, 3), round(t.position.y, 3)) for t in terminals], [(0.0, -12.0), (0.0, 12.0)])

    def test_table_context_text_devices_are_ignored(self) -> None:
        entities = (
            CadEntity(entity_id='h1', kind='TEXT', props={'gc_1': '序号', 'gc_10': '0', 'gc_20': '20'}),
            CadEntity(entity_id='h2', kind='TEXT', props={'gc_1': '代号', 'gc_10': '20', 'gc_20': '20'}),
            CadEntity(entity_id='h3', kind='TEXT', props={'gc_1': '名称', 'gc_10': '40', 'gc_20': '20'}),
            CadEntity(entity_id='h4', kind='TEXT', props={'gc_1': '规格及型号', 'gc_10': '60', 'gc_20': '20'}),
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '断路器', 'gc_10': '40', 'gc_20': '0'}),
            CadEntity(entity_id='t2', kind='TEXT', props={'gc_1': '1QF', 'gc_10': '20', 'gc_20': '0'}),
            CadEntity(entity_id='n1', kind='TEXT', props={'gc_1': '1', 'gc_10': '0', 'gc_20': '0'}),
            CadEntity(entity_id='n2', kind='TEXT', props={'gc_1': '630A', 'gc_10': '80', 'gc_20': '0'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '-10', 'gc_20': '0', 'gc_11': '-2', 'gc_21': '0'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '2', 'gc_20': '0', 'gc_11': '10', 'gc_21': '0'}),
        )
        options = ModelBuildOptions(
            wire_filter=WireFilter(min_length=0.1),
            device_templates=(
                DeviceTemplate(
                    device_type='breaker',
                    text_keywords=('断路器',),
                    label_globs=('*QF*',),
                    footprint_radius=8.0,
                    min_terminals=2,
                    max_terminals=2,
                    text_group_radius=8.0,
                ),
            ),
        )
        model = build_system_model(entities, options=options)
        self.assertEqual(len(model.devices), 0)


if __name__ == '__main__':
    unittest.main()
