# utils/dynamic_renderer.py
import uuid
import random
import time
from datetime import datetime, timedelta
from jinja2 import Environment, BaseLoader


class DynamicRenderer:
    def __init__(self):
        # 初始化 Jinja2 环境
        # 关键点：修改标识符，避免与 JSON 的 {} 冲突
        self.env = Environment(
            loader=BaseLoader(),
            variable_start_string='((',  # 开始符号，例如 ((
            variable_end_string='))'  # 结束符号，例如 ))
        )

        # 注册所有你想要在 CSV 里使用的“工具函数”
        self.env.globals.update({
            "time_now": self._time_now,
            "time_offset": self._time_offset,
            "random_id": self._random_id,
            "random_int": self._random_int,
            "random_phone": self._random_phone,
            "concat": self._concat
        })

    # ==========================
    # 下面是供 CSV 调用的工具函数
    # ==========================

    def _time_now(self, fmt="%Y-%m-%d %H:%M:%S"):
        """返回当前时间，支持自定义格式"""
        return datetime.now().strftime(fmt)

    def _time_offset(self, days=0, hours=0, minutes=0, fmt="%Y-%m-%d %H:%M:%S"):
        """返回偏移后的时间：支持前后几天、几小时"""
        dt = datetime.now() + timedelta(days=days, hours=hours, minutes=minutes)
        return dt.strftime(fmt)

    def _random_id(self, length=8):
        """生成随机字符串ID"""
        return str(uuid.uuid4()).replace("-", "")[:length]

    def _random_int(self, min_val=0, max_val=100):
        """生成随机整数"""
        return random.randint(min_val, max_val)

    def _random_phone(self):
        """生成随机手机号"""
        prefix = random.choice(["138", "139", "150", "188", "130"])
        suffix = "".join(str(random.randint(0, 9)) for _ in range(8))
        return f"{prefix}{suffix}"

    def _concat(self, *args):
        """拼接字符串"""
        return "".join(str(arg) for arg in args)

    # ==========================
    # 核心渲染方法
    # ==========================
    def render(self, template_str):
        """
        传入包含 (( func() )) 的字符串，返回处理后的字符串
        """
        try:
            template = self.env.from_string(template_str)
            return template.render()
        except Exception as e:
            raise ValueError(f"模板渲染失败: {e}")


renderer = DynamicRenderer()