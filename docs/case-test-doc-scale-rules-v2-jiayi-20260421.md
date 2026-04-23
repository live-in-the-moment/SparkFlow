# 案例测试结果：Doc Scale Rules V2

## 1. 测试目标

对真实工程案例“加益供电所10kV合江线新增配变及黄沙公用台变改造工程”重新执行一轮 `v2` 能力验证，确认：

- 工程附件是否能被自动发现
- 说明书/清册/杆塔明细表是否能被抽取为结构化事实
- `stategrid_peidian_strict_v2` 是否能在真实 `DWG` 上进入正式 `audit` 链路

## 2. 测试样本

- 图纸：
  [图纸-加益供电所10kV合江线新增配变及黄沙公用台变改造工程.dwg](</D:/code/project/moment/SparkFlow/docs/罗定供电局2025年中低压配电网第十批紧急项目--4项/罗定供电局2025年中低压配电网第十批紧急项目施工图--评审前/罗定供电局2025年中低压配电网第十批紧急项目施工图/加益供电所10kV合江线新增配变及黄沙公用台变改造工程/附件3 施工图/图纸-加益供电所10kV合江线新增配变及黄沙公用台变改造工程.dwg>)
- 说明书：
  [附件1 施工图设计说明书_加益供电所10kV合江线新增配变及黄沙公用台变改造工程.docx](</D:/code/project/moment/SparkFlow/docs/罗定供电局2025年中低压配电网第十批紧急项目--4项/罗定供电局2025年中低压配电网第十批紧急项目施工图--评审前/罗定供电局2025年中低压配电网第十批紧急项目施工图/加益供电所10kV合江线新增配变及黄沙公用台变改造工程/附件1 施工图设计说明书_加益供电所10kV合江线新增配变及黄沙公用台变改造工程.docx>)
- 材料清册：
  [附件4 主要设备材料清册.xlsx](</D:/code/project/moment/SparkFlow/docs/罗定供电局2025年中低压配电网第十批紧急项目--4项/罗定供电局2025年中低压配电网第十批紧急项目施工图--评审前/罗定供电局2025年中低压配电网第十批紧急项目施工图/加益供电所10kV合江线新增配变及黄沙公用台变改造工程/附件4 主要设备材料清册.xlsx>)
- 杆塔明细表：
  [10kV及以下杆（塔）明细表-加益供电所10kV合江线新增配变及黄沙公用台变改造工程.xls](</D:/code/project/moment/SparkFlow/docs/罗定供电局2025年中低压配电网第十批紧急项目--4项/罗定供电局2025年中低压配电网第十批紧急项目施工图--评审前/罗定供电局2025年中低压配电网第十批紧急项目施工图/加益供电所10kV合江线新增配变及黄沙公用台变改造工程/附件3 施工图/10kV及以下杆（塔）明细表-加益供电所10kV合江线新增配变及黄沙公用台变改造工程.xls>)

## 3. 执行时间

- 首轮执行：`2026-04-21 18:07` 至 `2026-04-21 18:08`（Asia/Shanghai）
- 继续推进后复测：`2026-04-21 18:18` 至 `2026-04-21 18:20`（Asia/Shanghai）

## 4. 执行内容

### 4.1 文档上下文抽取

调用 `build_project_document_context()`，并将结果落盘到：

- [project_document_context.json](/D:/code/project/moment/SparkFlow/tmp/case_doc_scale_rules_v2_20260421-180653/project_document_context.json:1)

### 4.2 真实图纸审图命令

执行命令：

```powershell
python -X utf8 -m sparkflow audit "<真实DWG路径>" --out tmp\case_doc_scale_rules_v2_20260421-180653\audit_run --ruleset rulesets\stategrid_peidian_strict
```

命令输出产物：

- [audit_exit_code.txt](/D:/code/project/moment/SparkFlow/tmp/case_doc_scale_rules_v2_20260421-180653/audit_exit_code.txt:1)
- [audit_stdout.txt](/D:/code/project/moment/SparkFlow/tmp/case_doc_scale_rules_v2_20260421-180653/audit_stdout.txt:1)
- [audit_stderr.txt](/D:/code/project/moment/SparkFlow/tmp/case_doc_scale_rules_v2_20260421-180653/audit_stderr.txt:1)
- [report.json](/D:/code/project/moment/SparkFlow/tmp/case_doc_scale_rules_v2_20260421-180653/audit_run/20260421T102001Z/report.json:1)
- [report.md](/D:/code/project/moment/SparkFlow/tmp/case_doc_scale_rules_v2_20260421-180653/audit_run/20260421T102001Z/report.md:1)
- [report.docx](/D:/code/project/moment/SparkFlow/tmp/case_doc_scale_rules_v2_20260421-180653/audit_run/20260421T102001Z/report.docx:1)

## 5. 实际结果

### 5.1 附件发现

结果：`PASS`

系统自动发现了 4 个目标输入源：

- `docx` 说明书 1 份
- `xlsx` 材料/设备清册 2 份
- `xls` 杆塔明细表 1 份

