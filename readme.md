一、项目目标（明确边界）

构建一个面向**电力一次系统图（优先）**的自动审图工具，实现：

DWG/DXF 图纸解析

图元结构化建模

基于规则的自动审图

错误检测与报告生成

人工交互修正闭环

⚠️ 本阶段定位：工具型产品（单场景闭环），非平台型服务
业务流程：
- 用户上传一次系统图（DWG/DXF）
- 工具解析图元，构建系统模型
- 模型与规则引擎对比，检测错误
- 生成错误报告，提示用户修正
- 用户手动修正错误
- 工具重复对比，确认无错误
- 输出审核通过的系统图

当前审图能力（默认最高级：拓扑 + 规则）：
- 解析：实体类型/图层统计、bbox、关键坐标（LINE端点、TEXT/INSERT插入点等）
- 建模：Device（label/device_type/terminals/source_entity_ids）
- 拓扑：候选导线（LINE + LWPOLYLINE/POLYLINE 拆段）→ 端点吸附聚类 → nets（连通分量）→ 输出 topology.json
- 规则：基础规则 + 拓扑级规则（以 topology.json 所对应的拓扑为输入）

当前审图能力分级（Level 1/2/3）：
- Level 1（图元抽取）：实体类型/图层统计、bbox、关键坐标（LINE端点、TEXT插入点、INSERT插入点）
- Level 2（设备对象）：从 INSERT + 附近文本构建 Device（label/device_type/terminals/source_entity_ids）
- Level 3（拓扑关系）：候选导线（LINE + LWPOLYLINE 拆段）→ 端点吸附聚类 → 连通分量（nets）→ 输出 topology.json，并运行拓扑级规则


⚠️ 语义边界（重要）：
- 拓扑是“候选导线”的几何连通拓扑；候选导线需要通过图层/线型/长度过滤减少 DIM/标注引线等噪声
- 设备类型识别与端子模板需要规则库持续补齐；未命中模板时会回退到“设备附近线端点聚类/默认端子”

二、命令行使用

单文件审图：
- `python -m sparkflow audit <file.dxf|file.dwg> --out out`
  - 可选：`--ruleset rulesets\\example`（加载规则库目录 ruleset.json）
  - 可选：`--topo-tol 1.0`（拓扑吸附容差）
  - 可选：候选导线过滤
    - `--wire-layer-include <pattern>` / `--wire-layer-exclude <pattern>`（可重复）
    - `--wire-ltype-include <pattern>` / `--wire-ltype-exclude <pattern>`（可重复）
    - `--wire-min-length <float>`（过滤短线段）

典设目录扫描索引：
- `python -m sparkflow index <dataset_dir> --out out --hash`

典设目录批量审图（单图报告 + 汇总报告）：
- `python -m sparkflow audit-dataset <dataset_dir> --out out --ruleset rulesets\\example`

测试用例（拓扑 + 报告输出）：
- DXF（推荐先用 DXF 验证拓扑产物）：
  - `python -m sparkflow audit "image\\111\\电缆CAD图纸\\国网低压典设第26章E模块2017-8-18.dxf" --out out_level3 --dxf-backend auto --topo-tol 1.0`
  - `python -m sparkflow audit "image\\111\\电缆CAD图纸\\国网低压典设第25章B模块2017-12-11.dxf" --out out_level3 --dxf-backend auto --topo-tol 1.0`
  - 预期输出：
    - `out_level3\\<run_id>\\report.md`（最终报告文档）
    - `out_level3\\<run_id>\\report.json`（结构化报告）
    - `out_level3\\<run_id>\\report.docx`（Word 报告）
    - `out_level3\\<run_id>\\topology.json`（拓扑产物：nodes/edges/nets）

三、DWG→DXF 转换器配置

目前 DWG 需要先转换为 DXF 才能进入解析与审图。支持两类后端：

