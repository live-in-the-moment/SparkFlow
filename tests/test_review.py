from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape as xml_escape

import ezdxf

from sparkflow.__main__ import main
from sparkflow.cad.parse import CadParseOptions
from sparkflow.review import _load_technical_point_rules, load_review_rules, review_audit
from sparkflow.review_workflow import build_rectification_checklist, review_pipeline, split_review_pages


class ReviewFlowTests(unittest.TestCase):
    def test_review_baseline_fixture_exists(self) -> None:
        fixture_path = _review_fixture_path()
        self.assertTrue(fixture_path.exists(), fixture_path)
        fixture = _load_review_fixture()
        self.assertEqual(fixture["project"]["project_code"], "030451DY26030001")

    def test_load_review_rules_extracts_project_rules(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, review_dir, fixture = _stage_review_fixture(root)

            rules_doc = load_review_rules(review_dir, project_code=fixture["project"]["project_code"])

            self.assertEqual(rules_doc["project_code"], fixture["project"]["project_code"])
            self.assertEqual(rules_doc["project_name"], fixture["project"]["project_name"])
            self.assertEqual(
                rules_doc["major_issues"]["execution_status"],
                fixture["review"]["major_issues"]["execution_status"],
            )
            self.assertEqual(len(rules_doc["review_rules"]), len(fixture["expected"]["result_by_text"]))
            self.assertEqual(rules_doc["review_rules"][0]["check_type"], "drawing_text_presence")
            self.assertIn("10kV土建通道走向图", rules_doc["review_rules"][0]["keywords"])
            self.assertEqual(rules_doc["review_rules"][3]["check_type"], "manual_review")
            self.assertEqual(rules_doc["review_rules"][10]["source_type"], "cost")

    def test_load_review_rules_handles_realistic_major_issue_column_layout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            review_dir = Path(td) / "评审意见"
            review_dir.mkdir(parents=True, exist_ok=True)
            row = [""] * 15
            row[0] = "4"
            row[1] = "加益供电所10kV合江线新增配变及黄沙公用台变改造工程"
            row[2] = "035352DP24110647"
            row[6] = "1、设计说明书1.2建设规模智能网关数量校核。"
            row[7] = "1、设计说明书1.2建设规模智能网关数量已核实修改。"
            row[8] = "1、按新的调差系数调差；"
            row[9] = "1、已更新为最新调差系数；"
            row[10] = "已执行"
            row[11] = "否"
            row[12] = "无"
            row[13] = "否"
            row[14] = "无"
            _write_xlsx_sheet(
                review_dir / "附件2：设计和造价主要问题统计表.xlsx",
                "表5 设计和造价主要问题统计表",
                [
                    ["序号", "工程名称", "工程编码/项目数", "可研估算", "送审预算", "审定预算", "技术意见", "技术意见回复", "技经意见", "技经意见回复", "评审意见执行情况"],
                    row,
                ],
            )

            rules_doc = load_review_rules(review_dir, project_code="035352DP24110647")

            self.assertEqual(rules_doc["project_name"], "加益供电所10kV合江线新增配变及黄沙公用台变改造工程")
            self.assertEqual(rules_doc["major_issues"]["technical_opinion"], row[6])
            self.assertEqual(rules_doc["major_issues"]["technical_reply"], row[7])
            self.assertEqual(rules_doc["major_issues"]["cost_opinion"], row[8])
            self.assertEqual(rules_doc["major_issues"]["cost_reply"], row[9])
            self.assertEqual(rules_doc["major_issues"]["execution_status"], row[10])

    def test_load_review_rules_includes_matching_technical_points_excel(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            review_dir = Path(td) / "评审意见"
            tech_dir = review_dir / "评审技术要点"
            tech_dir.mkdir(parents=True, exist_ok=True)

            major_row = [""] * 15
            major_row[0] = "4"
            major_row[1] = "加益供电所10kV合江线新增配变及黄沙公用台变改造工程"
            major_row[2] = "035352DP24110647"
            major_row[6] = "1、设计说明书1.2建设规模智能网关数量校核。"
            major_row[7] = "1、已核实。"
            major_row[8] = ""
            major_row[9] = ""
            major_row[10] = "已执行"
            _write_xlsx_sheet(
                review_dir / "附件2：设计和造价主要问题统计表.xlsx",
                "表5 设计和造价主要问题统计表",
                [["序号", "工程名称", "工程编码/项目数"], major_row],
            )

            tech_rows = [
                ["配网工程设计评审技术要点"],
                ["项目名称：加益供电所10kV合江线新增配变及黄沙公用台变改造工程"],
                ["县区局：罗定供电局"],
                ["评审类别", "评审项", "评审要点", "本项目是否适用", "扣分标准"],
                ["总体情况", "总体部分（20分）", "设计说明书1.2建设规模智能网关数量校核。", "是", "扣分"],
                ["技术方案", "台区（10分）", "图08 10kV线路走向示意图（改造后）补充标注新建台架变新建电杆规格。", "是", "扣分"],
                ["技术方案", "台区（10分）", "不相关项目规则。", "否", "扣分"],
            ]
            _write_xlsx_sheet(
                tech_dir / "配网工程设计评审技术要点（加益供电所10kV合江线新增配变及黄沙公用台变改造工程）.xlsx",
                "技术要点",
                tech_rows,
            )

            rules_doc = load_review_rules(review_dir, project_code="035352DP24110647")

            self.assertIn("technical_points_excels", rules_doc["source_files"])
            self.assertEqual(len(rules_doc["source_files"]["technical_points_excels"]), 1)
            tech_rules = [item for item in rules_doc["review_rules"] if item["source_type"] == "technical_points"]
            self.assertEqual(len(tech_rules), 2)
            self.assertEqual(tech_rules[0]["source_text"], "设计说明书1.2建设规模智能网关数量校核。")
            self.assertEqual(tech_rules[0]["scope"], "manual")
            self.assertEqual(tech_rules[1]["source_text"], "图08 10kV线路走向示意图（改造后）补充标注新建台架变新建电杆规格。")
            self.assertEqual(tech_rules[1]["scope"], "drawing")

    def test_load_review_rules_accepts_technical_points_subdir_input(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            review_dir = Path(td) / "评审意见"
            tech_dir = review_dir / "评审技术要点"
            tech_dir.mkdir(parents=True, exist_ok=True)

            project_name = "加益供电所10kV合江线新增配变及黄沙公用台变改造工程"
            project_code = "035352DP24110647"

            major_row = [""] * 15
            major_row[0] = "4"
            major_row[1] = project_name
            major_row[2] = project_code
            major_row[6] = "1、设计说明书1.2建设规模智能网关数量校核。"
            major_row[7] = "1、已核实。"
            major_row[10] = "已执行"
            _write_xlsx_sheet(
                review_dir / "附件2：设计和造价主要问题统计表.xlsx",
                "表5 设计和造价主要问题统计表",
                [["序号", "工程名称", "工程编码/项目数"], major_row],
            )

            _write_xlsx_sheet(
                tech_dir / f"配网工程设计评审技术要点（{project_name}）.xlsx",
                "技术要点",
                [
                    ["配网工程设计评审技术要点"],
                    [f"项目名称：{project_name}"],
                    ["评审类别", "评审项", "评审要点", "本项目是否适用", "扣分标准"],
                    ["总体情况", "总体部分（20分）", "设计说明书1.2建设规模智能网关数量校核。", "是", "扣分"],
                ],
            )

            rules_doc = load_review_rules(tech_dir, project_code=project_code)

            self.assertEqual(rules_doc["project_name"], project_name)
            self.assertEqual(Path(rules_doc["review_dir"]), review_dir.resolve())
            self.assertEqual(len(rules_doc["source_files"]["technical_points_excels"]), 1)
            tech_rules = [item for item in rules_doc["review_rules"] if item["source_type"] == "technical_points"]
            self.assertEqual(len(tech_rules), 1)
            self.assertEqual(tech_rules[0]["source_text"], "设计说明书1.2建设规模智能网关数量校核。")

    def test_load_technical_point_rules_prefers_filename_matched_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project_name = "加益供电所10kV合江线新增配变及黄沙公用台变改造工程"
            matching = root / f"配网工程设计评审技术要点（{project_name}）.xls"
            other_1 = root / "配网工程设计评审技术要点（素龙供电所10kV上宁线新增配变及桅杆脚公用台变改造工程）.xls"
            other_2 = root / "配网工程设计评审技术要点（附城所10kV朗溪线石龙台区改建工程）.xls"
            for path in (matching, other_1, other_2):
                path.write_bytes(b"placeholder")

            seen: list[str] = []

            def fake_read_excel_sheets(path: Path) -> list[tuple[str, list[list[str]]]]:
                seen.append(path.name)
                if path != matching:
                    raise AssertionError(f"unexpected workbook load: {path.name}")
                return [
                    (
                        "技术要点",
                        [
                            ["配网工程设计评审技术要点"],
                            [f"项目名称：{project_name}"],
                            ["评审类别", "评审项", "评审要点", "本项目是否适用", "扣分标准"],
                            ["总体情况", "总体部分（20分）", "设计说明书1.2建设规模智能网关数量校核。", "是", "扣分"],
                        ],
                    )
                ]

            with patch("sparkflow.review._read_excel_sheets", side_effect=fake_read_excel_sheets):
                rules = _load_technical_point_rules(
                    (matching, other_1, other_2),
                    project_name=project_name,
                    project_code="",
                )

            self.assertEqual(seen, [matching.name])
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]["source_text"], "设计说明书1.2建设规模智能网关数量校核。")

    def test_load_technical_point_rules_falls_back_to_sheet_content_when_filename_is_generic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "配网工程设计评审技术要点.xls"
            path.write_bytes(b"placeholder")
            project_name = "加益供电所10kV合江线新增配变及黄沙公用台变改造工程"

            with patch(
                "sparkflow.review._read_excel_sheets",
                return_value=[
                    (
                        "技术要点",
                        [
                            ["配网工程设计评审技术要点"],
                            [f"项目名称：{project_name}"],
                            ["评审类别", "评审项", "评审要点", "本项目是否适用", "扣分标准"],
                            ["总体情况", "总体部分（20分）", "设计说明书1.2建设规模智能网关数量校核。", "是", "扣分"],
                        ],
                    )
                ],
            ):
                rules = _load_technical_point_rules((path,), project_name=project_name, project_code="")

            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]["source_text"], "设计说明书1.2建设规模智能网关数量校核。")

    def test_review_audit_writes_document_driven_report(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drawing, review_dir, fixture = _stage_review_fixture(root)
            out = root / "out"

            output = review_audit(
                drawing,
                review_dir,
                out,
                project_code=fixture["project"]["project_code"],
                parse_options=CadParseOptions(dxf_backend="ascii"),
            )

            self.assertTrue(output.drawing_info_json_path.exists())
            self.assertTrue(output.review_rules_json_path.exists())
            self.assertTrue(output.review_report_json_path.exists())
            self.assertTrue(output.review_report_md_path.exists())

            report = json.loads(output.review_report_json_path.read_text(encoding="utf-8"))
            self.assertEqual(report["project_code"], fixture["project"]["project_code"])
            self.assertEqual(report["drawing_info_json_path"], str(output.drawing_info_json_path))
            self.assertEqual(report["review_rules_json_path"], str(output.review_rules_json_path))
            self.assertEqual(
                report["summary"]["placeholder_text_count"],
                fixture["expected"]["placeholder_text_count"],
            )
            self.assertEqual(
                report["summary"]["review_rule_counts"],
                _expected_rule_result_counts(fixture),
            )
            self.assertCountEqual(
                report["summary"]["placeholder_texts"],
                fixture["expected"]["placeholder_texts"],
            )

            results = {item["source_text"]: item["result"] for item in report["review_rule_results"]}
            for text, expected in fixture["expected"]["result_by_text"].items():
                self.assertEqual(results[text], _normalize_expected_rule_result(expected))

    def test_review_audit_can_skip_sparkflow_audit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drawing, review_dir, fixture = _stage_review_fixture(root)
            out = root / "out"

            output = review_audit(
                drawing,
                review_dir,
                out,
                project_code=fixture["project"]["project_code"],
                parse_options=CadParseOptions(dxf_backend="ascii"),
                include_sparkflow_audit=False,
            )

            report = json.loads(output.review_report_json_path.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["sparkflow_audit_skipped"])
            self.assertIsNone(report["sparkflow_report_json_path"])
            self.assertIsNone(report["sparkflow_report_md_path"])
            self.assertIsNone(output.sparkflow_report_json_path)
            self.assertIsNone(output.sparkflow_report_md_path)

    def test_review_audit_infers_project_from_drawing_name_with_technical_points_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drawing, review_dir, fixture = _stage_review_fixture(root)
            project = fixture["project"]
            project_name = str(project["project_name"])
            drawing_named = root / f"{project_name}.dxf"
            drawing.replace(drawing_named)

            tech_dir = review_dir / "评审技术要点"
            _write_xlsx_sheet(
                tech_dir / f"配网工程设计评审技术要点（{project_name}）.xlsx",
                "技术要点",
                [
                    ["配网工程设计评审技术要点"],
                    [f"项目名称：{project_name}"],
                    ["评审类别", "评审项", "评审要点", "本项目是否适用", "扣分标准"],
                    ["总体情况", "总体部分（20分）", "建议补充10kV土建通道走向图。", "是", "扣分"],
                ],
            )

            output = review_audit(
                drawing_named,
                tech_dir,
                root / "out",
                parse_options=CadParseOptions(dxf_backend="ascii"),
                include_sparkflow_audit=False,
            )

            report = json.loads(output.review_report_json_path.read_text(encoding="utf-8"))
            self.assertEqual(report["project_code"], project["project_code"])
            self.assertEqual(report["project_name"], project_name)
            self.assertTrue(report["summary"]["sparkflow_audit_skipped"])
            self.assertEqual(Path(report["review_dir"]), review_dir.resolve())
            self.assertTrue(any(item["source_type"] == "technical_points" for item in report["review_rule_results"]))

    def test_drawing_info_command_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drawing, _, fixture = _stage_review_fixture(root)
            out_json = root / "drawing_info.json"

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "drawing-info",
                        str(drawing),
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
            for text in fixture["expected"]["drawing_info_unique_texts"]:
                self.assertIn(text, drawing_info["unique_texts"])
            self.assertCountEqual(
                drawing_info["placeholder_texts"],
                fixture["expected"]["placeholder_texts"],
            )

    def test_review_pipeline_writes_split_pages_and_rectification_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drawing, review_dir, fixture = _stage_review_fixture(root)
            out = root / "out"

            output = review_pipeline(
                drawing,
                review_dir,
                out,
                project_code=fixture["project"]["project_code"],
                parse_options=CadParseOptions(dxf_backend="ezdxf"),
                include_sparkflow_audit=False,
            )

            self.assertTrue(output.split_manifest_json_path.exists())
            self.assertTrue(output.rectification_checklist_md_path.exists())
            self.assertTrue(output.rectification_checklist_json_path.exists())

            manifest = json.loads(output.split_manifest_json_path.read_text(encoding="utf-8"))
            for sheet_no, expected in fixture["expected"]["page_expectations"].items():
                page = next(item for item in manifest if item["sheet_no"] == int(sheet_no))
                self.assertEqual(page["title"], expected["title"])
                self.assertCountEqual(page["placeholder_texts"], expected["placeholder_texts"])

            checklist_md = output.rectification_checklist_md_path.read_text(encoding="utf-8")
            self.assertIn("整改问题清单", checklist_md)
            self.assertIn(fixture["expected"]["page_expectations"]["3"]["title"], checklist_md)
            self.assertIn(fixture["expected"]["placeholder_texts"][0], checklist_md)

    def test_review_pipeline_command_writes_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drawing, review_dir, fixture = _stage_review_fixture(root)
            out = root / "out"

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "review-pipeline",
                        str(drawing),
                        "--review-dir",
                        str(review_dir),
                        "--out",
                        str(out),
                        "--project-code",
                        fixture["project"]["project_code"],
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

    def test_rectification_checklist_labels_prefer_sheet_no_then_page_seq(self) -> None:
        checklist = build_rectification_checklist(
            {
                "project_code": "P1",
                "project_name": "工程A",
                "input_path": "drawing.dxf",
                "review_dir": "review",
                "summary": {},
                "review_rule_results": [
                    {
                        "rule_id": "technical.1",
                        "result": "failed",
                        "source_text": "补充10kV线路走向示意图",
                        "keywords": ["线路走向示意图", "系统图"],
                        "reply": "",
                        "explanation": "missing",
                    }
                ],
            },
            [
                {
                    "sheet_no": 8,
                    "page_seq": 1,
                    "title": "10kV线路走向示意图",
                    "codes": ["47-ABC-08"],
                    "primary_code": "47-ABC-08",
                    "placeholder_texts": ["FXX"],
                    "texts_path": "page8.texts.json",
                    "png_path": "page8.png",
                    "svg_path": "page8.svg",
                },
                {
                    "sheet_no": None,
                    "page_seq": 2,
                    "title": "系统图（续页）",
                    "codes": ["47-ABC-D01"],
                    "primary_code": "47-ABC-D01",
                    "placeholder_texts": [],
                    "texts_path": "page2.texts.json",
                    "png_path": "page2.png",
                    "svg_path": "page2.svg",
                },
            ],
        )

        self.assertEqual(checklist["page_issues"][0]["page_label"], "8 10kV线路走向示意图")
        self.assertEqual(checklist["review_issues"][0]["related_pages"], ["8 10kV线路走向示意图", "2 系统图（续页）"])

    def test_split_review_pages_supports_qingneng_frame_names(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drawing_path = root / "qingneng_layout.dxf"
            _write_qingneng_split_review_dxf(drawing_path)

            manifest_path = split_review_pages(drawing_path, root / "split")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(manifest), 3)
            self.assertEqual(sum(1 for item in manifest if item["kind"] == "frame_a4l1v"), 1)
            self.assertEqual(sum(1 for item in manifest if item["kind"] == "frame_a3l1hfl"), 2)

            line_page = next(item for item in manifest if item["title"] == "10kV线路走向示意图（改造后）")
            box_page = next(item for item in manifest if item["title"] == "100kVA-200kVA变压器配电箱系统图（3P）")

            self.assertEqual(line_page["sheet_no"], 8)
            self.assertEqual(box_page["sheet_no"], 26)
            self.assertTrue(Path(line_page["svg_path"]).exists())
            self.assertTrue(Path(box_page["texts_path"]).exists())

    def test_split_review_pages_prefers_qingneng_title_block_code_and_title(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drawing_path = root / "qingneng_title_block.dxf"
            _write_qingneng_title_block_dxf(drawing_path)

            manifest_path = split_review_pages(drawing_path, root / "split")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(manifest), 2)

            page1 = manifest[0]
            page2 = manifest[1]

            self.assertEqual(page1["primary_code"], "035352DY23020004-D01")
            self.assertEqual(page1["sheet_no"], None)
            self.assertEqual(page1["page_seq"], 1)
            self.assertEqual(page1["title_part_no"], 1)
            self.assertEqual(page1["title_part_total"], 3)
            self.assertEqual(page1["title"], "加益变电站10kV合江线单线图1/3（改造前）")
            self.assertEqual(page1["slug"], "01_035352DY23020004-D01")

            self.assertEqual(page2["primary_code"], "035352DY23020004-D01")
            self.assertEqual(page2["sheet_no"], None)
            self.assertEqual(page2["page_seq"], 2)
            self.assertEqual(page2["title_part_no"], 2)
            self.assertEqual(page2["title_part_total"], 3)
            self.assertEqual(page2["title"], "加益变电站10kV合江线单线图2/3（改造前）")
            self.assertEqual(page2["slug"], "02_035352DY23020004-D01")

            self.assertEqual(page1["placeholder_texts"], [])
            self.assertEqual(page2["placeholder_texts"], [])


def _review_fixture_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "review_baseline" / "030451DY26030001" / "fixture.json"


def _load_review_fixture() -> dict[str, object]:
    return json.loads(_review_fixture_path().read_text(encoding="utf-8"))


def _stage_review_fixture(root: Path) -> tuple[Path, Path, dict[str, object]]:
    fixture = _load_review_fixture()
    review_dir = root / "评审意见"
    drawing_path = root / "review_baseline.dxf"
    _write_review_workbooks_from_fixture(review_dir, fixture)
    _write_split_review_dxf_from_fixture(drawing_path, fixture)
    return drawing_path, review_dir, fixture


def _expected_rule_result_counts(fixture: dict[str, object]) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "manual_review": 0}
    for value in fixture["expected"]["result_by_text"].values():
        counts[_normalize_expected_rule_result(str(value))] += 1
    return counts


