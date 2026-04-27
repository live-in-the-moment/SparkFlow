from __future__ import annotations

import unittest

from backend.cad.entities import CadEntity
from backend.model.build_options import (
    DeviceTemplate,
    ModelBuildOptions,
    TerminalDef,
    WireFilter,
    default_model_build_options,
)
from backend.model.builder import build_system_model


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
        self.assertEqual(len(model.wires), 0)

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

    def test_table_context_switchgear_label_near_wires_is_recognized(self) -> None:
        entities = (
            CadEntity(entity_id='h1', kind='TEXT', props={'gc_1': '序号', 'gc_10': '0', 'gc_20': '20'}),
            CadEntity(entity_id='h2', kind='TEXT', props={'gc_1': '名称', 'gc_10': '20', 'gc_20': '20'}),
            CadEntity(entity_id='h3', kind='TEXT', props={'gc_1': '数量', 'gc_10': '40', 'gc_20': '20'}),
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '出 线 柜', 'gc_10': '20', 'gc_20': '0'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '8', 'gc_20': '0', 'gc_11': '18', 'gc_21': '0'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '22', 'gc_20': '0', 'gc_11': '32', 'gc_21': '0'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertTrue(any(device.device_type == 'switchgear_unit' for device in model.devices))
        self.assertTrue(any((device.label or '') == '出线柜' for device in model.devices))

    def test_df_equipment_code_title_can_materialize_branch_box(self) -> None:
        entities = (
            CadEntity(entity_id='h1', kind='TEXT', props={'gc_1': '序号', 'gc_10': '0', 'gc_20': '20'}),
            CadEntity(entity_id='h2', kind='TEXT', props={'gc_1': '名称', 'gc_10': '20', 'gc_20': '20'}),
            CadEntity(entity_id='h3', kind='TEXT', props={'gc_1': '数量', 'gc_10': '40', 'gc_20': '20'}),
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': 'DF-2一次系统', 'gc_10': '20', 'gc_20': '0'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        branch_boxes = [device for device in model.devices if device.device_type == 'cable_branch_box']
        self.assertEqual(len(branch_boxes), 1)
        self.assertEqual(len(branch_boxes[0].terminals), 0)

    def test_descriptive_switchgear_title_is_not_recognized(self) -> None:
        entities = (
            CadEntity(entity_id='h1', kind='TEXT', props={'gc_1': '图12-1：低压综合配电箱电气系统图', 'gc_10': '20', 'gc_20': '0'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '10', 'gc_20': '0', 'gc_11': '30', 'gc_21': '0'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertEqual(len(model.devices), 0)

    def test_auxiliary_insert_switchgear_without_label_is_ignored(self) -> None:
        entities = (
            CadEntity(entity_id='ins1', kind='INSERT', props={'gc_10': '0', 'gc_20': '0', 'gc_2': 'DP-BOX'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '-6', 'gc_20': '0', 'gc_11': '6', 'gc_21': '0'}),
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '图12-3 低压综合配电箱布置图', 'gc_10': '30', 'gc_20': '0'}),
            CadEntity(entity_id='t2', kind='TEXT', props={'gc_1': '0', 'gc_10': '-10', 'gc_20': '14'}),
            CadEntity(entity_id='t3', kind='TEXT', props={'gc_1': 'a', 'gc_10': '0', 'gc_20': '14'}),
            CadEntity(entity_id='t4', kind='TEXT', props={'gc_1': 'b', 'gc_10': '10', 'gc_20': '14'}),
            CadEntity(entity_id='t5', kind='TEXT', props={'gc_1': 'c', 'gc_10': '20', 'gc_20': '14'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertFalse(any(device.device_type == 'switchgear_unit' for device in model.devices))

    def test_breaker_code_labels_are_not_merged_into_one_device(self) -> None:
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '1QF', 'gc_10': '0', 'gc_20': '0'}),
            CadEntity(entity_id='t2', kind='TEXT', props={'gc_1': '2QF~3QF', 'gc_10': '7', 'gc_20': '0'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '-8', 'gc_20': '0', 'gc_11': '-2', 'gc_21': '0'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '2', 'gc_20': '0', 'gc_11': '8', 'gc_21': '0'}),
            CadEntity(entity_id='w3', kind='LINE', props={'gc_10': '0', 'gc_20': '-8', 'gc_11': '0', 'gc_21': '-2'}),
            CadEntity(entity_id='w4', kind='LINE', props={'gc_10': '0', 'gc_20': '2', 'gc_11': '0', 'gc_21': '8'}),
            CadEntity(entity_id='w5', kind='LINE', props={'gc_10': '5', 'gc_20': '-8', 'gc_11': '5', 'gc_21': '-2'}),
            CadEntity(entity_id='w6', kind='LINE', props={'gc_10': '5', 'gc_20': '2', 'gc_11': '5', 'gc_21': '8'}),
        )
        options = ModelBuildOptions(
            wire_filter=WireFilter(min_length=0.1),
            device_templates=(
                DeviceTemplate(
                    device_type='breaker',
                    label_globs=('*QF*',),
                    footprint_radius=8.0,
                    min_terminals=2,
                    max_terminals=2,
                    text_group_radius=8.0,
                    terminal_layout='vertical',
                ),
            ),
        )

        model = build_system_model(entities, options=options)

        breakers = [device for device in model.devices if device.device_type == 'breaker']
        self.assertEqual(len(breakers), 2)
        normalized = sorted((device.label or '').replace(' ', '').replace('~', '') for device in breakers)
        self.assertEqual(normalized, ['1QF', '2QF3QF'])

    def test_single_letter_c_is_not_recognized_as_load(self) -> None:
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': 'c', 'gc_10': '0', 'gc_20': '0'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertEqual(len(model.devices), 0)

    def test_connection_instruction_text_is_not_recognized_as_load(self) -> None:
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '与避雷器安装横担连接', 'gc_10': '0', 'gc_20': '0'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertEqual(len(model.devices), 0)

    def test_current_rating_text_can_materialize_breaker_with_terminals(self) -> None:
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '630A', 'gc_10': '0', 'gc_20': '0'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '-2', 'gc_20': '-18', 'gc_11': '-2', 'gc_21': '-4'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '-2', 'gc_20': '4', 'gc_11': '-2', 'gc_21': '18'}),
            CadEntity(entity_id='w3', kind='LINE', props={'gc_10': '2', 'gc_20': '-18', 'gc_11': '2', 'gc_21': '-4'}),
            CadEntity(entity_id='w4', kind='LINE', props={'gc_10': '2', 'gc_20': '4', 'gc_11': '2', 'gc_21': '18'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        breakers = [device for device in model.devices if device.device_type == 'breaker']
        self.assertEqual(len(breakers), 1)
        self.assertEqual((breakers[0].label or ''), '630A')
        self.assertEqual(len(breakers[0].terminals), 2)

    def test_current_rating_breaker_can_attach_transformer_and_busbar_context(self) -> None:
        options = ModelBuildOptions(
            wire_filter=WireFilter(
                min_length=0.1,
                exclude_internal_device_wires=False,
                exclude_text_dense_wires=False,
            ),
            device_templates=default_model_build_options().device_templates
            + (
                DeviceTemplate(
                    device_type='transformer',
                    block_name='TR*',
                    match_mode='glob',
                    terminals=(
                        TerminalDef(name='hv', x=-12.0, y=0.0),
                        TerminalDef(name='lv', x=12.0, y=0.0),
                    ),
                    footprint_radius=18.0,
                    min_terminals=2,
                    max_terminals=2,
                ),
                DeviceTemplate(
                    device_type='busbar',
                    block_name='BUS*',
                    match_mode='glob',
                    terminals=(
                        TerminalDef(name='left', x=-12.0, y=0.0),
                        TerminalDef(name='right', x=12.0, y=0.0),
                    ),
                    footprint_radius=18.0,
                    min_terminals=2,
                    max_terminals=2,
                ),
            ),
        )
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '630A', 'gc_10': '0', 'gc_20': '0'}),
            CadEntity(entity_id='t2', kind='TEXT', props={'gc_1': '1#主变', 'gc_10': '-40', 'gc_20': '2'}),
            CadEntity(entity_id='t3', kind='TEXT', props={'gc_1': '10kV母线I段', 'gc_10': '40', 'gc_20': '2'}),
            CadEntity(entity_id='ins1', kind='INSERT', props={'gc_10': '-40', 'gc_20': '0', 'gc_2': 'TR_MAIN'}),
            CadEntity(entity_id='ins2', kind='INSERT', props={'gc_10': '40', 'gc_20': '0', 'gc_2': 'BUS_MAIN'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '-2', 'gc_20': '-18', 'gc_11': '-2', 'gc_21': '-4'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '-2', 'gc_20': '4', 'gc_11': '-2', 'gc_21': '18'}),
            CadEntity(entity_id='w3', kind='LINE', props={'gc_10': '2', 'gc_20': '-18', 'gc_11': '2', 'gc_21': '-4'}),
            CadEntity(entity_id='w4', kind='LINE', props={'gc_10': '2', 'gc_20': '4', 'gc_11': '2', 'gc_21': '18'}),
        )

        model = build_system_model(entities, options=options)

        breaker = next(device for device in model.devices if device.device_type == 'breaker' and (device.label or '') == '630A')
        self.assertEqual(len(breaker.terminals), 2)
        xs = sorted(round(terminal.position.x, 1) for terminal in breaker.terminals)
        self.assertLess(xs[0], -20.0)
        self.assertGreater(xs[1], 20.0)

    def test_incoming_switchgear_text_can_attach_transformer_and_busbar_context(self) -> None:
        options = ModelBuildOptions(
            wire_filter=WireFilter(min_length=0.1),
            device_templates=(
                DeviceTemplate(
                    device_type='switchgear_unit',
                    text_keywords=('进线总柜',),
                    footprint_radius=12.0,
                    min_terminals=2,
                    max_terminals=4,
                    text_group_radius=8.0,
                ),
                DeviceTemplate(
                    device_type='transformer',
                    block_name='TR*',
                    match_mode='glob',
                    terminals=(
                        TerminalDef(name='hv', x=-12.0, y=0.0),
                        TerminalDef(name='lv', x=12.0, y=0.0),
                    ),
                    footprint_radius=18.0,
                    min_terminals=2,
                    max_terminals=2,
                ),
                DeviceTemplate(
                    device_type='busbar',
                    block_name='BUS*',
                    match_mode='glob',
                    terminals=(
                        TerminalDef(name='left', x=-12.0, y=0.0),
                        TerminalDef(name='right', x=12.0, y=0.0),
                    ),
                    footprint_radius=18.0,
                    min_terminals=2,
                    max_terminals=2,
                ),
            ),
        )
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '1#进线总柜', 'gc_10': '0', 'gc_20': '0'}),
            CadEntity(entity_id='t2', kind='TEXT', props={'gc_1': '1#主变', 'gc_10': '-40', 'gc_20': '2'}),
            CadEntity(entity_id='t3', kind='TEXT', props={'gc_1': '0.4kV母线I段', 'gc_10': '40', 'gc_20': '2'}),
            CadEntity(entity_id='ins1', kind='INSERT', props={'gc_10': '-40', 'gc_20': '0', 'gc_2': 'TR_MAIN'}),
            CadEntity(entity_id='ins2', kind='INSERT', props={'gc_10': '40', 'gc_20': '0', 'gc_2': 'BUS_MAIN'}),
        )

        model = build_system_model(entities, options=options)

        switchgears = [device for device in model.devices if device.device_type == 'switchgear_unit']
        self.assertEqual(len(switchgears), 1)
        self.assertEqual(switchgears[0].label, '1#进线总柜')
        self.assertGreaterEqual(len(switchgears[0].terminals), 2)
        xs = sorted(round(terminal.position.x, 1) for terminal in switchgears[0].terminals)
        self.assertLess(xs[0], -10.0)
        self.assertGreater(xs[1], 10.0)

    def test_current_rating_breaker_can_infer_proxy_incoming_switchgear_from_context(self) -> None:
        options = ModelBuildOptions(
            wire_filter=WireFilter(
                min_length=0.1,
                exclude_internal_device_wires=False,
                exclude_text_dense_wires=False,
            ),
            device_templates=default_model_build_options().device_templates
            + (
                DeviceTemplate(
                    device_type='transformer',
                    block_name='TR*',
                    match_mode='glob',
                    terminals=(
                        TerminalDef(name='hv', x=-12.0, y=0.0),
                        TerminalDef(name='lv', x=12.0, y=0.0),
                    ),
                    footprint_radius=18.0,
                    min_terminals=2,
                    max_terminals=2,
                ),
                DeviceTemplate(
                    device_type='busbar',
                    block_name='BUS*',
                    match_mode='glob',
                    terminals=(
                        TerminalDef(name='left', x=-12.0, y=0.0),
                        TerminalDef(name='right', x=12.0, y=0.0),
                    ),
                    footprint_radius=18.0,
                    min_terminals=2,
                    max_terminals=2,
                ),
            ),
        )
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '630A', 'gc_10': '0', 'gc_20': '0'}),
            CadEntity(entity_id='t2', kind='TEXT', props={'gc_1': '1#主变', 'gc_10': '-40', 'gc_20': '2'}),
            CadEntity(entity_id='t3', kind='TEXT', props={'gc_1': '10kV母线I段', 'gc_10': '40', 'gc_20': '2'}),
            CadEntity(entity_id='ins1', kind='INSERT', props={'gc_10': '-40', 'gc_20': '0', 'gc_2': 'TR_MAIN'}),
            CadEntity(entity_id='ins2', kind='INSERT', props={'gc_10': '40', 'gc_20': '0', 'gc_2': 'BUS_MAIN'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '-2', 'gc_20': '-18', 'gc_11': '-2', 'gc_21': '-4'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '-2', 'gc_20': '4', 'gc_11': '-2', 'gc_21': '18'}),
            CadEntity(entity_id='w3', kind='LINE', props={'gc_10': '2', 'gc_20': '-18', 'gc_11': '2', 'gc_21': '-4'}),
            CadEntity(entity_id='w4', kind='LINE', props={'gc_10': '2', 'gc_20': '4', 'gc_11': '2', 'gc_21': '18'}),
        )

        model = build_system_model(entities, options=options)

        switchgears = [device for device in model.devices if device.device_type == 'switchgear_unit']
        self.assertTrue(any((device.label or '') == '1#进线柜' for device in switchgears))
        proxy = next(device for device in switchgears if (device.label or '') == '1#进线柜')
        self.assertTrue(proxy.id.startswith('proxy:'))
        self.assertEqual(len(proxy.terminals), 2)

    def test_outgoing_switchgear_text_can_attach_busbar_and_downstream_context(self) -> None:
        options = ModelBuildOptions(
            wire_filter=WireFilter(min_length=0.1),
            device_templates=(
                DeviceTemplate(
                    device_type='switchgear_unit',
                    text_keywords=('出线柜',),
                    footprint_radius=12.0,
                    min_terminals=2,
                    max_terminals=4,
                    text_group_radius=8.0,
                ),
                DeviceTemplate(
                    device_type='breaker',
                    block_name='BKR*',
                    match_mode='glob',
                    terminals=(
                        TerminalDef(name='left', x=-12.0, y=0.0),
                        TerminalDef(name='right', x=12.0, y=0.0),
                    ),
                    footprint_radius=18.0,
                    min_terminals=2,
                    max_terminals=2,
                ),
                DeviceTemplate(
                    device_type='busbar',
                    block_name='BUS*',
                    match_mode='glob',
                    terminals=(
                        TerminalDef(name='left', x=-12.0, y=0.0),
                        TerminalDef(name='right', x=12.0, y=0.0),
                    ),
                    footprint_radius=18.0,
                    min_terminals=2,
                    max_terminals=2,
                ),
            ),
        )
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '出线柜', 'gc_10': '0', 'gc_20': '0'}),
            CadEntity(entity_id='ins1', kind='INSERT', props={'gc_10': '-40', 'gc_20': '0', 'gc_2': 'BUS_MAIN'}),
            CadEntity(entity_id='ins2', kind='INSERT', props={'gc_10': '40', 'gc_20': '0', 'gc_2': 'BKR_MAIN'}),
        )

        model = build_system_model(entities, options=options)

        switchgear = next(device for device in model.devices if device.device_type == 'switchgear_unit')
        self.assertEqual(switchgear.label, '出线柜')
        self.assertEqual(len(switchgear.terminals), 2)
        xs = sorted(round(terminal.position.x, 1) for terminal in switchgear.terminals)
        self.assertLess(xs[0], -20.0)
        self.assertGreater(xs[1], 20.0)

    def test_branch_box_can_infer_global_terminals_from_parallel_wires(self) -> None:
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': 'DF-2一次系统', 'gc_10': '20', 'gc_20': '30'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '0', 'gc_20': '-12', 'gc_11': '60', 'gc_21': '-12'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '0', 'gc_20': '-4', 'gc_11': '60', 'gc_21': '-4'}),
            CadEntity(entity_id='w3', kind='LINE', props={'gc_10': '0', 'gc_20': '4', 'gc_11': '60', 'gc_21': '4'}),
            CadEntity(entity_id='w4', kind='LINE', props={'gc_10': '0', 'gc_20': '12', 'gc_11': '60', 'gc_21': '12'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        branch_boxes = [device for device in model.devices if device.device_type == 'cable_branch_box']
        self.assertEqual(len(branch_boxes), 1)
        self.assertEqual(len(branch_boxes[0].terminals), 4)
        terminal_names = [terminal.name for terminal in branch_boxes[0].terminals]
        self.assertEqual(terminal_names[0], 'feed')
        self.assertIn('branch_a', terminal_names)
        self.assertIn('branch_b', terminal_names)

    def test_branch_box_global_terminal_inference_tolerates_dense_parallel_wire_sets(self) -> None:
        entities = [CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': 'DF-2一次系统', 'gc_10': '20', 'gc_20': '30'})]
        for idx, y in enumerate((-24, -16, -8, 0, 8, 16, 24, 32, 40), start=1):
            entities.append(
                CadEntity(
                    entity_id=f'w{idx}',
                    kind='LINE',
                    props={'gc_10': '0', 'gc_20': str(y), 'gc_11': '60', 'gc_21': str(y)},
                )
            )
        for idx, x in enumerate((0, 20, 40, 60, 80, 100, 120, 140, 160), start=20):
            entities.append(
                CadEntity(
                    entity_id=f'w{idx}',
                    kind='LINE',
                    props={'gc_10': str(x), 'gc_20': '-24', 'gc_11': str(x), 'gc_21': '40'},
                )
            )

        model = build_system_model(tuple(entities), options=default_model_build_options())

        branch_boxes = [device for device in model.devices if device.device_type == 'cable_branch_box']
        self.assertEqual(len(branch_boxes), 1)
        self.assertGreaterEqual(len(branch_boxes[0].terminals), 3)

    def test_text_group_merges_into_nearby_insert_device(self) -> None:
        entities = (
            CadEntity(entity_id='ins1', kind='INSERT', props={'gc_10': '20', 'gc_20': '0', 'gc_2': 'BKR1'}),
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '1QF', 'gc_10': '60', 'gc_20': '0'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        breakers = [device for device in model.devices if device.device_type == 'breaker']
        self.assertEqual(len(breakers), 1)
        self.assertEqual(breakers[0].id, 'dev:ins1')
        self.assertEqual(breakers[0].label, '1QF')

    def test_df2_style_feeder_titles_without_nearby_wires_are_not_materialized(self) -> None:
        entities = (
            CadEntity(entity_id='t1', kind='TEXT', props={'gc_1': '进线', 'gc_10': '0', 'gc_20': '40'}),
            CadEntity(entity_id='t2', kind='TEXT', props={'gc_1': '出线', 'gc_10': '30', 'gc_20': '40'}),
            CadEntity(entity_id='w1', kind='LINE', props={'gc_10': '0', 'gc_20': '0', 'gc_11': '60', 'gc_21': '0'}),
            CadEntity(entity_id='t3', kind='TEXT', props={'gc_1': 'DF-2一次系统', 'gc_10': '20', 'gc_20': '60'}),
            CadEntity(entity_id='w2', kind='LINE', props={'gc_10': '0', 'gc_20': '-12', 'gc_11': '60', 'gc_21': '-12'}),
            CadEntity(entity_id='w3', kind='LINE', props={'gc_10': '0', 'gc_20': '-4', 'gc_11': '60', 'gc_21': '-4'}),
            CadEntity(entity_id='w4', kind='LINE', props={'gc_10': '0', 'gc_20': '4', 'gc_11': '60', 'gc_21': '4'}),
            CadEntity(entity_id='w5', kind='LINE', props={'gc_10': '0', 'gc_20': '12', 'gc_11': '60', 'gc_21': '12'}),
        )

        model = build_system_model(entities, options=default_model_build_options())

        self.assertFalse(any(device.device_type == 'feeder' for device in model.devices))
        anchor_unresolved = [item for item in model.unresolved if item.kind == 'terminal_anchor' and item.extra.get('device_type') == 'feeder']
        self.assertEqual(anchor_unresolved, [])


if __name__ == '__main__':
    unittest.main()
