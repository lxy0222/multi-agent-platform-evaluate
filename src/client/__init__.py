from .dify_client import DifyClient


# from .coze_client import CozeClient

class AgentClientFactory:
    @staticmethod
    def create(config: dict):
        """
        config: 包含了该 agent 的所有参数 (platform, api_key, bot_id 等)
        """
        platform = config.get("platform", "").lower()

        if platform == "dify":
            # DifyClient 内部会自己去 config 里找 api_key
            return DifyClient(config)

        elif platform == "coze":
            # CozeClient 内部会自己去 config 里找 bot_id
            # return CozeClient(config)
            raise NotImplementedError("Coze Client 暂未实现")

        else:
            raise ValueError(f"不支持的平台类型: {platform}")