def _normalize_expected_rule_result(value: str) -> str:
    mapping = {
        "evidence_found": "passed",
        "not_found_in_drawing": "failed",
        "manual_required": "manual_review",
    }
    return mapping[value]


def _write_review_workbooks_from_fixture(review_dir: Path, fixture: dict[str, object]) -> None:
    review = fixture["review"]
    project = fixture["project"]
    project_summary = review["project_summary"]
    major_issues = review["major_issues"]
    workbook_files = review["workbook_files"]

    summary_row = [""] * 35
    summary_row[1] = project["project_name"]
    summary_row[2] = project["project_code"]
    summary_row[3] = project_summary["total_investment"]
    summary_row[4] = project_summary["viability_estimate"]
    summary_row[5] = project_summary["submitted_budget"]
    summary_row[6] = project_summary["approved_budget"]
    summary_row[8] = project_summary["project_type"]
    summary_row[33] = project_summary["standard_design_diff"]

    major_row = [""] * 13
    major_row[2] = project["project_name"]
    major_row[3] = project["project_code"]
    major_row[6] = major_issues["technical_opinion"]
    major_row[7] = major_issues["technical_expert"]
    major_row[8] = major_issues["technical_reply"]
    major_row[9] = major_issues["cost_opinion"]
    major_row[10] = major_issues["cost_expert"]
    major_row[11] = major_issues["cost_reply"]
    major_row[12] = major_issues["execution_status"]

    _write_xlsx_sheet(
        review_dir / workbook_files["summary"],
        "表4.2 评审情况明细表",
        [["序号", "工程名称", "工程编号"], summary_row],
    )
    _write_xlsx_sheet(
        review_dir / workbook_files["major_issues"],
        "表5 设计和造价主要问题统计表",
        [["序号", "批次", "工程名称", "工程编号"], major_row],
    )


