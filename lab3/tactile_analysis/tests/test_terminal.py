"""Check Chinese terminal behavior separately from the saved data contract."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import unittest

from tactile_analysis.cli import main
from tactile_analysis.convert_recording import main as convert_main
from tactile_analysis.terminal import error_text


ROOT = Path(__file__).parents[1]


class TerminalTest(unittest.TestCase):
    def invoke(self, function, args, code=0):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            if code == 0:
                self.assertEqual(function(args), 0)
            else:
                with self.assertRaises(SystemExit) as caught:
                    function(args)
                self.assertEqual(caught.exception.code, code)
        return stdout.getvalue(), stderr.getvalue()

    def fixture(self):
        import test_convert_recording as module
        fixture = module.ConvertRecordingTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_all_script_help_is_chinese_and_readable_without_package_install(self):
        for name in ("analyze_recording.py", "convert_recording_to_hdf5.py", "audit_recording.py",
                     "convert_npz_to_hdf5.py", "make_demo_hdf5.py", "make_physical_demo.py"):
            with self.subTest(script=name):
                result = subprocess.run([sys.executable, str(ROOT / "examples" / name), "--help"],
                                        cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("用法：", result.stdout)
                self.assertIn("显示帮助信息并退出", result.stdout)
                for english in ("usage:", "positional arguments:", "options:", "show this help message"):
                    self.assertNotIn(english, result.stdout)

    def test_argument_failures_are_chinese(self):
        cases = [([], "缺少必填参数"), (["missing.zip", "--unknown"], "无法识别的参数"),
                 (["missing.zip", "--smooth-window", "x"], "需要整数"),
                 (["missing.zip", "--contact-threshold", "x"], "需要数值"),
                 (["missing.zip", "--force-unit", "N"], "无效取值"),
                 (["missing.zip", "--heatmap-frame", "bad"], "热力图帧必须"),
                 (["missing.zip", "--contact-threshold"], "需要一个参数值")]
        for args, expected in cases:
            with self.subTest(args=args):
                _, error = self.invoke(main, args, 2)
                self.assertIn("参数错误", error)
                self.assertIn(expected, error)
                self.assertNotIn("usage:", error)
                self.assertNotIn("Traceback", error)

    def test_dependency_errors_keep_chinese_paths_without_english_messages(self):
        self.assertEqual(error_text(FileNotFoundError(2, "No such file or directory", "中文文件.zip")),
                         "找不到文件或目录：中文文件.zip")
        self.assertEqual(error_text(PermissionError(13, "Permission denied", "中文目录")),
                         "没有文件读写权限：中文目录")
        self.assertEqual(error_text(json.JSONDecodeError("Expecting value", "?", 0)),
                         "JSON 格式错误：第 1 行，第 1 列")

    def test_default_quality_summary_is_chinese_and_json_is_opt_in(self):
        fixture = self.fixture()
        archive = fixture.make_zip()
        text, _ = self.invoke(main, [str(archive), "--list-trials", "--quiet"])
        self.assertIn("左手（选择标识：left）", text)
        self.assertIn("右手（选择标识：right）", text)
        self.assertIn("数据包有效率", text)
        self.assertIn("不能据此认定真实接触", text)
        self.assertFalse(fixture.output.exists())
        text, _ = self.invoke(main, [str(archive), "--list-trials", "--quiet", "--json"])
        self.assertEqual(json.loads(text)["verified_npz_count"], 6)

    def test_chinese_raw_summary_does_not_change_saved_report(self):
        fixture = self.fixture()
        output = fixture.base / "chinese-raw"
        text, progress = self.invoke(main, [str(fixture.make_zip()), "--allow-unverified", "--output-dir", str(output)])
        self.assertIn("分析完成，结果目录", text)
        self.assertIn("未验证原始信号诊断", text)
        self.assertIn("左手", text)
        self.assertIn("右手", text)
        self.assertIn("原始波形已生成", progress)
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["summaries"]["left"]["analysis_mode"], "unverified_raw_diagnostic")
        self.assertIn("active_taxel_count_mean", report["summaries"]["left"])

    def test_chinese_physical_summary_labels_synthetic_calibration(self):
        fixture = self.fixture()
        spec = importlib.util.spec_from_file_location("physical_terminal_demo", ROOT / "examples/make_physical_demo.py")
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        trial, calibration = demo.make_demo(fixture.base / "demo")
        text, _ = self.invoke(main, [str(trial), "--trial", "left", "--calibration", str(calibration),
                                    "--output-dir", str(fixture.base / "physical-cn"), "--quiet"])
        self.assertIn("标定来源：合成练习数据", text)
        self.assertIn("接触面积峰值：6 mm²", text)
        self.assertIn("法向力标量和峰值：6 N", text)
        self.assertIn("接触压力峰值：1.5e+06 Pa", text)

    def test_conversion_summary_and_optional_json(self):
        fixture = self.fixture()
        archive = fixture.make_zip()
        text, _ = self.invoke(convert_main, [str(archive), str(fixture.base / "cn.h5")])
        self.assertIn("转换完成", text)
        self.assertIn("已回读核对字段数组", text)
        self.assertIn("左手触觉帧数：4", text)
        text, _ = self.invoke(convert_main, [str(archive), str(fixture.base / "json.h5"), "--json"])
        self.assertEqual(json.loads(text)["source_npz_count"], 6)

    def test_missing_input_reports_chinese_without_traceback(self):
        for function, args in ((main, ["/missing/不存在.zip", "--quiet"]),
                               (convert_main, ["/missing/不存在.zip", "/tmp/unused-output.h5"])):
            with self.subTest(function=function.__module__):
                _, error = self.invoke(function, args, 1)
                self.assertIn("找不到文件或目录", error)
                self.assertNotIn("No such file", error)
                self.assertNotIn("Traceback", error)
