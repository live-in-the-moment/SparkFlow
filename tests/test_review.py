from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import ezdxf

from sparkflow.__main__ import main
from sparkflow.cad.parse import CadParseOptions
from sparkflow.review import load_review_bundle, review_audit
from sparkflow.review_workflow import review_pipeline


class ReviewFlowTests(unittest.TestCase):
    def test_load_review_bundle_extracts_project_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            review_dir = root / "评审意见"
            review_dir.mkdir(parents=True, exist_ok=True)

            _write_review_workbooks(review_dir, project_code="030451DY26030001")

            bundle = load_review_bundle(review_dir, project_code="030451DY26030001")

            self.assertEqual(bundle["project_code"], "030451DY26030001")
            self.assertEqual(bundle["project_name"], "南水供电所景旺电子（厂房一）10kV业扩配套工程")
            self.assertEqual(bundle["major_issues"]["execution_status"], "已执行")
            self.assertEqual(len(bundle["requirements"]), 5)
            self.assertEqual(bundle["requirements"][0]["scope"], "drawing")
            self.assertIn("10kV土建通道走向图", bundle["requirements"][0]["keywords"])
            self.assertEqual(bundle["requirements"][1]["scope"], "manual")
            self.assertEqual(bundle["requirements"][3]["source_type"], "cost")

    def test_review_audit_writes_document_driven_report(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / "景旺电子.dxf"
            review_dir = root / "评审意见"
            out = root / "out"
            dxf.write_text(_DXF_REVIEW, encoding="utf-8")
            review_dir.mkdir(parents=True, exist_ok=True)
            _write_review_workbooks(review_dir, project_code="030451DY26030001")

            output = review_audit(
                dxf,
                review_dir,
                out,
                project_code="030451DY26030001",
                parse_options=CadParseOptions(dxf_backend="ascii"),
            )

            self.assertTrue(output.drawing_info_json_path.exists())
            self.assertTrue(output.review_bundle_json_path.exists())
            self.assertTrue(output.review_report_json_path.exists())
            self.assertTrue(output.review_report_md_path.exists())

            report = json.loads(output.review_report_json_path.read_text(encoding="utf-8"))
            self.assertEqual(report["project_code"], "030451DY26030001")
            self.assertEqual(report["drawing_info_json_path"], str(output.drawing_info_json_path))
            self.assertEqual(report["review_bundle_json_path"], str(output.review_bundle_json_path))
            self.assertEqual(report["summary"]["placeholder_text_count"], 1)
            self.assertIn("FXX", report["summary"]["placeholder_texts"])

            results = {item["text"]: item["result"] for item in report["requirements"]}
            self.assertEqual(results["补充10kV土建通道走向图"], "evidence_found")
            self.assertEqual(results["设计说明书补充电缆线路说明"], "manual_required")
            self.assertEqual(results["图纸补充二次柜工程量说明"], "evidence_found")

    def test_review_audit_can_skip_sparkflow_audit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / "景旺电子.dxf"
            review_dir = root / "评审意见"
            out = root / "out"
            dxf.write_text(_DXF_REVIEW, encoding="utf-8")
            review_dir.mkdir(parents=True, exist_ok=True)
            _write_review_workbooks(review_dir, project_code="030451DY26030001")

            output = review_audit(
                dxf,
                review_dir,
                out,
                project_code="030451DY26030001",
                parse_options=CadParseOptions(dxf_backend="ascii"),
                include_sparkflow_audit=False,
            )

            report = json.loads(output.review_report_json_path.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["sparkflow_audit_skipped"])
            self.assertIsNone(report["sparkflow_report_json_path"])
            self.assertIsNone(report["sparkflow_report_md_path"])
            self.assertIsNone(output.sparkflow_report_json_path)
            self.assertIsNone(output.sparkflow_report_md_path)

    def test_drawing_info_command_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / "drawing.dxf"
            out_json = root / "drawing_info.json"
            dxf.write_text(_DXF_REVIEW, encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "drawing-info",
                        str(dxf),
                        "--out",
                        str(out_json),
                        "--dxf-backend",
                        "ascii",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue().strip(), str(out_json))
            self.assertEqual(stderr.getvalue(), "")

            drawing_info = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertIn("10kV土建通道走向图", drawing_info["unique_texts"])
            self.assertIn("FXX", drawing_info["placeholder_texts"])

    def test_review_pipeline_writes_split_pages_and_rectification_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / "workflow.dxf"
            review_dir = root / "评审意见"
            out = root / "out"
            _write_split_review_dxf(dxf)
            review_dir.mkdir(parents=True, exist_ok=True)
            _write_review_workbooks(review_dir, project_code="030451DY26030001")

            output = review_pipeline(
                dxf,
                review_dir,
                out,
                project_code="030451DY26030001",
                parse_options=CadParseOptions(dxf_backend="ezdxf"),
                include_sparkflow_audit=False,
            )

            self.assertTrue(output.split_manifest_json_path.exists())
            self.assertTrue(output.rectification_checklist_md_path.exists())
            self.assertTrue(output.rectification_checklist_json_path.exists())

            manifest = json.loads(output.split_manifest_json_path.read_text(encoding="utf-8"))
            page = next(item for item in manifest if item["sheet_no"] == 3)
            self.assertEqual(page["title"], "10kV单线图（改造后1）")
            self.assertIn("10kV XXX甲线", page["placeholder_texts"])

            checklist_md = output.rectification_checklist_md_path.read_text(encoding="utf-8")
            self.assertIn("整改问题清单", checklist_md)
            self.assertIn("10kV单线图（改造后1）", checklist_md)
            self.assertIn("10kV XXX甲线", checklist_md)

    def test_review_pipeline_command_writes_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dxf = root / "workflow.dxf"
            review_dir = root / "评审意见"
            out = root / "out"
            _write_split_review_dxf(dxf)
            review_dir.mkdir(parents=True, exist_ok=True)
            _write_review_workbooks(review_dir, project_code="030451DY26030001")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "review-pipeline",
                        str(dxf),
                        "--review-dir",
                        str(review_dir),
                        "--out",
                        str(out),
                        "--project-code",
                        "030451DY26030001",
                        "--dxf-backend",
                        "ezdxf",
                        "--skip-sparkflow-audit",
                    ]
                )

            self.assertEqual(exit_code, 0)
            lines = stdout.getvalue().splitlines()
            self.assertGreaterEqual(len(lines), 4)
            self.assertTrue(Path(lines[1]).exists())
            self.assertTrue(Path(lines[2]).exists())
            self.assertTrue(Path(lines[3]).exists())
            self.assertEqual(stderr.getvalue(), "")


