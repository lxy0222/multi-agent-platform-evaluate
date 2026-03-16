from abc import ABC, abstractmethod

class BaseAgentClient(ABC):
    """
    智能体通用客户端基类 (Adapter Interface)
    """
    def __init__(self, config: dict):
        self.config = config
        # 统一从 config 中提取基础信息，子类可按需提取更多
        self.platform = config.get('platform', 'unknown')

    @abstractmethod
    def send_message(self, query, inputs, user, response_mode="blocking", conversation_id=""):
        """
        统一的对话接口
        :return: {
            "status": "success/error",
            "answer": str,
            "json_data": dict, # 解析后的结构化数据
            "conversation_id": str,
            "raw_outputs": dict # 原始回包
        }
        """
        pass

    @abstractmethod
    def run_workflow(self, inputs, user) -> dict:
        """
        统一的工作流执行接口
        """
        pass