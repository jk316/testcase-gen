"""信而泰（Xinertel）ALPS 客户端 —— 稳定 SDK。

封装所有 ``/v1/cl/*`` 接口，屏蔽 HTTP 请求、时间戳、session_id、签名等细节。
生成的可执行测试脚本只 ``from examples.sdk import AlpsClient`` 并编排调用顺序，
不直接接触底层实现。

使用方式::

    client = AlpsClient(base_url="https://10.99.80.111:7070", name="admin", password="admin")
    client.login()
    ...  # 编排调用
    client.logout()
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, Optional

import requests

from examples.sdk.errors import ApiError, AttackNotFoundError
from models.ddos_attack_config import (
    AppModule,
    AppProfileBrief,
    AttackModule,
    AttackProfileBrief,
    BasicData,
    Behav,
    DataRate,
    DefaultProfile,
    LoadProfile,
    ProfileDetail,
    SharedSettings,
    SrcPort,
    SuperFlow,
    TestcaseInfo,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AlpsClient",
    "build_signature",
    "sha1_hex",
    "find_attack_profile_id",
    "find_available_network",
    "find_available_port",
    "extract_matched_ports",
]


def sha1_hex(text: str) -> str:
    """Return SHA-1 hex digest of a UTF-8 string."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build_signature(name: str, password: str, ts: int) -> str:
    """按规则生成登录签名：signature = SHA1(name + timestamp(int) + SHA1(password))。"""
    return sha1_hex(f"{name}{ts}{sha1_hex(password)}")


