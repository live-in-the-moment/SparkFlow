# SparkFlow Normative Summary

## wire.floating_endpoints
- title: Floating wire endpoint recheck
- clause: GB 50303-2022 6.1.1
- enabled: false
- severity: error
- params: {"tol": 0.002}
- applies_to: electrical_schematic

## device.missing_label
- title: Device label completeness
- clause: GB 50303-2015 6.1.2
- enabled: true
- params: {"radius": 10.0}
- applies_to: single_line|electrical_schematic
