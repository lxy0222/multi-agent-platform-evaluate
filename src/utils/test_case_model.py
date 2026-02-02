"""
统一的测试用例数据模型
定义标准化的测试用例数据结构，所有不同格式的CSV都会被转换为这个统一格式
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class WorkflowType(Enum):
    """工作流类型枚举"""
    CHAT = "chat"  # 对话型
    WORKFLOW = "workflow"  # 工作流型


class TestCaseType(Enum):
    """测试用例类型枚举"""
    CHAT_MESSAGE = "chat_message"  # 聊天消息测试
    WORKFLOW_EXECUTION = "workflow_execution"  # 工作流执行测试
    MIXED = "mixed"  # 混合类型


@dataclass
class UnifiedTestCase:
    """
    统一的测试用例数据结构
    所有不同格式的测试用例都会被转换为这个标准格式
    """
    # ========== 基础信息 ==========
    case_id: str  # 用例ID，如 CASE_01
    target_agent: str  # 目标智能体，如 follow_up, todo_exec_follow
    scene_description: str  # 场景描述
    case_type: TestCaseType = TestCaseType.CHAT_MESSAGE  # 用例类型
    
    # ========== 输入数据 ==========
    input_query: str = ""  # 用户输入的查询内容
    dynamic_inputs: Dict[str, Any] = field(default_factory=dict)  # 动态输入参数
    
    # ========== 会话管理 ==========
    session_key: Optional[str] = None  # 会话标识，用于多轮对话
    conversation_id: Optional[str] = None  # 具体的会话ID
    
    # ========== 预期结果 ==========
    expected_action: str = "Reply"  # 预期动作：Reply, Block, Delay等
    expected_result: Optional[str] = None  # 预期回复内容（用于LLM评估）
    assert_rules: List[str] = field(default_factory=list)  # 断言规则列表
    
    # ========== 扩展字段 ==========
    order_detail: Optional[Dict[str, Any]] = None  # 订单详情（用于待办工作流）
    chat_history: Optional[List[Dict[str, Any]]] = None  # 聊天历史
    metadata: Dict[str, Any] = field(default_factory=dict)  # 其他元数据
    
    # ========== 执行控制 ==========
    enabled: bool = True  # 是否启用该用例
    tags: List[str] = field(default_factory=list)  # 用例标签，用于分类和过滤
    priority: int = 1  # 优先级，1-5，数字越大优先级越高
    
    def __post_init__(self):
        """初始化后的处理"""
        # 自动推断用例类型
        if self.case_type == TestCaseType.CHAT_MESSAGE:
            if "todo_exec" in self.target_agent:
                self.case_type = TestCaseType.WORKFLOW_EXECUTION
        
        # 自动添加标签
        if not self.tags:
            self.tags = [self.target_agent, self.expected_action]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "case_id": self.case_id,
            "target_agent": self.target_agent,
            "scene_description": self.scene_description,
            "case_type": self.case_type.value,
            "input_query": self.input_query,
            "dynamic_inputs": self.dynamic_inputs,
            "session_key": self.session_key,
            "conversation_id": self.conversation_id,
            "expected_action": self.expected_action,
            "expected_result": self.expected_result,
            "assert_rules": self.assert_rules,
            "order_detail": self.order_detail,
            "chat_history": self.chat_history,
            "metadata": self.metadata,
            "enabled": self.enabled,
            "tags": self.tags,
            "priority": self.priority
        }
    
    def get_workflow_type(self) -> WorkflowType:
        """获取工作流类型"""
        if "todo_exec" in self.target_agent:
            return WorkflowType.WORKFLOW
        return WorkflowType.CHAT
    
    def should_check_human_transfer(self) -> bool:
        """是否需要检查转人工"""
        return "转人工" in self.assert_rules or any(
            rule in self.metadata.get("Assert", "") 
            for rule in ["转人工", "needHuman"]
        )
    
    def get_user_id(self) -> str:
        """获取用户ID"""
        # 优先从 dynamic_inputs 中获取
        if "patientId" in self.dynamic_inputs:
            return str(self.dynamic_inputs["patientId"])
        if "sys.user_id" in self.dynamic_inputs:
            return str(self.dynamic_inputs["sys.user_id"])
        # 默认使用 case_id
        return f"qa_{self.case_id}"

