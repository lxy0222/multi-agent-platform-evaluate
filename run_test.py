import pytest
import os
import shutil
import sys
from utils.config_loader import ConfigLoader


def clean_old_reports(temp_dir, html_dir):
    """清理旧的测试报告，防止历史数据干扰"""
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    if os.path.exists(html_dir):
        shutil.rmtree(html_dir)

    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(html_dir, exist_ok=True)
    print(f"🧹 已清理旧报告目录: {temp_dir}, {html_dir}")


def build_pytest_args(config):
    """根据配置文件组装 Pytest 命令行参数"""
    runner_conf = config.get("runner")

    # 基础参数
    args = [
        runner_conf.get("test_path", "tests/"),  # 测试用例目录
        f"--alluredir={runner_conf.get('report_temp_dir')}",  # Allure 数据目录
        "--clean-alluredir",  # 清理 Allure 历史数据
        "-v",  # 详细模式
        "-s"  # 允许控制台输出 print 内容
    ]

    # 并发配置 (pytest-xdist)
    concurrency = runner_conf.get("concurrency", 1)
    if concurrency != 1:
        args.extend(["-n", str(concurrency)])
        # 分布式运行时，保证日志按顺序输出 (可选)
        # args.append("--dist=loadscope")

    # 重试配置 (pytest-rerunfailures)
    reruns = runner_conf.get("reruns", 0)
    if reruns > 0:
        args.extend([
            f"--reruns={reruns}",
            f"--reruns-delay={runner_conf.get('rerun_delay', 1)}"
        ])

    # 重复执行配置 (pytest-repeat)
    repeat = runner_conf.get("repeat", 1)
    if repeat > 1:
        args.extend([
            f"--count={repeat}",
        ])

    return args


def generate_report(temp_dir, html_dir):
    """调用 Allure 命令行生成 HTML 报告"""
    # 注意：这需要系统环境变量中安装了 allure 命令行工具
    # Mac: brew install allure
    # Windows: scoop install allure
    print("📊 正在生成 HTML 测试报告...")
    try:
        # os.system 返回 0 表示成功
        exit_code = os.system(f"allure generate {temp_dir} -o {html_dir} --clean")
        if exit_code == 0:
            print(f"✅ 报告生成成功: {os.path.abspath(html_dir)}/index.html")
        else:
            print("⚠️ 报告生成失败，请检查是否安装了 allure 命令行工具")
    except Exception as e:
        print(f"⚠️ 生成报告时发生错误: {e}")


def open_report(html_dir):
    """自动打开报告"""
    print("🚀 正在打开浏览器预览...")
    os.system(f"allure open {html_dir}")


def main():
    # 1. 加载配置
    try:
        config = ConfigLoader("config/config.yaml")
    except Exception as e:
        print(f"❌ 配置文件加载失败: {e}")
        sys.exit(1)

    runner_conf = config.get("runner")
    temp_dir = runner_conf.get("report_temp_dir", "./reports/temp")
    html_dir = runner_conf.get("report_html_dir", "./reports/html")

    # 2. 环境清理
    clean_old_reports(temp_dir, html_dir)

    # 3. 组装参数
    pytest_args = build_pytest_args(config)
    print(f"▶️ 开始执行测试，参数: {' '.join(pytest_args)}")

    # 4. 执行 Pytest
    # pytest.main 返回值：0=Pass, 1=Fail, 2=Interrupted, etc.
    exit_code = pytest.main(pytest_args)

    # 5. 生成报告
    generate_report(temp_dir, html_dir)

    # 6. 自动打开 (仅在配置开启且非 CI 环境下)
    # 在 CI/CD 中通常通过环境变量 CI=true 来判断
    is_ci = os.getenv("CI") == "true"
    if runner_conf.get("auto_open_report") and not is_ci:
        # 注意：allure open 会启动一个本地 web 服务，阻塞进程
        # 如果只想生成不打开，可以注释掉这行
        # 或者使用 subprocess.Popen 异步打开
        # 这里演示同步打开
        # open_report(html_dir)
        pass

        # 返回退出码给操作系统 (用于 CI/CD 判断构建成功/失败)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()