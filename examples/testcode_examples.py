import array
import time
import hashlib
from typing import Optional, Dict, Any
from models.ddos_attack_config import DataRate, BasicData, AttackProfileBrief, ProfileDetail, SuperFlow, LoadProfile, DefaultProfile, Behav, SrcPort, AttackModule, SharedSettings, TestcaseInfo
from exceptions import AttackNotFoundError
import requests
import logging


# ----------------- 通用工具函数 ----------------- #

def sha1_hex(text: str) -> str:
    """Return SHA-1 hex digest of a UTF-8 string."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build_signature(name: str, password: str, ts: int) -> str:
    """
    Build signature according to the rule:
    signature = SHA1( name + timestamp(int) + SHA1(password) )
    """
    return sha1_hex(f"{name}{ts}{sha1_hex(password)}")


class ApiError(Exception):
    """统一的 API 异常类型"""
    pass


class AlpsClient:
    """
    封装所有 /v1/cl/* 接口的客户端。

    使用方式：
        client = AlpsClient(base_url="https://...", name="admin", password="admin")
        client.login()
        ports = client.get_port_list()
        ...
        client.logout()
    """

    def __init__(
        self,
        base_url: str,
        name: str,
        *,
        password: Optional[str] = None,
        signature: Optional[str] = None,
        observer: str = "",
        verify: bool | str = False,  # False 忽略证书校验；生产可传 CA 证书路径
        timeout: float = 15.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        """
        Args:
            base_url: 服务端基础地址，如 "https://10.99.80.111:7070"
            name: 用户名
            password: 若提供，将用于生成签名（推荐）；与 signature 互斥。
            signature: 若已在外部生成，可直接传入（与 password 互斥）。
            observer: ""(默认) / "1"=强制登录 / "2"=观察者模式登录。
            verify:  requests 的 verify 参数。
            timeout: 默认请求超时时间。
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

        self.session_id: Optional[str] = None  # 登录成功后赋值

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
        """
        统一封装 HTTP 请求、错误处理和 JSON 解析。
        """
        url = f"{self.base_url}{path}"
        ts = int(time.time())

        # 基础 query 参数
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
            # 这里不再用 uu.Error，而是统一用 ApiError
            raise ApiError(f"HTTP {resp.status_code}: {resp.text[:500]}")

        try:
            return resp.json()
        except ValueError:
            raise ApiError(f"非 JSON 响应: {resp.text[:2000]}")

    # ---------- 公开 API 方法 ---------- #

    def login(self, timestamp: Optional[int] = None) -> Dict[str, Any]:
        """
        调用 POST /v1/cl/user/login，成功后在 client 内部保存 session_id。
        """
        ts = int(timestamp if timestamp is not None else time.time())

        payload: Dict[str, Any] = {
            "name": self.name,
            "observer": self.observer,
        }

        if self.signature is not None:
            payload["signature"] = self.signature
        else:
            # 使用 password 现场生成签名
            payload["signature"] = build_signature(self.name, self.password, ts)  # type: ignore[arg-type]

        # login 的 timestamp 必须和签名中的一致
        params = {"timestamp": str(ts)}

        data = self._request(
            method="POST",
            path="/v1/cl/user/login",
            params=params,
            json_body=payload,
            need_timestamp=False,  # 已在 params 中手动放入 ts
            add_session_id=False,
        )

        # 从结果中提取 session_id
        self.session_id = data.get("result", {}).get("session_id")
        if not self.session_id:
            raise ApiError(f"登录成功但未返回 session_id: {data}")

        return data

    def get_port_list(self, timestamp: Optional[int] = None) -> Dict[str, Any]:
        """
        GET /v1/cl/port/list
        """
        params: Dict[str, Any] = {}
        if timestamp is not None:
            params["timestamp"] = str(int(timestamp))

        return self._request(
            method="GET",
            path="/v1/cl/port/list",
            params=params,
            add_session_id=True,
        )

    def create_testcase(
        self,
        testcase_name: str,
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        """
        POST /v1/cl/testcase/create
        """
        payload = {
            "overwrite": overwrite,
            "testcase_name": testcase_name,
        }

        return self._request(
            method="POST",
            path="/v1/cl/testcase/create",
            json_body=payload,
            add_session_id=True,
        )

    def logout(self, timestamp: Optional[int] = None) -> Dict[str, Any]:
        """
        POST /v1/cl/user/logout
        Query: timestamp, session_id
        Body: { "name": name }
        """
        if not self.session_id:
            # 如果根本没登录成功，直接返回一个空结果，避免 finally 里又抛异常
            return {"message": "no session_id, skip logout"}

        params: Dict[str, Any] = {}
        if timestamp is not None:
            params["timestamp"] = str(int(timestamp))

        payload = {"name": self.name}

        data = self._request(
            method="POST",
            path="/v1/cl/user/logout",
            params=params,
            json_body=payload,
            add_session_id=True,
        )

        # 登出后清空本地 session_id
        self.session_id = None
        return data

    def get_network_list(self) -> Dict[str, Any]:
        """
        GET /v1/cl/network/list
        """
        return self._request(
            method="GET",
            path="/v1/cl/network/list",
            add_session_id=True,
        )

    def get_profile_list(self) -> Dict[str, Any]:
        """
        GET /v1/cl/load/profile/list
        """
        return self._request(
            method="GET",
            path="/v1/cl/load/profile/list",
            add_session_id=True,
        )

    def fetch_network(self, network_id: int) -> Dict[str, Any]:
        """
        POST /v1/cl/network/fetch
        Query: timestamp, session_id
        Body: { "network_id": network_id}
        """
        payload = {"network_id": network_id}

        return self._request(
            method="POST",
            path="/v1/cl/network/fetch",
            add_session_id=True,
            json_body=payload
        )

    def get_component_list(self) -> Dict[str, Any]:
        """
        GET /v1/cl/testcase/component/list
        """
        return self._request(
            method="GET",
            path="/v1/cl/testcase/component/list",
            add_session_id=True,
        )

    def get_ddos_attack_flow_list(self) -> Dict[str, Any]:
        """
        GET /v1/cl/ddos/attack/flow/list
        """
        return self._request(
            method="GET",
            path="/v1/cl/ddos/attack/flow/list",
            add_session_id=True,
        )

    def get_ddos_attack_list(self) -> Dict[str, Any]:
        """
        GET /v1/cl/ddos/attack/list
        """
        return self._request(
            method="GET",
            path="/v1/cl/ddos/attack/list",
            add_session_id=True,
        )
    
    def get_attack_profile(self, attack_profile_id: int) -> Dict[str, Any]:
        """
        Post /v1/cl/ddos/attack/profile/fetch
        Query: timestamp, session_id
        Body: { "attack_profile_id": attack_profile_id}
        """
        payload = {"attack_profile_id": attack_profile_id}

        return self._request(
            method="POST",
            path="/v1/cl/ddos/attack/profile/fetch",
            add_session_id=True,
            json_body=payload
        )

    def delete_testcase(self, testcase_id: array) -> Dict[str, Any]:
        """
        POST /v1/cl/testcase/delete
        Query: timestamp, session_id
        Body: { "testcase_id": testcase_id}
        """
        payload = {"testcase_id": testcase_id}

        return self._request(
            method="POST",
            path="/v1/cl/testcase/delete",
            add_session_id=True,
            json_body=payload
        )

    def fetch_testcase_param(self, testcase_id_list: list) -> Dict[str, Any]:
        """
        POST /v1/cl/testcase/delete
        Query: timestamp, session_id
        Body: { "testcase_id": testcase_id}
        """
        payload = {"testcase_id": testcase_id_list}

        return self._request(
            method="POST",
            path="/v1/cl/testcase/param/fetch",
            add_session_id=True,
            json_body=payload
        )
    
    def save_testcase(self, testcase_id: int, testcase_info: TestcaseInfo) -> Dict[str, Any]:
        """
        POST /v1/cl/testcase/save
        Query: timestamp, session_id
        Body: { "testcase_id": testcase_id, "testcase_info": testcase_info}
        """
        payload = {"testcase_id": testcase_id, "testcase_info": testcase_info.model_dump()}

        return self._request(
            method="POST",
            path="/v1/cl/testcase/save",
            add_session_id=True,
            json_body=payload
        )

    def get_ddos_attack_profile_list(self) -> Dict[str, Any]:
        """
        GET  /v1/cl/ddos/attack/profile/list
        """
        return self._request(
            method="GET",
            path="/v1/cl/ddos/attack/profile/list",
            add_session_id=True,
        )

    def set_basic_data(self, attack_name: str) -> BasicData:
        """
        set basic_data for attack
        """
        attack_basic_data = BasicData(
        name = attack_name, #TODO 搜索得到
        desc="",
        client_tags=["client6"], #TODO 搜索得到
        server_tags=["server6"], #TODO 搜索得到
        disable=False
        )
        return attack_basic_data

    def set_data_rate(self) -> DataRate:
        """
        set data_rate for attack, min_rate and max_rate is configurable.
        """
        attack_data_rate = DataRate(
            unlimited=False,
            unit=1,
            type=0,
            min_rate=5154,
            max_rate=5154
        )
        return attack_data_rate

    def set_attack_profile_brief(self, profile_id: int, profile_name: str) -> AttackProfileBrief:
        """
        set attack_profile_brief for attack
        """
        attack_profile_brief = AttackProfileBrief(
            profile_id=profile_id,
            profile_name=profile_name,
            user_id=1
        )
        return attack_profile_brief

    # def set_flow_item(self) -> FlowItem:
    #     """
    #     set flow_item for attack
    #     """
    #     attack_flow_item = FlowItem(
    #         flow_id=1, #TODO 搜索得到
    #         user_id=1, 
    #         flow_name="UDP Flood Attack"  #TODO 搜索得到
    #     )
    #     return attack_flow_item

    
    def set_profile_detail(self) -> ProfileDetail:
        """
        set profile_detail for attack
        """
        attack_profile_detail = ProfileDetail(
            name="UDP Flood Attack", #TODO 搜索得到
            desc="",
            user_id=1
        )
        return attack_profile_detail

    def set_super_flow(self) -> SuperFlow:
        """
        set super_flow for attack
        """
        attack_super_flow = SuperFlow(
            load_profile_type=0,
            max_flows=80000,  # TODO 计算得出
            max_flow_rate=80000, # TODO 计算得出
            max_flow_attempts=0,
            enable_conn_ctrl=False,
            max_outstanding_conns=1000,
            enable_bandwidth_ctrl=False,
            enable_max_flows=True,
            flow_timeout=2000
        )
        return attack_super_flow


    def set_load_profile(self) -> LoadProfile:
        """
        set load_profile for attack
        """
        attack_load_profile = LoadProfile(
            default=DefaultProfile(ramp_up=Behav(behavior=1, duration=2), steady=Behav(behavior=1, duration=60), ramp_down=Behav(behavior=1, duration=2))
        )
        return attack_load_profile
    
    def set_src_port(self) -> SrcPort:
        """
        set src_port for attack
        """
        return SrcPort(
            type = 2,
            min = 1024,
            max = 65535,
            polling_mode = 0
        )
    
    def set_attack_module(self, profile_id: int, profile_name: str) -> AttackModule:
        basic_data = self.set_basic_data(profile_name)
        data_rate = self.set_data_rate()
        src_port = self.set_src_port()
        attack_profile = self.set_attack_profile_brief(profile_id, profile_name)
        super_flow = self.set_super_flow()
        load_profile = self.set_load_profile()
        
        return AttackModule(
            basic=basic_data,
            load_profile=load_profile,
            attack_profile=attack_profile,
            data_rate= data_rate,
            super_flow=super_flow,
            src_port=src_port,
            delay_start=2,
            delay_start_second=2,
        )
    
    def set_shared_settings(self, testcase_name: str) -> SharedSettings:
        shared_settings = SharedSettings()
        shared_settings.port_reset = True
        shared_settings.testcase_name = testcase_name
        shared_settings.network_id = 18
        shared_settings.network_name = "ZGC Scene Two Network"
        shared_settings.enable_cpu_usage = False
        shared_settings.enable_custom_stats = False
        shared_settings.sample_interval = 1
        return shared_settings

    def set_testcase_info(self, testcase_id: int, testcase_name: str, profile_id: int, profile_name: str) -> TestcaseInfo:
        testcase_info = TestcaseInfo()
        testcase_info.testcase_id = testcase_id
        attack_module = self.set_attack_module(profile_id, profile_name)
        shared_settings = self.set_shared_settings(testcase_name)
        testcase_info.ddos_attack_list = [attack_module]
        testcase_info.shared_settings = shared_settings
        testcase_info.component_tags = ["client6","server6"]
        return testcase_info

def find_attack_profile_id(attack_profile_list, attack_name):
    attack_name_lower = attack_name.lower()
    for profile in attack_profile_list:
        profile_name = profile.get("profile_name")
        if not profile_name:
            continue
        
        if attack_name_lower in profile_name.lower(): 
            profile_id = profile.get("profile_id")
            return profile_id, profile_name
    # 如果遍历完没有 return
    logging.error(f"未找到攻击 '{attack_name}' 的 profile_id")
    raise AttackNotFoundError("attack not found")

def extract_matched_ports(data: Dict[str, Any]) -> list[Dict[str, Any]]:
    """筛选出 is_reserved=True 且 test_running=False 的端口"""
    matched: list[Dict[str, Any]] = []
    for chassis in data.get("result", []):
        for card in chassis.get("card_list", []):
            for port in card.get("port_list", []):
                if port.get("is_reserved") and not port.get("test_running"):
                    matched.append({"port_id": port.get("port_id")})
    return matched


# ----------------- 示例入口 ----------------- #

if __name__ == "__main__":
    BASE_URL = "https://10.99.80.111:7070"
    NAME = "admin"
    PASSWORD = "admin"

    client = AlpsClient(
        base_url=BASE_URL,
        name=NAME,
        password=PASSWORD,
        observer="",      # "1" 强制登录 / "2" 观察者模式
        verify=False,     # 测试环境忽略证书
    )

    try:
        login_data = client.login()
        print("Login success:", login_data)

        # port_list_data = client.get_port_list()
        # matched_port_ids = extract_matched_ports(port_list_data)testcase/component/create
        # print("matched_port_ids:", matched_port_ids)

        # attack_profile_list_data = client.get_ddos_attack_profile_list()
        # attack_profile_list = attack_profile_list_data.get("result", {})
        # print("attack_profile_list: ", attack_profile_list)
        # attack_name = "UDP Flood Attack"
        # profile_id, profile_name  = find_attack_profile_id(attack_profile_list, attack_name)


        # testcase_name = f"TestCase_by_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # testcase_data = client.create_testcase(testcase_name=testcase_name, overwrite=True)
        # print("testcase_data:", testcase_data)
        # testcase_id = testcase_data.get("result", {}).get("testcase_id")
        # testcase_info = client.set_testcase_info(testcase_id, testcase_name, profile_id, profile_name)
        # testcase_save_result = client.save_testcase(testcase_id, testcase_info)
        # print("testcase_save_result:", testcase_save_result)


        # network_list = client.get_network_list()
        # print("network_list:", network_list)

        # profile_list = client.get_profile_list()
        # print("profile_list:", profile_list)

        # network_data = client.fetch_network(17)  # 17是zgc scene one network 的ID
        # print("network_data: ", network_data)

        # ddos_attack_flow_list = client.get_ddos_attack_flow_list()  # 17是zgc scene one network 的ID
        # print("ddos_attack_flow_list: ", ddos_attack_flow_list)

        # ddos_attack_list = client.get_ddos_attack_list()  # 获取攻击类型
        # print("ddos_attack_list: ", ddos_attack_list)

        component_list = client.get_component_list()
        print("component_list: ", component_list)

        # param_list = client.fetch_testcase_param(10850)
        # print("param_list: ", param_list)


    except ApiError as e:
        print("API error:", e)
    except requests.HTTPError as e:
        print("HTTP error:", e.response.status_code, e.response.text)
    except Exception as e:
        print("Unexpected error:", str(e))
    finally:
        try:
            logout_data = client.logout()
            print("Logout:", logout_data)
        except ApiError as e:
            print("Logout error:", e)
        print("=== 执行完成 ===")
