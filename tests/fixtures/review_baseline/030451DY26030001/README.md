# Review Baseline Fixture

该目录保存 `030451DY26030001` 项目的正式脱敏基线夹具。

来源：

- 原始评审意见目录：`docs/珠海金湾供电局2026年3月配网业扩配套项目--2项/评审意见`
- 原始图纸：`docs/珠海金湾供电局2026年3月配网业扩配套项目--2项/评审前/.../南水供电所景旺电子（厂房一）10kV业扩配套工程.dwg`
- 基线运行目录：`tmp/review_pipeline_030451DY26030001_docdriven/20260415T070348Z`

内容：

- `fixture.json`：从真实项目输入提取后生成的脱敏夹具规范，用于生成项目专用评审规则基线

脱敏规则：

- 保留工程编号 `030451DY26030001`
- 保留评审意见语义、图号、页码、占位符类型、关键证据词
- 脱敏工程名称、专家姓名、参考项目名、变电站名称、用户单位名称、本地绝对路径

用法：

- [tests/test_review.py](D:/code/project/moment/SparkFlow/tests/test_review.py) 会读取该 `fixture.json`
- 测试运行时再临时生成 `review_dir/*.xlsx` 和 `drawing.dxf`
- 测试会把 `评审意见` 解析为 `review_rules`，再对解析后的图纸执行规则审查
- 仓库内不直接保存真实 `DWG/XLSX` 原件
