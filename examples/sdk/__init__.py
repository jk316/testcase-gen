"""信而泰（Xinertel）ALPS 稳定 SDK。

生成的可执行测试脚本从这里导入运行时：::

    from examples.sdk import AlpsClient, ApiError

领域模型见 ``models.ddos_attack_config``。
"""
from examples.sdk.client import (
    AlpsClient,
    build_signature,
    extract_matched_ports,
    find_attack_profile_id,
    find_available_port,
    sha1_hex,
)
from examples.sdk.errors import AlpsError, ApiError, AttackNotFoundError
from examples.sdk.capabilities import CAPABILITIES, Capability, get_capability

__all__ = [
    "AlpsClient",
    "ApiError",
    "AlpsError",
    "AttackNotFoundError",
    "Capability",
    "CAPABILITIES",
    "build_signature",
    "extract_matched_ports",
    "find_attack_profile_id",
    "find_available_port",
    "get_capability",
    "sha1_hex",
]