def _write_split_review_dxf_from_fixture(path: Path, fixture: dict[str, object]) -> None:
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 10))

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

    page_h_block = doc.blocks.new("frame_a3l1hfl_（新）珠海电力-a2a3a4-阶段无设计")
    page_h_block.add_lwpolyline(
        [(-25, -5), (395, -5), (395, 292), (-25, 292)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )
    page_h_block.add_lwpolyline(
        [(0, 0), (370, 0), (370, 250), (0, 250)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )

    page_v_block = doc.blocks.new("frame_a3l1vl_（新）珠海电力-a2a3a4-阶段无设计")
    page_v_block.add_lwpolyline(
        [(-5, -5), (292, -5), (292, 415), (-5, 415)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )
    page_v_block.add_lwpolyline(
        [(0, 0), (250, 0), (250, 370), (0, 370)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )

    layout = doc.layouts.get("Layout1")
    layout.add_blockref(
        "frame_a4l1v_（新）目录无设计",
        (100, 500),
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )
    y = 700.0
    for entry in fixture["drawing"]["directory_entries"]:
        layout.add_text(
            entry["code"],
            dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (120, y), "height": 6},
        )
        layout.add_text(
            entry["title"],
            dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (180, y), "height": 6},
        )
        y -= 12.0

    start_x = 420.0
    start_y = 500.0
    step_x = 520.0
    step_y = 470.0
    for index, page in enumerate(fixture["drawing"]["pages"]):
        row = index // 3
        col = index % 3
        insert_x = start_x + col * step_x
        insert_y = start_y - row * step_y
        if page["kind"] == "frame_a3l1vl":
            block_name = "frame_a3l1vl_（新）珠海电力-a2a3a4-阶段无设计"
            text_x = insert_x + 30.0
            text_y = insert_y + 350.0
        else:
            block_name = "frame_a3l1hfl_（新）珠海电力-a2a3a4-阶段无设计"
            text_x = insert_x + 50.0
            text_y = insert_y + 230.0
        layout.add_blockref(
            block_name,
            (insert_x, insert_y),
            dxfattribs={"layer": "YFLayer_FrameLayer"},
        )
        layout.add_text(
            page["code"],
            dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (insert_x + 30, insert_y + 15), "height": 6},
        )
        for text in page["texts"]:
            layout.add_text(
                text,
                dxfattribs={"layer": "0", "insert": (text_x, text_y), "height": 8},
            )
            text_y -= 12.0
        layout.add_line((insert_x + 40, insert_y + 30), (insert_x + 220, insert_y + 30), dxfattribs={"layer": "0"})

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)


