from __future__ import annotations

import unittest

from sparkflow.model.connectivity import ConnectivityBuildOptions, build_connectivity
from sparkflow.model.electrical import build_electrical_graph
from sparkflow.model.types import Device, Point2D, SystemModel, Terminal, UnresolvedItem, WireSegment
from sparkflow.rules.rules import FloatingWireEndpointsRule


class ElectricalGraphTests(unittest.TestCase):
    def test_builds_switchable_and_coupled_relations(self) -> None:
        model = SystemModel(
            wires=(
                WireSegment(id='w1', a=Point2D(0, 0), b=Point2D(10, 0)),
                WireSegment(id='w2', a=Point2D(20, 0), b=Point2D(30, 0)),
            ),
            devices=(
                Device(
                    id='dev:b1',
                    position=Point2D(5, 0),
                    label='B1',
                    device_type='breaker',
                    terminals=(
                        Terminal(id='dev:b1:t1', position=Point2D(0, 0), name='in'),
                        Terminal(id='dev:b1:t2', position=Point2D(10, 0), name='out'),
                    ),
                ),
                Device(
                    id='dev:t1',
                    position=Point2D(25, 0),
                    label='T1',
                    device_type='transformer',
                    terminals=(
                        Terminal(id='dev:t1:t1', position=Point2D(20, 0), name='hv'),
                        Terminal(id='dev:t1:t2', position=Point2D(30, 0), name='lv'),
                    ),
                ),
            ),
        )
        model = build_connectivity(model, options=ConnectivityBuildOptions(tol=0.1))
        model = build_electrical_graph(model)
        assert model.electrical is not None
        relation_types = {relation.id: relation.type for relation in model.electrical.relations}
        self.assertIn('switchable', relation_types.values())
        self.assertIn('coupled', relation_types.values())
        self.assertEqual(len(model.electrical.nets), 2)

    def test_filters_terminal_anchor_unresolved_when_device_was_later_resolved(self) -> None:
        model = SystemModel(
            wires=(
                WireSegment(id='w1', a=Point2D(0, 0), b=Point2D(10, 0)),
                WireSegment(id='w2', a=Point2D(10, 0), b=Point2D(20, 0)),
            ),
            devices=(
                Device(
                    id='dev:df1',
                    position=Point2D(10, 0),
                    label='DF-1',
                    device_type='cable_branch_box',
                    source_entity_ids=('text:1',),
                    terminals=(
                        Terminal(id='dev:df1:t1', position=Point2D(0, 0), name='feed', source_entity_ids=('text:1',)),
                        Terminal(id='dev:df1:t2', position=Point2D(20, 0), name='branch_a', source_entity_ids=('text:1',)),
                    ),
                ),
            ),
            unresolved=(
                UnresolvedItem(
                    kind='terminal_anchor',
                    source_entity_ids=('text:1',),
                    reason='文本设备候选未识别到足够端子锚点，已跳过。',
                    extra={'device_type': 'cable_branch_box', 'label': 'DF-1'},
                ),
            ),
        )
        model = build_connectivity(model, options=ConnectivityBuildOptions(tol=0.1))
        model = build_electrical_graph(model)
        assert model.electrical is not None
        unresolved = [item for item in model.electrical.unresolved if item.kind == 'terminal_anchor']
        self.assertEqual(unresolved, [])

    def test_connectivity_prunes_unanchored_nodes_created_only_by_self_loop_wires(self) -> None:
        model = SystemModel(
            wires=(
                WireSegment(
                    id='w1',
                    a=Point2D(0.0, 0.0),
                    b=Point2D(0.05, 0.05),
                    source_entity_ids=('wire:1',),
                ),
            ),
        )

        model = build_connectivity(model, options=ConnectivityBuildOptions(tol=0.1))

        assert model.connectivity is not None
        self.assertEqual(model.connectivity.nodes, ())
        self.assertEqual(model.connectivity.edges, ())
        self.assertEqual(FloatingWireEndpointsRule().run(model).issues, ())


if __name__ == '__main__':
    unittest.main()
