import pytest
import os
import shutil
import sys
import argparse
from src.utils.config_loader import ConfigLoader

# 全局常量
BASELINE_FILE = "data/baseline_scores.json"


def preserve_history(temp_dir):
    """
    备份 Allure 的历史数据
    Allure 的历史趋势保存在 report/history 目录下，需要迁移到 temp/history 才能在下一次生成时生效
    """
    history_src = os.path.join(temp_dir, "../html/history")  # 假设 html 在 temp 同级目录
    history_dst = os.path.join(temp_dir, "history")

    if os.path.exists(history_src):
        # 如果 temp/history 已存在先删除，防止冲突
        if os.path.exists(history_dst):
            shutil.rmtree(history_dst)

        # 复制历史数据到本次运行的临时目录
        shutil.copytree(history_src, history_dst)
        print(f"[*] 已加载历史趋势数据: {history_src} -> {history_dst}")
    else:
        print("[i] 未发现历史趋势数据,本次将作为首次运行")


def clean_old_reports(temp_dir, html_dir):
    """清理旧的测试报告，但保留必要的目录结构"""
    # 注意：不要直接删除 temp_dir，否则刚复制进去的 history 也没了
    # 我们可以只删除 temp_dir 下除 history 以外的文件，或者依靠 --clean-alluredir (pytest参数)

    # 这里只清理 HTML 输出目录，TEMP 目录交给 pytest 的 --clean-alluredir 处理
    if os.path.exists(html_dir):
        shutil.rmtree(html_dir)

    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(html_dir, exist_ok=True)


def build_pytest_args(config):
    """根据配置文件组装 Pytest 命令行参数"""
    runner_conf = config.get("runner")

    args = [
        runner_conf.get("test_path", "src/tests/"),
        f"--alluredir={runner_conf.get('report_temp_dir')}",
        "--clean-alluredir",  # Pytest 会自动清理 temp 目录
        "-v",
        "-s"
    ]

    # 并发配置
    concurrency = runner_conf.get("concurrency", 1)
    if concurrency != 1:
        args.extend(["-n", str(concurrency)])

    # 重复执行
    repeat = runner_conf.get("repeat", 1)
    if repeat > 1:
        args.extend([f"--count={repeat}"])

    return args


def generate_report(temp_dir, html_dir):
    """生成报告"""
    print("[*] 正在生成 HTML 测试报告...")
    # 注意:不要加 --clean,否则会把我们手动拷进去的 history 删掉
    # 但为了保证 html 目录干净,我们在 clean_old_reports 里已经删过 html_dir 了
    exit_code = os.system(f"allure generate {temp_dir} -o {html_dir} --clean")
    if exit_code == 0:
        print(f"[OK] 报告生成成功: {os.path.abspath(html_dir)}/index.html")
    else:
        print("[!] 报告生成失败")


def main():
    # 1. 解析命令行参数
    parser = argparse.ArgumentParser(description="AI Agent 自动化测试启动器")
    parser.add_argument("--save-baseline", action="store_true", help="将本次测试结果保存为baseline")
    parser.add_argument("--baseline-version", type=str, default="baseline", help="Baseline版本名称")
    parser.add_argument("--compare-baseline", type=str, help="与指定baseline版本对比")
    parser.add_argument("--baseline-description", type=str, default="", help="Baseline描述信息")
    cli_args = parser.parse_args()

    # 2. 加载配置
    try:
        config = ConfigLoader("config/config.yaml")
    except Exception as e:
        print(f"[X] 配置文件加载失败: {e}")
        sys.exit(1)

    runner_conf = config.get("runner")
    temp_dir = runner_conf.get("report_temp_dir", "./reports/temp")
    html_dir = runner_conf.get("report_html_dir", "./reports/html")

    # 3. 设置环境变量(供 pytest hooks 使用)
    if cli_args.save_baseline:
        os.environ["SAVE_BASELINE"] = "true"
        os.environ["BASELINE_VERSION"] = cli_args.baseline_version
        if cli_args.baseline_description:
            os.environ["BASELINE_DESCRIPTION"] = cli_args.baseline_description
        print(f"[!] 本次运行将保存为 baseline: {cli_args.baseline_version}")
    
    if cli_args.compare_baseline:
        os.environ["COMPARE_BASELINE"] = cli_args.compare_baseline
        print(f"[*] 将与 baseline 对比: {cli_args.compare_baseline}")

    # 4. 清理旧报告
    clean_old_reports(temp_dir, html_dir)

    # 5. 执行 Pytest
    pytest_args = build_pytest_args(config)
    print(f"[>] 开始执行测试...")
    exit_code = pytest.main(pytest_args)

    # 6. 注入历史趋势数据
    preserve_history(temp_dir)

    # 7. 生成报告
    generate_report(temp_dir, html_dir)
    
    # 8. 清理环境变量
    for key in ["SAVE_BASELINE", "BASELINE_VERSION", "BASELINE_DESCRIPTION", "COMPARE_BASELINE"]:
        if key in os.environ:
            del os.environ[key]

    sys.exit(exit_code)


if __name__ == "__main__":
    main()