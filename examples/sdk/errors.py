"""信而泰 ALPS SDK 统一异常类型。"""


class AlpsError(Exception):
    """SDK 所有异常的基类。"""


class ApiError(AlpsError):
    """调用 ALPS 接口时发生的错误（HTTP 非 2xx、非 JSON 响应等）。"""


class AttackNotFoundError(AlpsError):
    """在攻击 profile 列表中未匹配到指定攻击类型时抛出。"""
