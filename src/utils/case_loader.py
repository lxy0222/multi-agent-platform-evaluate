"""
统一的测试用例加载器
支持加载不同格式的CSV文件，并转换为统一的数据模型
"""
import os
import json
import csv
from typing import List, Dict, Any, Optional
from src.utils.test_case_model import UnifiedTestCase, TestCaseType
from src.utils.config_loader import ConfigLoader


class CaseLoader:
    """测试用例加载器"""
    
    def __init__(self, data_dir: str = "data"):
        """
        初始化加载器

        Args:
            data_dir: 测试数据目录（相对于项目根目录）
        """
        # 如果是相对路径，转换为绝对路径
        if not os.path.isabs(data_dir):
            # 获取当前文件所在目录（utils目录）
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 项目根目录是utils的上一级
            project_root = os.path.dirname(current_dir)
            # 拼接data目录
            self.data_dir = os.path.join(project_root, data_dir)
        else:
            self.data_dir = data_dir

        self.supported_formats = {
            "golden_dataset": self._parse_golden_dataset,
            "xiaofang_fz_cases": self._parse_xiaofang_fz_cases,
            "exports": self._parse_exports_format,
            "default": self._parse_default_format
        }
    
    def load_cases(
        self, 
        file_path: str,
        case_filter: Optional[Dict[str, Any]] = None
    ) -> List[UnifiedTestCase]:
        """
        加载测试用例
        
        Args:
            file_path: CSV文件路径（相对或绝对路径）
            case_filter: 过滤条件，如 {"tags": ["follow_up"], "enabled": True}
        
        Returns:
            统一格式的测试用例列表
        """
        # 处理路径
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.data_dir, file_path)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"测试数据文件未找到: {file_path}")
        
        # 读取CSV
        raw_cases = self._read_csv(file_path)
        
        # 识别格式并解析
        parser = self._identify_parser(file_path, raw_cases)
        unified_cases = parser(raw_cases)
        
        # 应用过滤器
        if case_filter:
            unified_cases = self._apply_filter(unified_cases, case_filter)
        
        print(f"✅ 成功加载 {len(unified_cases)} 条测试用例 (来源: {os.path.basename(file_path)})")
        return unified_cases
    
    def load_multiple_files(
        self,
        file_patterns: List[str],
        case_filter: Optional[Dict[str, Any]] = None
    ) -> List[UnifiedTestCase]:
        """
        加载多个测试用例文件
        
        Args:
            file_patterns: 文件路径列表或通配符
            case_filter: 过滤条件
        
        Returns:
            合并后的测试用例列表
        """
        all_cases = []
        for pattern in file_patterns:
            try:
                cases = self.load_cases(pattern, case_filter)
                all_cases.extend(cases)
            except Exception as e:
                print(f"⚠️ 加载文件 {pattern} 失败: {e}")
        
        return all_cases
    
    def _read_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """读取CSV文件"""
        cases = []
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 清理空值
                cleaned_row = {k: (v.strip() if v else "") for k, v in row.items()}
                cases.append(cleaned_row)
        return cases
    
    def _identify_parser(self, file_path: str, raw_cases: List[Dict]) -> callable:
        """识别文件格式并返回对应的解析器"""
        filename = os.path.basename(file_path).lower()
        
        # 根据文件名识别
        for key, parser in self.supported_formats.items():
            if key in filename:
                return parser
        
        # 根据列名识别
        if raw_cases:
            columns = set(raw_cases[0].keys())
            if "Order_Detail" in columns and "Chat_History" in columns:
                return self._parse_xiaofang_fz_cases
            elif "Case_ID" in columns and "Dynamic_Inputs" in columns:
                return self._parse_golden_dataset
        
        # 默认解析器
        return self._parse_default_format
    
    def _parse_golden_dataset(self, raw_cases: List[Dict]) -> List[UnifiedTestCase]:
        """解析 xiaofang_fz_chat.csv 格式"""
        unified_cases = []
        
        for row in raw_cases:
            try:
                # 解析 Dynamic_Inputs
                dynamic_inputs = {}
                if row.get("Dynamic_Inputs"):
                    try:
                        dynamic_inputs = json.loads(row["Dynamic_Inputs"])
                    except json.JSONDecodeError:
                        print(f"⚠️ 用例 {row.get('Case_ID')} 的 Dynamic_Inputs 解析失败")
                
                # 解析断言规则
                assert_rules = []
                if row.get("Assert"):
                    assert_str = str(row["Assert"]).strip()
                    if assert_str and assert_str.lower() not in ["", "none", "null"]:
                        assert_rules = [assert_str]
                
                case = UnifiedTestCase(
                    case_id=row.get("Case_ID", ""),
                    target_agent=row.get("Target_Agent", ""),
                    scene_description=row.get("场景描述", ""),
                    input_query=row.get("Input_Query", ""),
                    dynamic_inputs=dynamic_inputs,
                    session_key=row.get("Session_Key"),
                    expected_action=row.get("Expected_Action", "Reply"),
                    assert_rules=assert_rules,
                    metadata={"source_file": "xiaofang_fz_chat.csv"}
                )
                
                unified_cases.append(case)
            except Exception as e:
                print(f"⚠️ 解析用例失败: {row.get('Case_ID', 'Unknown')} - {e}")
        
        return unified_cases

    def _parse_xiaofang_fz_cases(self, raw_cases: List[Dict]) -> List[UnifiedTestCase]:
        """解析 xiaofang_fz_todo.csv 格式（包含 Order_Detail 和 Chat_History）"""
        from src.utils.dynamic_renderer import renderer

        unified_cases = []

        for row in raw_cases:
            try:
                # 解析 Dynamic_Inputs
                dynamic_inputs = {}
                if row.get("Dynamic_Inputs"):
                    try:
                        rendered = renderer.render(row["Dynamic_Inputs"])
                        dynamic_inputs = json.loads(rendered)
                    except Exception as e:
                        print(f"⚠️ 用例 {row.get('Case_ID')} 的 Dynamic_Inputs 解析失败: {e}")

                # 解析 Order_Detail
                order_detail = None
                if row.get("Order_Detail"):
                    try:
                        rendered = renderer.render(row["Order_Detail"])
                        order_detail = json.loads(rendered)
                    except Exception as e:
                        print(f"⚠️ 用例 {row.get('Case_ID')} 的 Order_Detail 解析失败: {e}")

                # 解析 Chat_History
                chat_history = None
                if row.get("Chat_History"):
                    try:
                        rendered = renderer.render(row["Chat_History"])
                        chat_history = json.loads(rendered)
                    except Exception as e:
                        print(f"⚠️ 用例 {row.get('Case_ID')} 的 Chat_History 解析失败: {e}")

                case = UnifiedTestCase(
                    case_id=row.get("Case_ID", ""),
                    target_agent=row.get("Target_Agent", ""),
                    session_key=row.get("Session_Key", ""),
                    scene_description=row.get("场景描述", ""),
                    case_type=TestCaseType.WORKFLOW_EXECUTION,
                    dynamic_inputs=dynamic_inputs,
                    order_detail=order_detail,
                    chat_history=chat_history,
                    expected_action=row.get("Expected_Action", "Reply"),
                    assert_rules=row.get("Assert", ""),
                    metadata={"source_file": "xiaofang_fz_todo.csv"}
                )

                unified_cases.append(case)
            except Exception as e:
                print(f"⚠️ 解析用例失败: {row.get('Case_ID', 'Unknown')} - {e}")

        return unified_cases

    def _parse_exports_format(self, raw_cases: List[Dict]) -> List[UnifiedTestCase]:
        """解析 exports 格式（Langfuse导出格式）"""
        unified_cases = []

        for idx, row in enumerate(raw_cases):
            try:
                # 解析 input
                input_data = {}
                if row.get("input"):
                    try:
                        input_data = json.loads(row["input"])
                    except:
                        pass

                # 解析 expectedOutput
                expected_output = {}
                if row.get("expectedOutput"):
                    try:
                        expected_output = json.loads(row["expectedOutput"])
                    except:
                        pass

                # 解析 metadata
                metadata = {}
                if row.get("metadata"):
                    try:
                        metadata = json.loads(row["metadata"])
                    except:
                        pass

                case = UnifiedTestCase(
                    case_id=f"EXPORT_{idx+1:03d}",
                    target_agent=metadata.get("app_id", "unknown"),
                    scene_description=f"导出用例 {idx+1}",
                    input_query=input_data.get("scene", ""),
                    dynamic_inputs=metadata,
                    expected_action="Reply",
                    metadata={
                        "source_file": "exports",
                        "expected_output": expected_output,
                        "trace_id": row.get("sourceTraceId", "")
                    }
                )

                unified_cases.append(case)
            except Exception as e:
                print(f"⚠️ 解析导出用例 {idx+1} 失败: {e}")

        return unified_cases

    def _parse_default_format(self, raw_cases: List[Dict]) -> List[UnifiedTestCase]:
        """默认解析器，尝试智能识别字段"""
        unified_cases = []

        for idx, row in enumerate(raw_cases):
            try:
                # 智能识别字段
                case_id = row.get("Case_ID") or row.get("case_id") or f"CASE_{idx+1:03d}"
                target_agent = row.get("Target_Agent") or row.get("target_agent") or "unknown"
                scene_desc = row.get("场景描述") or row.get("scene_description") or row.get("description") or ""

                case = UnifiedTestCase(
                    case_id=case_id,
                    target_agent=target_agent,
                    scene_description=scene_desc,
                    metadata={"source_file": "unknown", "raw_data": row}
                )

                unified_cases.append(case)
            except Exception as e:
                print(f"⚠️ 解析用例 {idx+1} 失败: {e}")

        return unified_cases

    def _apply_filter(
        self,
        cases: List[UnifiedTestCase],
        filter_dict: Dict[str, Any]
    ) -> List[UnifiedTestCase]:
        """应用过滤条件"""
        filtered = cases

        if "case_ids" in filter_dict:
            case_ids = set(filter_dict["case_ids"])
            filtered = [c for c in filtered if c.case_id in case_ids]

        if "tags" in filter_dict:
            required_tags = set(filter_dict["tags"])
            filtered = [c for c in filtered if any(tag in c.tags for tag in required_tags)]

        if "target_agents" in filter_dict:
            agents = set(filter_dict["target_agents"])
            filtered = [c for c in filtered if c.target_agent in agents]

        if "enabled" in filter_dict:
            enabled = filter_dict["enabled"]
            filtered = [c for c in filtered if c.enabled == enabled]

        return filtered