_DXF_REVIEW = """0
SECTION
2
ENTITIES
0
LINE
10
0
20
0
11
10
21
0
0
LINE
10
10
20
0
11
10
21
10
0
TEXT
10
0
20
0
1
10kV土建通道走向图
0
TEXT
10
0
20
5
1
二次柜工程量说明
0
TEXT
10
0
20
10
1
FXX
0
ENDSEC
0
EOF
"""


def _write_review_workbooks(review_dir: Path, *, project_code: str) -> None:
    summary_row = [""] * 35
    summary_row[1] = "南水供电所景旺电子（厂房一）10kV业扩配套工程"
    summary_row[2] = project_code
    summary_row[3] = "100"
    summary_row[4] = "98"
    summary_row[5] = "90"
    summary_row[6] = "88"
    summary_row[8] = "业扩配套"
    summary_row[33] = "无"

    major_row = [""] * 13
    major_row[2] = "南水供电所景旺电子（厂房一）10kV业扩配套工程"
    major_row[3] = project_code
    major_row[6] = (
        "技术意见：\n"
        "（1）补充10kV土建通道走向图\n"
        "（2）设计说明书补充电缆线路说明\n"
        "（3）图纸补充二次柜工程量说明"
    )
    major_row[7] = "张工"
    major_row[8] = "（1）已补充\n（2）已补充\n（3）已补充"
    major_row[9] = "1、预算备注“参考近期领料价”的甲供设备价格\n2、一般勘察费计算有误，应按30%"
    major_row[10] = "李工"
    major_row[11] = "1、已修正\n2、已修正"
    major_row[12] = "已执行"

    _write_xlsx_sheet(
        review_dir / "附件12 20kV及以下配网工程设计评审情况汇总表(珠海金湾供电局2026年3月配网业扩配套项目）.xlsx",
        "表4.2 评审情况明细表",
        [["序号", "工程名称", "工程编号"], summary_row],
    )
    _write_xlsx_sheet(
        review_dir / "珠海金湾供电局2026年3月配网业扩配套项目批次设计和造价主要问题统计表（2项）2026.3.25(1).xlsx",
        "表5 设计和造价主要问题统计表",
        [["序号", "批次", "工程名称", "工程编号"], major_row],
    )


def _write_split_review_dxf(path: Path) -> None:
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))

    directory_block = doc.blocks.new("frame_a4l1v_（新）目录无设计")
    directory_block.add_lwpolyline(
        [(-25, -37), (185, -37), (185, 260), (-25, 260)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )
    directory_block.add_lwpolyline(
        [(0, 0), (160, 0), (160, 220), (0, 220)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )

    page_block = doc.blocks.new("frame_a3l1hfl_（新）珠海电力-a2a3a4-阶段无设计")
    page_block.add_lwpolyline(
        [(-25, -5), (395, -5), (395, 292), (-25, 292)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )
    page_block.add_lwpolyline(
        [(0, 0), (370, 0), (370, 250), (0, 250)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )

    layout = doc.layouts.get("Layout1")
    layout.add_blockref(
        "frame_a4l1v_（新）目录无设计",
        (100, 500),
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )
    layout.add_text(
        "47-P26011006S-03",
        dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (120, 680), "height": 6},
    )
    layout.add_text(
        "10kV单线图（改造后1）",
        dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (180, 680), "height": 6},
    )

    layout.add_blockref(
        "frame_a3l1hfl_（新）珠海电力-a2a3a4-阶段无设计",
        (400, 500),
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )
    layout.add_text(
        "47-P26011006S-03",
        dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (430, 515), "height": 6},
    )
    layout.add_text(
        "10kV XXX甲线",
        dxfattribs={"layer": "0", "insert": (460, 710), "height": 10},
    )
    layout.add_text(
        "110kV达能变电站(FXXX间隔)",
        dxfattribs={"layer": "0", "insert": (460, 690), "height": 8},
    )
    layout.add_line((450, 670), (720, 670), dxfattribs={"layer": "0"})

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)


def _write_xlsx_sheet(path: Path, sheet_name: str, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '</Types>'
            ),
        )
        archive.writestr(
            "_rels/.rels",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="xl/workbook.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "xl/workbook.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets><sheet name="{xml_escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
                "</workbook>"
            ),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr("xl/worksheets/sheet1.xml", _render_xlsx_sheet(rows))


def _render_xlsx_sheet(rows: list[list[str]]) -> str:
    rendered_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            cell_ref = f"{_xlsx_column_name(column_index)}{row_index}"
            cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{xml_escape(value)}</t></is></c>')
        rendered_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(rendered_rows)}</sheetData>'
        "</worksheet>"
    )


def _xlsx_column_name(index: int) -> str:
    name = ""
    value = index
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


if __name__ == "__main__":
    unittest.main()