def _write_qingneng_split_review_dxf(path: Path) -> None:
    doc = ezdxf.new(setup=True)

    directory_block = doc.blocks.new("擎能A4竖")
    directory_block.add_lwpolyline(
        [(-25, -37), (185, -37), (185, 260), (-25, 260)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )

    page_block = doc.blocks.new("擎能A3横")
    page_block.add_lwpolyline(
        [(-25, -5), (395, -5), (395, 292), (-25, 292)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )

    layout = doc.layouts.get("Layout1")
    layout.dxf.name = "布局"
    layout.add_blockref("擎能A4竖", (100, 500), dxfattribs={"layer": "YFLayer_FrameLayer"})
    layout.add_text(
        "47-ABC-08",
        dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (120, 700), "height": 6},
    )
    layout.add_text(
        "10kV线路走向示意图（改造后）",
        dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (180, 700), "height": 6},
    )
    layout.add_text(
        "47-ABC-26",
        dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (120, 688), "height": 6},
    )
    layout.add_text(
        "100kVA-200kVA变压器配电箱系统图（3P）",
        dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (180, 688), "height": 6},
    )

    pages = [
        ((420, 500), "47-ABC-08", "10kV线路走向示意图（改造后）", ["终端位置：xxx台架变"]),
        ((960, 500), "47-ABC-26", "100kVA-200kVA变压器配电箱系统图（3P）", ["SH15-M-XXXkVA"]),
    ]
    for insert, code, title, texts in pages:
        insert_x, insert_y = insert
        layout.add_blockref("擎能A3横", insert, dxfattribs={"layer": "YFLayer_FrameLayer"})
        layout.add_text(
            code,
            dxfattribs={"layer": "YFLayer_FrameAttribute", "insert": (insert_x + 30, insert_y + 15), "height": 6},
        )
        layout.add_text(
            title,
            dxfattribs={"layer": "0", "insert": (insert_x + 50, insert_y + 230), "height": 8},
        )
        text_y = insert_y + 210
        for text in texts:
            layout.add_text(
                text,
                dxfattribs={"layer": "0", "insert": (insert_x + 50, text_y), "height": 8},
            )
            text_y -= 12
        layout.add_line(
            (insert_x + 40, insert_y + 30),
            (insert_x + 220, insert_y + 30),
            dxfattribs={"layer": "0"},
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)


