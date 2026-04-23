# SparkFlow Normative Summary

## wire.floating_endpoints
- enabled: true
- severity: warning
- params: {"tol": 0.001}
- applies_to: single_line|electrical_schematic|general_supported_electrical

## device.missing_label
- enabled: true
- params: {"radius": 10.0}
- applies_to: single_line|electrical_schematic|general_supported_electrical

## device.duplicate_label
- enabled: true
- params: {}

## device.label_pattern_invalid
- enabled: true
- severity: warning
- params: {}
- applies_to: single_line|electrical_schematic|general_supported_electrical

## electrical.component_missing_terminals
- enabled: true
- params: {}

## electrical.component_unconnected
- enabled: true
- severity: warning
- params: {}

## electrical.transformer_same_net
- enabled: true
- params: {}

## electrical.switch_same_net
- enabled: true
- params: {}

## electrical.switchgear_role_connection
- enabled: true
- severity: warning
- params: {}
- applies_to: single_line|electrical_schematic

## electrical.switchgear_feed_chain
- enabled: true
- severity: warning
- params: {}
- applies_to: single_line|electrical_schematic

## electrical.tie_switchgear_dual_side
- enabled: true
- severity: warning
- params: {}
- applies_to: single_line|electrical_schematic

## electrical.incoming_transformer_busbar_direction
- enabled: true
- severity: warning
- params: {"min_axis_separation": 2.0}
- applies_to: single_line

## electrical.tie_busbar_segment_consistency
- enabled: true
- severity: warning
- params: {}
- applies_to: single_line|electrical_schematic

## electrical.busbar_underconnected
- enabled: true
- severity: warning
- params: {"min_connected_terminals": 2}

## electrical.branch_box_insufficient_branches
- enabled: true
- params: {"min_branch_terminals": 2}

## electrical.relation_unresolved
- enabled: false
- params: {}
