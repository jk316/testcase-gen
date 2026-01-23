"""
Redis API 参数查询工具
根据 Redis key 格式查询 API 的输入和输出参数
"""
import json
from typing import Dict, Any, Optional
from langchain_core.tools import tool
import redis
from config import get_config
from build_api_index_redis import get_redis_client, build_redis_key
from utils.logger import get_logger


logger = get_logger(__name__)
config = get_config()

# 全局 Redis 客户端（单例模式）
_redis_client: Optional[redis.Redis] = None


def get_redis_client_singleton() -> redis.Redis:
    """获取 Redis 客户端单例"""
    global _redis_client
    if _redis_client is None:
        _redis_client = get_redis_client(config.redis)
    return _redis_client


def query_api_params_from_redis(
    http_method: str,
    url_path: str
) -> Dict[str, Any]:
    """
    从 Redis 查询 API 参数
    
    Args:
        http_method: HTTP 方法（如 "POST", "GET"）
        url_path: URL 路径（如 "/v1/cl/user/login"）
        
    Returns:
        包含 input_params 和 output_params 的字典
        如果查询失败或不存在，返回空字典
    """
    try:
        redis_client = get_redis_client_singleton()
        
        # 构建 Redis Key
        key = build_redis_key(http_method, url_path)
        
        # 从 Redis Hash 中获取参数
        result = redis_client.hgetall(key)
        
        if not result:
            logger.warning(f"Redis 中未找到 key: {key}")
            return {
                "input_params": [],
                "output_params": []
            }
        
        # 解析 JSON 字符串
        input_params = json.loads(result.get("input_params", "[]"))
        output_params = json.loads(result.get("output_params", "[]"))
        
        return {
            "input_params": input_params,
            "output_params": output_params
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"解析 Redis 数据失败: {e}")
        return {
            "input_params": [],
            "output_params": []
        }
    except Exception as e:
        logger.error(f"查询 Redis API 参数失败: {e}", exc_info=True)
        return {
            "input_params": [],
            "output_params": []
        }


@tool
def get_api_params(http_method: str, url_path: str) -> Dict[str, Any]:
    """
    根据 HTTP 方法和 URL 路径从 Redis 查询 API 的输入和输出参数。
    
    Redis key 格式: api:params:<HTTP_METHOD>:<URL_PATH>
    
    Args:
        http_method: HTTP 方法，如 "POST", "GET", "PUT", "DELETE", "PATCH"（不区分大小写，会自动转换为大写）
        url_path: URL 路径，如 "/v1/cl/user/login"（必须以 / 开头）
        
    Returns:
        包含以下字段的字典:
        - input_params: 输入参数列表，每个参数包含 name, location, json_path, type, required, desc
        - output_params: 输出参数列表，每个参数包含 name, location, json_path, type, required, desc
        
    Example:
        result = get_api_params("POST", "/v1/cl/user/login")
        # 返回:
        # {
        #     "input_params": [
        #         {
        #             "name": "username",
        #             "location": "body",
        #             "json_path": "body.username",
        #             "type": "string",
        #             "required": true,
        #             "desc": "用户名"
        #         },
        #         ...
        #     ],
        #     "output_params": [
        #         {
        #             "name": "token",
        #             "location": "response.body",
        #             "json_path": "body.token",
        #             "type": "string",
        #             "required": true,
        #             "desc": "访问令牌"
        #         },
        #         ...
        #     ]
        # }
    """
    # 规范化 HTTP 方法（转换为大写）
    http_method = http_method.upper()
    
    # 规范化 URL 路径（确保以 / 开头）
    if not url_path.startswith("/"):
        url_path = "/" + url_path
    
    logger.info(f"查询 API 参数: {http_method} {url_path}")
    
    result = query_api_params_from_redis(http_method, url_path)
    
    logger.info(
        f"查询结果: 输入参数 {len(result.get('input_params', []))} 个, "
        f"输出参数 {len(result.get('output_params', []))} 个"
    )
    
    return result


# 导出工具列表，方便在其他地方使用
__all__ = ["get_api_params"]