def load_cases_from_config(config_path: str = "config/config.yaml") -> List[UnifiedTestCase]:
    """
    从配置文件加载测试用例
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        测试用例列表
    """
    # 加载配置
    config = ConfigLoader(config_path)
    test_files = config.get("test_data.files", [])
    case_filter = config.get("test_data.filter", {}) or {}
    
    # 过滤掉 None 值（yaml中注释掉的字段可能是None，取决于加载方式，但通常yaml safe_load不会把注释的key读出来）
    # 但如果用户在yaml里写 key: null 或者 key: ，那么值就是None
    if case_filter:
        case_filter = {k: v for k, v in case_filter.items() if v is not None}
    
    # 实例化加载器
    loader = CaseLoader(data_dir="data")
    
    # 加载用例
    try:
        # 检查CASE_FILTER是否有实际的过滤条件
        has_filter = any(v for v in case_filter.values() if v)
        filter_to_use = case_filter if has_filter else None
        
        cases = loader.load_multiple_files(test_files, case_filter=filter_to_use)
        
        if filter_to_use:
            print(f"   应用的过滤条件: {filter_to_use}")
    except Exception as e:
        print(f"❌ 加载测试用例失败: {e}")
        import traceback
        traceback.print_exc()
        cases = []
        
    if not cases:
        print("⚠️ 没有找到任何测试用例")
        
    return cases