1) 外部转换器（推荐，适合批处理/服务化）
- 通过参数传入：`--dwg-backend cli --dwg-converter "<cmd...>"`
- 或通过环境变量：`SPARKFLOW_DWG2DXF_CMD="<cmd...>"`
- 命令约定：
  - 默认会在命令后追加 `<input.dwg> <output.dxf>`
  - 若命令中包含 `{in}` `{out}`，则使用占位符替换（不再追加）

2) AutoCAD COM（可选，需安装 AutoCAD）
- 通过参数启用：`--dwg-backend autocad`
- 需要本机 AutoCAD 可用，且 Python 环境安装 pywin32（用于 COM 调用）

四、DXF 解析后端（auto / ascii / ezdxf）

SparkFlow 提供三种 DXF 解析后端（默认 `auto`，推荐用于审图）：

- `auto`：审图优先策略
  - 先尝试 `ascii`；若解析失败，或解析质量指标不达标（例如 bbox 缺失/关键实体缺失），则回退到 `ezdxf`
  - 报告会记录最终使用的后端与回退原因，便于复现与调参
- `ascii`：自研 ASCII DXF 解析器（基于 group code 两行一组抽取 `SECTION ENTITIES`）
  - 优点：依赖少、行为可控、适合快速统计/批处理扫描
  - 局限：对复杂 DXF 特性支持有限（例如部分实体字段、容错与兼容性）
- `ezdxf`：基于 ezdxf 的 DXF 读取与实体遍历
  - 优点：覆盖更多 DXF 实体与字段，兼容性更强，便于扩展对象识别
  - 代价：资源开销更高；且 ezdxf 不负责 DWG→DXF 或 DXF 版本转换

使用方式：
- 单文件：`python -m sparkflow audit <file.dxf|file.dwg> --dxf-backend ascii|ezdxf|auto`
- 批处理：`python -m sparkflow audit-dataset <dataset_dir> --dxf-backend ascii|ezdxf|auto`

五、规则知识库（ruleset.json）

规则库目录需包含 `ruleset.json`，最小示例见 `rulesets/example/ruleset.json`。

规则框架：
- 规则以 `rule_id` 标识，通过 `enabled_rules` 控制启用列表
- `params` 支持为每条规则传参（例如 `wire.floating_endpoints.tol`、`device.missing_label.radius`）
- 内置规则（可在规则注册表中查看）：
  - `wire.floating_endpoints`：悬空线端点（基于候选导线 wires）
  - `device.missing_label`：设备缺少附近文本标注
  - `device.duplicate_label`：设备标注重复
  - `topo.terminal_unconnected`：端子未连接到任何导线网络（需要拓扑产物）
  - `topo.breaker_same_net`：断路器多个端子落在同一网络（需要拓扑产物与 ≥2 端子）

建模参数（ruleset.json 的 params._model）：
- `wire_filter`：候选导线过滤（include/exclude layers、include/exclude linetypes、min_length）
- `terminal_templates`：设备端子模板（按 block_name 匹配，支持 equals/contains/glob + 可选 ATTRIB 条件；terminals 至少 2 个）

ruleset.json 示例（截取）：
```json
{
  "version": "my_ruleset_v1",
  "enabled_rules": [
    "wire.floating_endpoints",
    "device.missing_label",
    "device.duplicate_label",
    "topo.terminal_unconnected",
    "topo.breaker_same_net"
  ],
  "params": {
    "_model": {
      "wire_filter": {
        "exclude_layers": ["DIM", "标注", "设备"],
        "min_length": 0.0
      },
      "terminal_templates": [
        {
          "block_name": "BKR*",
          "match_mode": "glob",
          "terminals": [
            {"name": "in", "x": -10.0, "y": 0.0},
            {"name": "out", "x": 10.0, "y": 0.0}
          ]
        }
      ]
    },
    "wire.floating_endpoints": {"tol": 1.0}
  }
}
```