### 5.2 文档抽取

结果：`PARTIAL PASS`

复测后系统当前抽取出的 `expected_counts` 为：

- `smart_gateway = 1`
- `distribution_transformer = 1`
- `dtu = 0`
- `pole_tower = 14`

人工 spot-check：

- 说明书“1.2 建设规模”表中，`配电智能网关 = 1`，与系统抽取一致。
- 说明书“1.2 建设规模”表中，`DTU（台） = 0`，与系统抽取一致。
- 说明书“1.2 建设规模”表中，`配变数量（台） = 1`，复测后已与系统抽取一致。
- 杆（塔）明细表中按真实杆号 `N0-N13` 计数后，系统当前抽取 `杆塔 = 14`。

结论：

- `智能网关`、`DTU`、`台变` 的说明书主表抽取已具备案例可用性。
- `measurement_comm_unit` 和 `secondary_cabinet` 在该真实工程样本中，复测后未再生成误识别主值；当前更偏向“无明确结构化来源则不纳入 `expected_counts`”。
- `杆塔` 已改为优先使用 `杆（塔）明细表` 的真实杆号计数，不再被说明书中的拆旧表或正文噪声覆盖。

### 5.3 真实 DWG 审图

结果：`FAIL`

本次真实 `DWG -> audit` 命令已正常返回并生成报告，但并未进入正式规则判定阶段。关键结果如下：

- `exit_code = 0`
- `rule_version = stategrid_peidian_strict_v2`
- `parser = unprocessed`
- `passed = false`
- 唯一 issue：`cad.parse_failed`

复测后的原始失败原因来自报告：

```text
DWG 暂不支持直接解析，且未检测到可用转换器。可选择：配置 SPARKFLOW_DWG2DXF_CMD（外部工具），或安装 AutoCAD+pywin32。详情：AutoCAD COM 转换失败：未生成输出 DXF 文件。
```

结论：

- `stategrid_peidian_strict_v2` 已成功进入真实案例命令路径，报告中记录的版本号正确。
- AutoCAD COM 重试后，阻塞形态从“被呼叫方拒绝接收呼叫”推进成了“未生成输出 DXF 文件”，说明转换阶段有推进，但仍未完成可用 DXF 落盘。
- 这次真实案例仍没有跑到“文档事实 + 图纸计数 -> 正式 issue 输出”这一步，原因仍是 `DWG -> DXF` 前置转换未打通。

## 6. 结论汇总

- 附件自动发现：`PASS`
- Word/XLSX/XLS 文档抽取链路：`PASS`
- 真实说明书主表中的 `智能网关`、`DTU`、`台变` 抽取：`PASS`
- 真实杆塔明细表计数：`PASS`
- 真实 `综合测控通信单元 / 二次柜` 结构化数量来源：`NOT FOUND IN THIS CASE`
- 真实 `DWG -> DXF` 转换：`PASS`
- 真实整套施工图进入完整 `audit`：`FAIL (TIMEOUT)`

## 7. 当前阻塞

### 7.1 环境阻塞

- AutoCAD COM 已能在该案例上产出 DXF，最新成功落盘示例：
  `C:\Users\simon\AppData\Local\Temp\sparkflow_dwg2dxf_n9cejtqg\图纸-加益供电所10kV合江线新增配变及黄沙公用台变改造工程.dxf`
- 但将整套施工图（约 1e8 字节级 DXF）继续送入 `audit` 时，即使降到 `--level 1`，在 10 分钟窗口内仍未收敛，也没有生成 `report.json`。

### 7.1.1 真实性能证据

- `parse_cad + selection_texts` 可完成，并已验证能提取出至少一个明确电气信号 `380V`
- `sparkflow audit <real-dxf> --level 1`：
  - 4 分钟窗口：超时
  - 10 分钟窗口：仍超时
  - 中间运行目录：
    - `tmp/case_doc_scale_rules_v2_20260421-180653/audit_from_dxf_l1/20260421T105158Z`
    - `tmp/case_doc_scale_rules_v2_20260421-180653/audit_from_dxf_l1/20260421T105645Z`
  - 两个目录均未落出 `report.json`，说明瓶颈在完整审图流程早期阶段

### 7.2 规则数据质量阻塞

- `measurement_comm_unit`、`secondary_cabinet` 在该案例中没有找到足够强的结构化数量来源，当前规则会保守跳过数量主值生成。
- `pole_tower = 14` 已按真实杆号计数生成，但仍需与你的业务口径核对这是否就是你希望参与比对的“杆塔数量”。

## 8. 建议后续动作

1. 下一步优先不是继续修转换，而是优化“大体量整套施工图”的 `audit` 性能，至少让该案例在可接受时限内生成 `report.json`。
2. 若你确认“杆塔数量”应按明细表中的真实杆号 `N0-N13` 计数，则把 `14` 固化为该类项目的默认口径。
3. 为 `综合测控通信单元`、`二次柜` 再补至少一条真实案例样本，建立可重复的结构化数量来源。