class AlpsClient:
    """封装所有 /v1/cl/* 接口的客户端。"""

    def __init__(
        self,
        base_url: str,
        name: str,
        *,
        password: Optional[str] = None,
        signature: Optional[str] = None,
        observer: str = "",
        verify: bool | str = False,
        timeout: float = 15.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        """
        Args:
            base_url: 服务端基础地址，如 "https://10.99.80.111:7070"。
            name: 用户名。
            password: 若提供，将用于现场生成签名（推荐）；与 signature 互斥。
            signature: 若已在外部生成，可直接传入；与 password 互斥。
            observer: ""(默认) / "1"=强制登录 / "2"=观察者模式登录。
            verify: requests 的 verify 参数；False 忽略证书校验。
            timeout: 默认请求超时时间（秒）。
            session: 可选的外部 Session；若为空则内部创建。
        """
        if (password is None) and (signature is None):
            raise ValueError("必须提供 password 或 signature 之一。")
        if (password is not None) and (signature is not None):
            raise ValueError("password 与 signature 只能二选一。")

        self.base_url = base_url.rstrip("/")
        self.name = name
        self.password = password
        self.signature = signature
        self.observer = observer
        self.verify = verify
        self.timeout = timeout
        self.session = session or requests.Session()

        self.session_id: Optional[str] = None

    # ---------- 内部通用请求方法 ---------- #

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        need_timestamp: bool = True,
        add_session_id: bool = False,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """统一封装 HTTP 请求、错误处理和 JSON 解析。"""
        url = f"{self.base_url}{path}"
        ts = int(time.time())

        params = dict(params or {})
        if need_timestamp:
            params.setdefault("timestamp", str(ts))
        if add_session_id:
            if not self.session_id:
                raise ApiError("session_id 为空，请先登录。")
            params.setdefault("session_id", self.session_id)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        resp = self.session.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=timeout or self.timeout,
            verify=self.verify,
        )

        if not resp.ok:
            raise ApiError(f"HTTP {resp.status_code}: {resp.text[:500]}")

        try:
            return resp.json()
        except ValueError:
            raise ApiError(f"非 JSON 响应: {resp.text[:2000]}")

    # ---------- 会话 ---------- #

    def login(self, timestamp: Optional[int] = None) -> Dict[str, Any]:
        """POST /v1/cl/user/login，成功后保存 session_id。"""
        ts = int(timestamp if timestamp is not None else time.time())

        payload: Dict[str, Any] = {"name": self.name, "observer": self.observer}
        if self.signature is not None:
            payload["signature"] = self.signature
        else:
            payload["signature"] = build_signature(self.name, self.password, ts)  # type: ignore[arg-type]

        data = self._request(
            method="POST",
            path="/v1/cl/user/login",
            params={"timestamp": str(ts)},
            json_body=payload,
            need_timestamp=False,
            add_session_id=False,
        )

        self.session_id = data.get("result", {}).get("session_id")
        if not self.session_id:
            raise ApiError(f"登录成功但未返回 session_id: {data}")
        return data

    def logout(self, timestamp: Optional[int] = None) -> Dict[str, Any]:
        """POST /v1/cl/user/logout。"""
        if not self.session_id:
            return {"message": "no session_id, skip logout"}

        params: Dict[str, Any] = {}
        if timestamp is not None:
            params["timestamp"] = str(int(timestamp))

        data = self._request(
            method="POST",
            path="/v1/cl/user/logout",
            params=params,
            json_body={"name": self.name},
            add_session_id=True,
        )
        self.session_id = None
        return data

    # ---------- 端口 ---------- #

    def get_port_list(self, timestamp: Optional[int] = None) -> Dict[str, Any]:
        """GET /v1/cl/port/list。"""
        params: Dict[str, Any] = {}
        if timestamp is not None:
            params["timestamp"] = str(int(timestamp))
        return self._request("GET", "/v1/cl/port/list", params=params, add_session_id=True)

    def reserve_port(self, port_id: str) -> Dict[str, Any]:
        """POST /v1/cl/port/reserve，预留指定端口。"""
        return self._request(
            "POST", "/v1/cl/port/reserve", json_body={"port_id": port_id}, add_session_id=True
        )

    def reserve_first_available_port(self) -> str:
        """查询端口列表并预留第一个可用（未预留、未运行）端口，返回 port_id。"""
        data = self.get_port_list()
        port_id = find_available_port(data)
        if port_id is None:
            raise ApiError("没有可用的未预留端口")
        self.reserve_port(port_id)
        return port_id

    def release_port(self, port_id: str) -> Dict[str, Any]:
        """POST /v1/cl/port/release，释放指定端口。"""
        return self._request(
            "POST", "/v1/cl/port/release", json_body={"port_id": port_id}, add_session_id=True
        )

    # ---------- 网络 / 组件 ---------- #

    def get_network_list(self) -> Dict[str, Any]:
        """GET /v1/cl/network/list。"""
        return self._request("GET", "/v1/cl/network/list", add_session_id=True)

    def select_first_available_network(self) -> tuple[int, str]:
        """查询网络邻居并返回第一个包含有效 id/name 的网络配置。"""
        network = find_available_network(self.get_network_list())
        if network is None:
            raise ApiError("没有可用的网络邻居")
        return network

    def fetch_network(self, network_id: int) -> Dict[str, Any]:
        """POST /v1/cl/network/fetch。"""
        return self._request(
            "POST", "/v1/cl/network/fetch", json_body={"network_id": network_id}, add_session_id=True
        )

    def get_component_list(self) -> Dict[str, Any]:
        """GET /v1/cl/testcase/component/list。"""
        return self._request("GET", "/v1/cl/testcase/component/list", add_session_id=True)

    # ---------- 攻击类型 / 攻击配置 ---------- #

    def get_ddos_attack_list(self) -> Dict[str, Any]:
        """GET /v1/cl/ddos/attack/list，获取支持的攻击类型。"""
        return self._request("GET", "/v1/cl/ddos/attack/list", add_session_id=True)

    def get_ddos_attack_flow_list(self) -> Dict[str, Any]:
        """GET /v1/cl/ddos/attack/flow/list。"""
        return self._request("GET", "/v1/cl/ddos/attack/flow/list", add_session_id=True)

    def get_ddos_attack_profile_list(self) -> Dict[str, Any]:
        """GET /v1/cl/ddos/attack/profile/list。"""
        return self._request("GET", "/v1/cl/ddos/attack/profile/list", add_session_id=True)

    def get_load_profile_list(self) -> Dict[str, Any]:
        """GET /v1/cl/load/profile/list（负载/业务 profile 列表）。"""
        return self._request("GET", "/v1/cl/load/profile/list", add_session_id=True)

    def get_attack_profile(self, attack_profile_id: int) -> Dict[str, Any]:
        """POST /v1/cl/ddos/attack/profile/fetch。"""
        return self._request(
            "POST",
            "/v1/cl/ddos/attack/profile/fetch",
            json_body={"attack_profile_id": attack_profile_id},
            add_session_id=True,
        )

    def create_attack_flow(self, flow_name: str, overwrite: bool = True) -> Dict[str, Any]:
        """POST /v1/cl/ddos/attack/flow/create，创建 DDoS 攻击流量模板（空壳）。"""
        return self._request(
            "POST",
            "/v1/cl/ddos/attack/flow/create",
            json_body={"flow_name": flow_name, "overwrite": overwrite},
            add_session_id=True,
        )

    def create_attack_profile(self, profile_name: str, overwrite: bool = True) -> Dict[str, Any]:
        """POST /v1/cl/ddos/attack/profile/create，创建攻击 profile（空壳，参数用 param/update 设置）。"""
        return self._request(
            "POST",
            "/v1/cl/ddos/attack/profile/create",
            json_body={"profile_name": profile_name, "overwrite": overwrite},
            add_session_id=True,
        )

    def update_attack_profile_param(
        self, profile_id: int, profile_name: str, param: str, value: Any
    ) -> Dict[str, Any]:
        """POST /v1/cl/ddos/attack/profile/param/update，更新攻击 profile 单个参数。

        param/value 的取值语义由设备定义（OpenAPI 未展开），需按实测校准。
        """
        return self._request(
            "POST",
            "/v1/cl/ddos/attack/profile/param/update",
            json_body={
                "profile_id": profile_id,
                "profile_name": profile_name,
                "param": param,
                "value": value,
            },
            add_session_id=True,
        )

    def create_load_profile(self, profile_name: str, overwrite: bool = True) -> Dict[str, Any]:
        """POST /v1/cl/load/profile/create，创建负载（业务）profile。"""
        return self._request(
            "POST",
            "/v1/cl/load/profile/create",
            json_body={"profile_name": profile_name, "overwrite": overwrite},
            add_session_id=True,
        )

    def update_load_profile_param(
        self, profile_id: int, profile_name: str, param: str, value: Any
    ) -> Dict[str, Any]:
        """POST /v1/cl/load/profile/param/update，更新负载（业务）profile 单个参数。"""
        return self._request(
            "POST",
            "/v1/cl/load/profile/param/update",
            json_body={
                "profile_id": profile_id,
                "profile_name": profile_name,
                "param": param,
                "value": value,
            },
            add_session_id=True,
        )

    def ensure_attack_profile(self, profile_name: str) -> tuple[int, str]:
        """复用优先：按名称匹配已有攻击 profile，找不到则新建空 profile。

        返回 ``(profile_id, profile_name)``。当前仅按名称复用；参数是否符合
        要求（带宽/时长/目标）的校验需后续用 ``profile/param/fetch`` 补充。
        """
        try:
            return find_attack_profile_id(
                self.get_ddos_attack_profile_list().get("result", []), profile_name
            )
        except AttackNotFoundError:
            data = self.create_attack_profile(profile_name)
            profile_id = data.get("result", {}).get("profile_id")
            if profile_id is None:
                raise ApiError(f"创建攻击 profile 失败，未返回 profile_id: {data}")
            return profile_id, profile_name

    def ensure_load_profile(self, profile_name: str) -> tuple[int, str]:
        """复用优先：按名称匹配已有负载（业务）profile，找不到则新建空 profile。"""
        try:
            return find_attack_profile_id(
                self.get_load_profile_list().get("result", []), profile_name
            )
        except AttackNotFoundError:
            data = self.create_load_profile(profile_name)
            profile_id = data.get("result", {}).get("profile_id")
            if profile_id is None:
                raise ApiError(f"创建 load profile 失败，未返回 profile_id: {data}")
            return profile_id, profile_name

    # ---------- 测试用例 ---------- #

    def create_testcase(self, testcase_name: str, overwrite: bool = True) -> Dict[str, Any]:
        """POST /v1/cl/testcase/create。"""
        return self._request(
            "POST",
            "/v1/cl/testcase/create",
            json_body={"overwrite": overwrite, "testcase_name": testcase_name},
            add_session_id=True,
        )

    def delete_testcase(self, testcase_id: Any) -> Dict[str, Any]:
        """POST /v1/cl/testcase/delete。"""
        return self._request(
            "POST", "/v1/cl/testcase/delete", json_body={"testcase_id": testcase_id}, add_session_id=True
        )

    def fetch_testcase_param(self, testcase_id_list: list) -> Dict[str, Any]:
        """POST /v1/cl/testcase/param/fetch。"""
        return self._request(
            "POST",
            "/v1/cl/testcase/param/fetch",
            json_body={"testcase_id": testcase_id_list},
            add_session_id=True,
        )

    def save_testcase(self, testcase_id: int, testcase_info: TestcaseInfo) -> Dict[str, Any]:
        """POST /v1/cl/testcase/save。"""
        return self._request(
            "POST",
            "/v1/cl/testcase/save",
            json_body={"testcase_id": testcase_id, "testcase_info": testcase_info.model_dump()},
            add_session_id=True,
        )

    def run_testcase(
        self,
        testcase_id: int,
        testcase_name: Optional[str] = None,
        port_mapping: Optional[Any] = None,
        instance_lookup_timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        """执行测试用例，并保证返回 ``result.instance_id``。

        部分设备版本的 ``testcase/run`` 成功响应只有 ``code/message``，与
        OpenAPI 声明不一致。此时通过 ``testcase/status`` 短暂轮询实例 ID，
        再把它补回 run 响应，给生成代码提供稳定的返回结构。
        """
        payload: Dict[str, Any] = {"testcase_id": testcase_id}
        if testcase_name is not None:
            payload["testcase_name"] = testcase_name
        if port_mapping is not None:
            payload["port_mapping"] = port_mapping
        data = self._request(
            "POST", "/v1/cl/testcase/run", json_body=payload, add_session_id=True
        )

        if data.get("code") not in (None, 0):
            raise ApiError(f"运行测试用例失败: {data.get('message', data)}")

        result = data.get("result")
        if isinstance(result, dict) and result.get("instance_id") is not None:
            return data

        deadline = time.monotonic() + max(0.0, instance_lookup_timeout)
        while True:
            status = self.get_testcase_status(testcase_id)
            status_result = status.get("result")
            if isinstance(status_result, dict) and status_result.get("instance_id") is not None:
                normalized = dict(data)
                normalized["result"] = dict(status_result)
                return normalized
            if time.monotonic() >= deadline:
                raise ApiError(
                    "测试用例已提交运行，但 run/status 均未返回 instance_id; "
                    f"run={data!r}, status={status!r}"
                )
            time.sleep(max(0.0, poll_interval))

    def get_testcase_status(self, testcase_id: int) -> Dict[str, Any]:
        """POST /v1/cl/testcase/status，查询运行状态与实例 ID。"""
        return self._request(
            "POST",
            "/v1/cl/testcase/status",
            json_body={"testcase_id": testcase_id},
            add_session_id=True,
        )

    def stop_testcase(self, testcase_id: int) -> Dict[str, Any]:
        """POST /v1/cl/testcase/stop，停止指定测试用例。"""
        return self._request(
            "POST", "/v1/cl/testcase/stop", json_body={"testcase_id": testcase_id}, add_session_id=True
        )

    # ---------- 统计 ---------- #

    def get_stats_model(self, instance_id: int) -> Dict[str, Any]:
        """POST /v1/cl/stats/model，获取测试用例实例的实时模型。"""
        return self._request(
            "POST", "/v1/cl/stats/model", json_body={"instance_id": instance_id}, add_session_id=True
        )

    def get_stats_overview(self, instance_id: int, interval: int = 1) -> Dict[str, Any]:
        """POST /v1/cl/stats/overview，获取测试用例实例的概览统计。"""
        payload: Dict[str, Any] = {"instance_id": instance_id, "interval": interval}
        return self._request(
            "POST", "/v1/cl/stats/overview", json_body=payload, add_session_id=True
        )

    def get_stats_category(
        self, instance_id: int, category: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """POST /v1/cl/stats/category/search，获取指定类别的实时统计。"""
        payload: Dict[str, Any] = {"instance_id": instance_id, "category": category}
        payload.update(kwargs)
        return self._request(
            "POST", "/v1/cl/stats/category/search", json_body=payload, add_session_id=True
        )

    # ---------- 攻击配置构建器 ---------- #
    # 这些方法返回 Pydantic 模型，供 save_testcase 使用；具体取值语义需按设备实测校准。

    def set_basic_data(self, attack_name: str) -> BasicData:
        """构建 BasicData。"""
        return BasicData(
            name=attack_name,
            desc="",
            client_tags=["client6"],  # TODO: 按设备实际标签查询
            server_tags=["server6"],
            disable=False,
        )

    def set_data_rate(self, rate: Optional[int] = None) -> DataRate:
        """构建 DataRate。unit/type 语义需按设备确认，此处保留既有默认。"""
        r = rate if rate is not None else 5154
        return DataRate(unlimited=False, unit=1, type=0, min_rate=r, max_rate=r)

    def set_attack_profile_brief(self, profile_id: int, profile_name: str) -> AttackProfileBrief:
        """构建 AttackProfileBrief。"""
        return AttackProfileBrief(profile_id=profile_id, profile_name=profile_name, user_id=1)

    def set_profile_detail(self, name: str, desc: str = "", user_id: int = 1) -> ProfileDetail:
        """构建 ProfileDetail。"""
        return ProfileDetail(name=name, desc=desc, user_id=user_id)

    def set_super_flow(
        self, max_flows: Optional[int] = None, max_flow_rate: Optional[int] = None
    ) -> SuperFlow:
        """构建 SuperFlow。max_flows/max_flow_rate 需按流量与时长计算。"""
        return SuperFlow(
            load_profile_type=0,
            max_flows=max_flows if max_flows is not None else 80000,
            max_flow_rate=max_flow_rate if max_flow_rate is not None else 80000,
            max_flow_attempts=0,
            enable_conn_ctrl=False,
            max_outstanding_conns=1000,
            enable_bandwidth_ctrl=False,
            enable_max_flows=True,
            flow_timeout=2000,
        )

    def set_load_profile(
        self, steady_duration: int = 60, ramp_up: int = 2, ramp_down: int = 2
    ) -> LoadProfile:
        """构建 LoadProfile；steady_duration 为稳态时长（秒）。"""
        return LoadProfile(
            default=DefaultProfile(
                ramp_up=Behav(behavior=1, duration=ramp_up),
                steady=Behav(behavior=1, duration=steady_duration),
                ramp_down=Behav(behavior=1, duration=ramp_down),
            )
        )

    def set_src_port(self) -> SrcPort:
        """构建 SrcPort（源端口范围）。"""
        return SrcPort(type=2, min=1024, max=65535, polling_mode=0)

    def set_attack_module(
        self,
        profile_id: int,
        profile_name: str,
        rate: Optional[int] = None,
        steady_duration: Optional[int] = None,
    ) -> AttackModule:
        """构建一个完整 AttackModule（basic + load_profile + attack_profile + ...）。"""
        return AttackModule(
            basic=self.set_basic_data(profile_name),
            load_profile=self.set_load_profile(steady_duration or 60),
            attack_profile=self.set_attack_profile_brief(profile_id, profile_name),
            data_rate=self.set_data_rate(rate),
            super_flow=self.set_super_flow(),
            src_port=self.set_src_port(),
            delay_start=2,
            delay_start_second=2,
        )

    def set_app_profile_brief(self, profile_id: int, profile_name: str) -> AppProfileBrief:
        """构建 AppProfileBrief（业务 profile 简要信息）。"""
        return AppProfileBrief(profile_id=profile_id, profile_name=profile_name, user_id=1)

    def set_app_module(
        self,
        profile_id: int,
        profile_name: str,
        rate: Optional[int] = None,
        steady_duration: Optional[int] = None,
    ) -> AppModule:
        """构建一个完整 AppModule（业务/应用仿真模块），结构与 AttackModule 平行。"""
        return AppModule(
            basic=self.set_basic_data(profile_name),
            load_profile=self.set_load_profile(steady_duration or 60),
            app_profile=self.set_app_profile_brief(profile_id, profile_name),
            data_rate=self.set_data_rate(rate),
            super_flow=self.set_super_flow(),
            src_port=self.set_src_port(),
            delay_start=2,
            delay_start_second=2,
        )

    def set_shared_settings(
        self,
        testcase_name: str,
        network_id: Optional[int] = None,
        network_name: Optional[str] = None,
    ) -> SharedSettings:
        """构建 SharedSettings。"""
        shared = SharedSettings()
        shared.port_reset = True
        shared.testcase_name = testcase_name
        if network_id is not None:
            shared.network_id = network_id
        if network_name is not None:
            shared.network_name = network_name
        shared.enable_cpu_usage = False
        shared.enable_custom_stats = False
        shared.sample_interval = 1
        return shared

    def set_testcase_info(
        self,
        testcase_id: int,
        testcase_name: str,
        attacks: list[dict[str, Any]],
        businesses: Optional[list[dict[str, Any]]] = None,
        network_id: Optional[int] = None,
        network_name: Optional[str] = None,
    ) -> TestcaseInfo:
        """构建 TestcaseInfo（支持多攻击 + 多业务）。

        ``attacks`` / ``businesses`` 每项形如::

            {"profile_id": int, "profile_name": str, "bandwidth_mbps": int, "duration_sec": int}

        ``bandwidth_mbps`` 映射到 ``data_rate``，``duration_sec`` 映射到 ``load_profile`` 稳态时长。
        """
        info = TestcaseInfo()
        info.testcase_id = testcase_id
        info.ddos_attack_list = [
            self.set_attack_module(
                a["profile_id"],
                a["profile_name"],
                a.get("bandwidth_mbps"),
                a.get("duration_sec"),
            )
            for a in attacks
        ]
        if businesses:
            info.app_simulator_list = [
                self.set_app_module(
                    b["profile_id"],
                    b["profile_name"],
                    b.get("bandwidth_mbps"),
                    b.get("duration_sec"),
                )
                for b in businesses
            ]
        info.shared_settings = self.set_shared_settings(
            testcase_name,
            network_id=network_id,
            network_name=network_name,
        )
        info.component_tags = ["client6", "server6"]
        return info


def find_attack_profile_id(attack_profile_list: Any, attack_name: str) -> tuple[int, str]:
    """在攻击 profile 列表中按名称匹配，返回 (profile_id, profile_name)。"""
    attack_name_lower = attack_name.lower()
    for profile in attack_profile_list:
        profile_name = profile.get("profile_name")
        if not profile_name:
            continue
        if attack_name_lower in profile_name.lower():
            return profile.get("profile_id"), profile_name
    logger.info("未找到名称匹配的 profile '%s'，将由调用方决定是否新建", attack_name)
    raise AttackNotFoundError("attack not found")


def find_available_network(data: Dict[str, Any]) -> Optional[tuple[int, str]]:
    """从 ``network/list`` 结果中选择第一个具有有效 id/name 的网络邻居。"""
    result = data.get("result", [])
    if not isinstance(result, list):
        return None
    for network in result:
        if not isinstance(network, dict):
            continue
        network_id = network.get("network_id")
        network_name = network.get("network_name")
        if network_id is not None and network_name:
            return int(network_id), str(network_name)
    return None


def extract_matched_ports(data: Dict[str, Any]) -> list[Dict[str, Any]]:
    """筛选 is_reserved=True 且 test_running=False 的端口。"""
    matched: list[Dict[str, Any]] = []
    for chassis in data.get("result", []):
        for card in chassis.get("card_list", []):
            for port in card.get("port_list", []):
                if port.get("is_reserved") and not port.get("test_running"):
                    matched.append({"port_id": port.get("port_id")})
    return matched


def find_available_port(data: Dict[str, Any]) -> Optional[str]:
    """从 port/list 结果里找第一个可用（未预留、未运行）端口的 port_id。"""
    for chassis in data.get("result", []):
        for card in chassis.get("card_list", []):
            for port in card.get("port_list", []):
                if not port.get("is_reserved") and not port.get("test_running"):
                    return port.get("port_id")
    return None
