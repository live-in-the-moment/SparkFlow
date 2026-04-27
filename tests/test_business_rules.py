from __future__ import annotations

import unittest

from backend.model.types import Device, ElectricalComponent, ElectricalGraph, ElectricalNet, ElectricalTerminal, Point2D, SystemModel
from backend.rules.rules import DeviceLabelPatternInvalidRule, DeviceNeedsNearbyTextRule, DuplicateDeviceLabelRule
from backend.rules.topology_rules import (
    ElectricalBranchBoxInsufficientBranchesRule,
    ElectricalBusbarUnderconnectedRule,
    ElectricalIncomingTransformerBusbarDirectionRule,
    ElectricalSwitchgearFeedChainRule,
    ElectricalSwitchgearRoleConnectionRule,
    ElectricalTieBusbarSegmentConsistencyRule,
    ElectricalTieSwitchgearDualSideRule,
    ElectricalTransformerSameNetRule,
)


class BusinessRuleTests(unittest.TestCase):
    def test_transformer_same_net_rule_flags_shorted_transformer(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='xf1', type='transformer', label='1#主变', terminal_ids=('xf1:t1', 'xf1:t2')),
                ),
                terminals=(
                    ElectricalTerminal(id='xf1:t1', component_id='xf1', role='hv', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='xf1:t2', component_id='xf1', role='lv', x=10, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('xf1:t1', 'xf1:t2'), node_ids=(1, 2)),
                ),
            )
        )

        issues = ElectricalTransformerSameNetRule().run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'electrical.transformer_same_net')

    def test_busbar_underconnected_rule_flags_sparse_busbar(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='bus1', type='busbar', label='0.4kV母线', terminal_ids=('bus1:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=0, y=0, node_id=1),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('bus1:t1',), node_ids=(1,)),
                ),
            )
        )

        issues = ElectricalBusbarUnderconnectedRule(min_connected_terminals=2).run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'electrical.busbar_underconnected')

    def test_branch_box_rule_flags_missing_branches(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(
                        id='df1',
                        type='cable_branch_box',
                        label='DF-1',
                        terminal_ids=('df1:feed', 'df1:branch_a'),
                    ),
                ),
                terminals=(
                    ElectricalTerminal(id='df1:feed', component_id='df1', role='feed', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='df1:branch_a', component_id='df1', role='branch_a', x=10, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('df1:feed',), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('df1:branch_a',), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalBranchBoxInsufficientBranchesRule(min_branch_terminals=2).run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'electrical.branch_box_insufficient_branches')

    def test_label_pattern_rule_flags_invalid_switchgear_label(self) -> None:
        model = SystemModel(
            devices=(
                Device(id='dev1', position=Point2D(0, 0), label='CAB-01', device_type='switchgear_unit'),
            )
        )

        issues = DeviceLabelPatternInvalidRule().run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'device.label_pattern_invalid')

    def test_label_pattern_rule_accepts_normalized_breaker_and_switchgear_unit_labels(self) -> None:
        model = SystemModel(
            devices=(
                Device(id='br1', position=Point2D(0, 0), label='1～2QS', device_type='breaker'),
                Device(id='br2', position=Point2D(5, 0), label='630A', device_type='breaker'),
                Device(id='sg1', position=Point2D(10, 0), label='出 线 单 元', device_type='switchgear_unit'),
                Device(id='xf1', position=Point2D(20, 0), label='电流互感器', device_type='transformer'),
            )
        )

        issues = DeviceLabelPatternInvalidRule().run(model).issues

        self.assertEqual(len(issues), 0)

    def test_duplicate_device_label_rule_ignores_generic_switchgear_labels(self) -> None:
        model = SystemModel(
            devices=(
                Device(id='sg1', position=Point2D(0, 0), label='出 线 柜', device_type='switchgear_unit'),
                Device(id='sg2', position=Point2D(10, 0), label='出线柜', device_type='switchgear_unit'),
            )
        )

        issues = DuplicateDeviceLabelRule().run(model).issues

        self.assertEqual(len(issues), 0)

    def test_duplicate_device_label_rule_flags_same_identifier_after_normalization(self) -> None:
        model = SystemModel(
            devices=(
                Device(id='sg1', position=Point2D(0, 0), label='1# 进 线 总 柜', device_type='switchgear_unit'),
                Device(id='sg2', position=Point2D(10, 0), label='1#进线总柜', device_type='switchgear_unit'),
            )
        )

        issues = DuplicateDeviceLabelRule().run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'device.duplicate_label')

    def test_duplicate_device_label_rule_ignores_far_apart_reused_component_codes(self) -> None:
        model = SystemModel(
            devices=(
                Device(id='br1', position=Point2D(0, 0), label='1QF', device_type='breaker', footprint_radius=18.0),
                Device(id='br2', position=Point2D(400, 0), label='1QF', device_type='breaker', footprint_radius=18.0),
            )
        )

        issues = DuplicateDeviceLabelRule().run(model).issues

        self.assertEqual(len(issues), 0)

    def test_missing_label_rule_skips_devices_that_already_have_labels(self) -> None:
        model = SystemModel(
            devices=(
                Device(id='sg1', position=Point2D(0, 0), label='1#进线总柜', device_type='switchgear_unit'),
            )
        )

        issues = DeviceNeedsNearbyTextRule().run(model).issues

        self.assertEqual(len(issues), 0)

    def test_switchgear_role_connection_rule_flags_outgoing_without_downstream_neighbor(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='sg1', type='switchgear_unit', label='出线柜1', terminal_ids=('sg1:t1', 'sg1:t2')),
                    ElectricalComponent(id='bus1', type='busbar', label='母线', terminal_ids=('bus1:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='sg1:t1', component_id='sg1', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='sg1:t2', component_id='sg1', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=5, y=0, node_id=1),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('sg1:t1', 'bus1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('sg1:t2',), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalSwitchgearRoleConnectionRule().run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'electrical.switchgear_role_connection')

    def test_switchgear_role_connection_rule_accepts_incoming_with_transformer_and_busbar(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='sg1', type='switchgear_unit', label='1#进线总柜', terminal_ids=('sg1:t1', 'sg1:t2')),
                    ElectricalComponent(id='xf1', type='transformer', label='1#主变', terminal_ids=('xf1:t1',)),
                    ElectricalComponent(id='bus1', type='busbar', label='母线', terminal_ids=('bus1:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='sg1:t1', component_id='sg1', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='sg1:t2', component_id='sg1', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='xf1:t1', component_id='xf1', role='lv', x=-5, y=0, node_id=1),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=15, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('sg1:t1', 'xf1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('sg1:t2', 'bus1:t1'), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalSwitchgearRoleConnectionRule().run(model).issues

        self.assertEqual(len(issues), 0)

    def test_switchgear_feed_chain_rule_flags_incoming_without_busbar_link_to_outgoing(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='sg_in', type='switchgear_unit', label='1#进线柜', terminal_ids=('sg_in:t1', 'sg_in:t2')),
                    ElectricalComponent(id='xf1', type='transformer', label='1#主变', terminal_ids=('xf1:t1',)),
                    ElectricalComponent(id='bus1', type='busbar', label='0.4kV母线', terminal_ids=('bus1:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='sg_in:t1', component_id='sg_in', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='sg_in:t2', component_id='sg_in', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='xf1:t1', component_id='xf1', role='lv', x=-5, y=0, node_id=1),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=15, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('sg_in:t1', 'xf1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('sg_in:t2', 'bus1:t1'), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalSwitchgearFeedChainRule().run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'electrical.switchgear_feed_chain')

    def test_switchgear_feed_chain_rule_accepts_incoming_and_outgoing_via_shared_busbar(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='sg_in', type='switchgear_unit', label='1#进线柜', terminal_ids=('sg_in:t1', 'sg_in:t2')),
                    ElectricalComponent(id='sg_out', type='switchgear_unit', label='1#出线柜', terminal_ids=('sg_out:t1', 'sg_out:t2')),
                    ElectricalComponent(id='xf1', type='transformer', label='1#主变', terminal_ids=('xf1:t1',)),
                    ElectricalComponent(id='bus1', type='busbar', label='0.4kV母线', terminal_ids=('bus1:t1', 'bus1:t2')),
                    ElectricalComponent(id='load1', type='load', label='所用电', terminal_ids=('load1:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='sg_in:t1', component_id='sg_in', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='sg_in:t2', component_id='sg_in', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='sg_out:t1', component_id='sg_out', role='left', x=20, y=0, node_id=2),
                    ElectricalTerminal(id='sg_out:t2', component_id='sg_out', role='right', x=30, y=0, node_id=3),
                    ElectricalTerminal(id='xf1:t1', component_id='xf1', role='lv', x=-5, y=0, node_id=1),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap_a', x=15, y=0, node_id=2),
                    ElectricalTerminal(id='bus1:t2', component_id='bus1', role='tap_b', x=25, y=0, node_id=2),
                    ElectricalTerminal(id='load1:t1', component_id='load1', role='load', x=35, y=0, node_id=3),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('sg_in:t1', 'xf1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('sg_in:t2', 'bus1:t1', 'bus1:t2', 'sg_out:t1'), node_ids=(2,)),
                    ElectricalNet(id='net:3', terminal_ids=('sg_out:t2', 'load1:t1'), node_ids=(3,)),
                ),
            )
        )

        issues = ElectricalSwitchgearFeedChainRule().run(model).issues

        self.assertEqual(len(issues), 0)

    def test_switchgear_feed_chain_rule_skips_proxy_incoming_switchgear(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='proxy:sg_in', type='switchgear_unit', label='1#进线柜', terminal_ids=('sg_in:t1', 'sg_in:t2')),
                    ElectricalComponent(id='xf1', type='transformer', label='1#主变', terminal_ids=('xf1:t1',)),
                    ElectricalComponent(id='bus1', type='busbar', label='I段母线', terminal_ids=('bus1:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='sg_in:t1', component_id='proxy:sg_in', role='source', x=-5, y=0, node_id=1),
                    ElectricalTerminal(id='sg_in:t2', component_id='proxy:sg_in', role='busbar', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='xf1:t1', component_id='xf1', role='hv', x=-10, y=0, node_id=1),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=15, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('sg_in:t1', 'xf1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('sg_in:t2', 'bus1:t1'), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalSwitchgearFeedChainRule().run(model).issues

        self.assertEqual(len(issues), 0)

    def test_tie_switchgear_dual_side_rule_flags_single_sided_tie(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='tie1', type='switchgear_unit', label='1#联络柜', terminal_ids=('tie1:t1', 'tie1:t2')),
                    ElectricalComponent(id='bus1', type='busbar', label='I段母线', terminal_ids=('bus1:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='tie1:t1', component_id='tie1', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='tie1:t2', component_id='tie1', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=15, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('tie1:t1',), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('tie1:t2', 'bus1:t1'), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalTieSwitchgearDualSideRule().run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'electrical.tie_switchgear_dual_side')

    def test_tie_switchgear_dual_side_rule_accepts_dual_busbar_tie(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='tie1', type='switchgear_unit', label='1#联络柜', terminal_ids=('tie1:t1', 'tie1:t2')),
                    ElectricalComponent(id='bus1', type='busbar', label='I段母线', terminal_ids=('bus1:t1',)),
                    ElectricalComponent(id='bus2', type='busbar', label='II段母线', terminal_ids=('bus2:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='tie1:t1', component_id='tie1', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='tie1:t2', component_id='tie1', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=-5, y=0, node_id=1),
                    ElectricalTerminal(id='bus2:t1', component_id='bus2', role='tap', x=15, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('tie1:t1', 'bus1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('tie1:t2', 'bus2:t1'), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalTieSwitchgearDualSideRule().run(model).issues

        self.assertEqual(len(issues), 0)

    def test_incoming_transformer_busbar_direction_rule_flags_same_side_links(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='sg1', type='switchgear_unit', label='1#进线柜', terminal_ids=('sg1:t1', 'sg1:t2')),
                    ElectricalComponent(id='xf1', type='transformer', label='1#主变', terminal_ids=('xf1:t1',)),
                    ElectricalComponent(id='bus1', type='busbar', label='I段母线', terminal_ids=('bus1:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='sg1:t1', component_id='sg1', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='sg1:t2', component_id='sg1', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='xf1:t1', component_id='xf1', role='lv', x=-5, y=0, node_id=1),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=-8, y=0, node_id=1),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('sg1:t1', 'xf1:t1', 'bus1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('sg1:t2',), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalIncomingTransformerBusbarDirectionRule().run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'electrical.incoming_transformer_busbar_direction')

    def test_incoming_transformer_busbar_direction_rule_accepts_opposite_sides(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='sg1', type='switchgear_unit', label='1#进线柜', terminal_ids=('sg1:t1', 'sg1:t2')),
                    ElectricalComponent(id='xf1', type='transformer', label='1#主变', terminal_ids=('xf1:t1',)),
                    ElectricalComponent(id='bus1', type='busbar', label='I段母线', terminal_ids=('bus1:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='sg1:t1', component_id='sg1', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='sg1:t2', component_id='sg1', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='xf1:t1', component_id='xf1', role='lv', x=-5, y=0, node_id=1),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=15, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('sg1:t1', 'xf1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('sg1:t2', 'bus1:t1'), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalIncomingTransformerBusbarDirectionRule().run(model).issues

        self.assertEqual(len(issues), 0)

    def test_tie_busbar_segment_consistency_rule_flags_same_segment_busbars(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='tie1', type='switchgear_unit', label='1#联络柜', terminal_ids=('tie1:t1', 'tie1:t2')),
                    ElectricalComponent(id='bus1', type='busbar', label='I段母线A', terminal_ids=('bus1:t1',)),
                    ElectricalComponent(id='bus2', type='busbar', label='I段母线B', terminal_ids=('bus2:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='tie1:t1', component_id='tie1', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='tie1:t2', component_id='tie1', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=-5, y=0, node_id=1),
                    ElectricalTerminal(id='bus2:t1', component_id='bus2', role='tap', x=15, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('tie1:t1', 'bus1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('tie1:t2', 'bus2:t1'), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalTieBusbarSegmentConsistencyRule().run(model).issues

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].rule_id, 'electrical.tie_busbar_segment_consistency')

    def test_tie_busbar_segment_consistency_rule_accepts_distinct_segments(self) -> None:
        model = SystemModel(
            electrical=ElectricalGraph(
                components=(
                    ElectricalComponent(id='tie1', type='switchgear_unit', label='1#联络柜', terminal_ids=('tie1:t1', 'tie1:t2')),
                    ElectricalComponent(id='bus1', type='busbar', label='I段母线', terminal_ids=('bus1:t1',)),
                    ElectricalComponent(id='bus2', type='busbar', label='II段母线', terminal_ids=('bus2:t1',)),
                ),
                terminals=(
                    ElectricalTerminal(id='tie1:t1', component_id='tie1', role='left', x=0, y=0, node_id=1),
                    ElectricalTerminal(id='tie1:t2', component_id='tie1', role='right', x=10, y=0, node_id=2),
                    ElectricalTerminal(id='bus1:t1', component_id='bus1', role='tap', x=-5, y=0, node_id=1),
                    ElectricalTerminal(id='bus2:t1', component_id='bus2', role='tap', x=15, y=0, node_id=2),
                ),
                nets=(
                    ElectricalNet(id='net:1', terminal_ids=('tie1:t1', 'bus1:t1'), node_ids=(1,)),
                    ElectricalNet(id='net:2', terminal_ids=('tie1:t2', 'bus2:t1'), node_ids=(2,)),
                ),
            )
        )

        issues = ElectricalTieBusbarSegmentConsistencyRule().run(model).issues

        self.assertEqual(len(issues), 0)


if __name__ == '__main__':
    unittest.main()