def _write_qingneng_title_block_dxf(path: Path) -> None:
    doc = ezdxf.new(setup=True)

    page_block = doc.blocks.new("擎能A3横")
    page_block.add_lwpolyline(
        [(-25, -5), (395, -5), (395, 292), (-25, 292)],
        close=True,
        dxfattribs={"layer": "YFLayer_FrameLayer"},
    )

    layout = doc.layouts.get("Layout1")
    layout.dxf.name = "布局"
    pages = [
        ((1100.0, 2847.3), "加益变电站10kV合江线单线图1/3（改造前）"),
        ((1570.0, 2847.3), "加益变电站10kV合江线单线图2/3（改造前）"),
    ]
    for insert_x, insert_y, title in [(x, y, title) for (x, y), title in pages]:
        layout.add_blockref("擎能A3横", (insert_x, insert_y), dxfattribs={"layer": "YFLayer_FrameLayer"})

        title_block_texts = [
            ("加益供电所10kV合江线新增配变及黄沙公用台变改造", insert_x + 304.0, insert_y + 37.7),
            ("工程", insert_x + 383.2, insert_y + 37.3),
            (title, insert_x + 306.4, insert_y + 21.1),
            ("035352DY23020004-D01", insert_x + 280.8, insert_y + 7.1),
            ("图 号", insert_x + 263.0, insert_y + 7.1),
            ("设计阶段", insert_x + 359.7, insert_y + 7.0),
            ("施工图", insert_x + 359.2, insert_y + 7.2),
            ("会", insert_x + 6.1, insert_y + 285.8),
            ("签", insert_x + 6.0, insert_y + 278.3),
        ]
        for text, x, y in title_block_texts:
            layout.add_text(text, dxfattribs={"layer": "0", "insert": (x, y), "height": 6})

        body_texts = [
            ("CT-70-70", insert_x + 150.0, insert_y + 180.0),
            ("GJ-35--GJ-75", insert_x + 190.0, insert_y + 165.0),
            ("原有10kV架空线路", insert_x + 320.0, insert_y + 286.0),
        ]
        for text, x, y in body_texts:
            layout.add_text(text, dxfattribs={"layer": "0", "insert": (x, y), "height": 8})

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
