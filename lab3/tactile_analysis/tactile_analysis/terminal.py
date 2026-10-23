"""中文终端界面；磁盘报告和可选 JSON 输出仍使用原有数据字段。"""

import argparse
import json
import re
import sys
import zipfile


class ChineseHelpFormatter(argparse.HelpFormatter):
    def _format_usage(self, usage, actions, groups, prefix):
        return super()._format_usage(usage, actions, groups, prefix or "用法：")


class ChineseArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", ChineseHelpFormatter)
        kwargs.setdefault("add_help", False)
        super().__init__(*args, **kwargs)
        self._positionals.title = "位置参数"
        self._optionals.title = "可选参数"
        self.add_argument("-h", "--help", action="help", help="显示帮助信息并退出")

    def _get_value(self, action, arg_string):
        try:
            return super()._get_value(action, arg_string)
        except argparse.ArgumentError as exc:
            if exc.message.startswith("invalid "):
                kind = {int: "整数", float: "数值"}.get(action.type, "有效值")
                raise argparse.ArgumentError(action, f"需要{kind}，实际收到：{arg_string!r}") from exc
            raise

    def _check_value(self, action, value):
        if action.choices is not None and value not in action.choices:
            raise argparse.ArgumentError(action, f"无效取值 {value!r}；可选值：{', '.join(map(str, action.choices))}")

    def error(self, message):
        for original, chinese in (
            ("the following arguments are required:", "缺少必填参数："),
            ("unrecognized arguments:", "无法识别的参数："),
            ("expected one argument", "需要一个参数值"),
            ("expected at least one argument", "至少需要一个参数值"),
            ("expected at most one argument", "最多接受一个参数值"),
            ("ambiguous option:", "参数缩写不明确："),
            ("could match", "可能匹配"),
            ("not allowed with argument", "不能与以下参数同时使用："),
        ):
            message = message.replace(original, chinese)
        message = re.sub(r"^argument (.+?): ", r"参数 \1：", message)
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}：参数错误：{message}\n")


def error_text(exc):
    """把依赖库的常见异常也转换为中文，保留文件名和字段标识符。"""
    text = str(exc)
    if isinstance(exc, FileNotFoundError):
        return f"找不到文件或目录：{exc.filename or '请检查输入路径'}"
    if isinstance(exc, PermissionError):
        return f"没有文件读写权限：{exc.filename or '请检查输入和输出路径'}"
    if isinstance(exc, json.JSONDecodeError):
        return f"JSON 格式错误：第 {exc.lineno} 行，第 {exc.colno} 列"
    if isinstance(exc, zipfile.BadZipFile):
        return "ZIP 文件已损坏，或输入文件不是有效的 ZIP 压缩包"
    if isinstance(exc, UnicodeError):
        return "文本文件编码无效，请使用 UTF-8 编码的 JSON、JSONL 或元数据文件"
    if re.search(r"[\u3400-\u9fff]", text) and getattr(exc, "errno", None) is None:
        return text
    if isinstance(exc, FileExistsError):
        return f"输出已存在，请选择新的输出路径：{exc.filename or '请检查输出参数'}"
    if isinstance(exc, KeyError):
        return f"缺少必需的字段、数组或文件：{exc.args[0]}"
    if isinstance(exc, ImportError):
        return f"缺少运行依赖：{getattr(exc, 'name', None) or '请按 README 安装依赖'}"
    if isinstance(exc, IndexError):
        return "所选帧或数组索引超出范围，请检查帧号和输入数组形状"
    if isinstance(exc, OSError):
        return f"无法读取或写入文件，请检查路径、权限和文件格式：{exc.filename or '请检查输入和输出文件'}"
    return "数据格式或参数不符合要求，请检查输入文件、数组形状和参数取值"


def hand_name(name):
    return {"left": "左手", "right": "右手"}.get(name, f"数据组 {name}")


def number(value, suffix=""):
    return "无可用值" if value is None else f"{value:.6g}{suffix}"


def print_quality(info):
    print(f"输入文件：{info['source']}")
    print(f"已通过哈希校验的 NPZ 分块：{info['verified_npz_count']}")
    for row in info["trials"]:
        print(f"\n{hand_name(row['trial'])}（选择标识：{row['trial']}）：")
        print(f"  帧数：{row['frames']}；每帧触觉点数：{row['taxels']}")
        print(f"  时间跨度：{number(row['duration_s'], ' 秒')}；平均采样率：{number(row['rate_hz'], ' Hz')}")
        for key, label in (("packet_valid_fraction", "数据包有效率"), ("sample_valid_fraction", "样本有效率")):
            value = row[key]
            print(f"  {label}：{number(value * 100 if value is not None else None, '%')}")
        print(f"  曾验证有效的触觉点数：{number(row['verified_taxels'])}")
        if row["unverified"]:
            print("  有效性检查未全部通过；原始信号诊断需显式添加 --allow-unverified，不能据此认定真实接触。")


def print_analysis(answer):
    print(f"分析完成，结果目录：{answer['output_dir']}")
    physical = "summary" in answer
    summaries = {"物理分析": answer["summary"]} if physical else answer["report"]["summaries"]
    for name, summary in summaries.items():
        print(f"\n{name if physical else hand_name(name)}：")
        print(f"  帧数：{summary['n_frames']}")
        if physical:
            source = "合成练习数据" if summary.get("calibration_source_kind") == "synthetic_demo" else "实测标定文件"
            print(f"  标定来源：{source}")
            for key, label, unit in (("contact_area_mm2_peak", "接触面积峰值", " mm²"),
                                     ("normal_force_sum_n_peak", "法向力标量和峰值", " N"),
                                     ("peak_pressure_pa", "接触压力峰值", " Pa")):
                if key in summary:
                    print(f"  {label}：{number(summary[key], unit)}")
        else:
            mode = "未验证原始信号诊断" if summary.get("analysis_mode") == "unverified_raw_diagnostic" else "原始信号分析"
            print(f"  分析模式：{mode}")
            print(f"  原始模长阈值：{number(summary['contact_threshold'])}")
            print(f"  超阈值触觉点数：平均 {number(summary['active_taxel_count_mean'])}，最大 {summary['active_taxel_count_peak']}")
            print("  上述计数与幅值不等于经标定的接触面积、物理力或压力。")
    print("\n图表和数据文件已保存；文件中的 JSON/CSV 字段保持原有格式。")


def print_conversion(result):
    print(f"转换完成：{result['output']}")
    print(f"输入文件：{result['source']}")
    print(f"已校验 NPZ 分块：{result['source_npz_count']}；已回读核对字段数组：{result['verified_field_arrays']}")
    for side, count in result["tactile_frames"].items():
        print(f"{hand_name(side)}触觉帧数：{count}")
    print(f"温度事件：{result['temperature_events']} 条；温度读数：{result['temperature_readings']} 个")
    print("原始整数值、有效性标记和各数据流独立时间戳已保留。")
