import pandas as pd
import os
import json
import openpyxl

def load_excel_cases(file_path: str) -> list:
    """
    读取 Excel 测试用例文件，并转换为字典列表。

    Args:
        file_path: Excel 文件路径 (.xlsx 或 .csv)

    Returns:
        list: 包含每一行测试数据的字典列表
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"测试数据文件未找到: {file_path}")

    try:
        # 判断文件类型读取
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path, engine='openpyxl')

        # 1. 数据清洗：将 Pandas 的 NaN (空值) 替换为 Python 的 None 或空字符串
        # 否则传入 Dify API 时会报错
        df = df.where(pd.notnull(df), None)

        # 2. 转换为字典列表
        cases = df.to_dict(orient='records')

        # 3. 特殊处理：如果 Excel 里有 JSON 字符串列（比如模拟的 MCP 返回数据），
        # 在这里尝试将其解析为对象，方便后续使用
        for case in cases:
            # 示例：如果你有一列叫 Mock_JSON_Data
            if 'Mock_JSON_Data' in case and case['Mock_JSON_Data']:
                try:
                    if isinstance(case['Mock_JSON_Data'], str):
                        case['Mock_JSON_Data'] = json.loads(case['Mock_JSON_Data'])
                except json.JSONDecodeError:
                    print(f"[Warning] Case {case.get('Case_ID')} 的 JSON 数据解析失败")

        print(f"成功加载 {len(cases)} 条测试用例。")
        return cases

    except Exception as e:
        raise RuntimeError(f"读取测试文件失败: {str(e)}")


# 简单测试一下
if __name__ == "__main__":
    # 假设你当前目录下有个 dummy.xlsx
    print(load_excel_cases("../data/golden_dataset.csv"))
    pass