"""
构建 API 正向索引到 Redis
根据 xrt_openapi.jsonl 文件，递归提取每个 API 的输入和输出参数，
按照 req.txt 指定的数据结构格式存储到 Redis 中。
"""
import json
import redis
from typing import Dict, List, Any, Optional
from extract_api_params import (
    load_api_data,
    extract_api_params_from_title
)
from config import get_config
from utils.logger import get_logger


logger = get_logger(__name__)


def convert_to_redis_format(params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将提取的参数转换为 Redis 存储格式（req.txt 要求的格式）
    
    Args:
        params: 从 extract_api_params_from_title 提取的参数列表
        
    Returns:
        转换后的参数列表，格式符合 req.txt 要求
    """
    redis_params = []
    
    for param in params:
        # 提取字段
        name = param.get("name", "")
        full_path = param.get("full_path", "")
        location = param.get("location", "")
        param_type = param.get("type", "string")
        required = param.get("required", False)
        desc = param.get("desc", "")
        
        # 对于输出参数，location 应该是 "response.body"
        direction = param.get("direction", "input")
        if direction == "output":
            # 根据 req.txt，输出参数的 location 始终是 "response.body"
            location = "response.body"
        else:
            # 输入参数，location 可能是 query/path/header/body
            # 如果 full_path 包含 request.body，location 应该是 "body"
            if "request.body" in full_path:
                location = "body"
            elif full_path.startswith("request."):
                # 从 full_path 中提取 location
                # 例如 "request.query.field" -> "query"
                parts = full_path.split(".", 2)
                if len(parts) >= 2:
                    location = parts[1]  # query, path, header
                else:
                    location = "query"
        
        # json_path 使用 full_path，但需要规范化
        # 移除 "request." 或 "response." 前缀，只保留路径部分
        if full_path.startswith("request."):
            json_path = full_path.replace("request.", "", 1)
        elif full_path.startswith("response."):
            json_path = full_path.replace("response.", "", 1)
        else:
            json_path = full_path
        
        redis_param = {
            "name": name,
            "location": location,
            "json_path": json_path,
            "type": param_type,
            "required": required,
            "desc": desc
        }
        
        redis_params.append(redis_param)
    
    return redis_params


def build_redis_key(http_method: str, url_path: str) -> str:
    """
    构建 Redis Key
    
    Args:
        http_method: HTTP 方法（如 "POST", "GET"）
        url_path: URL 路径（如 "/v1/cl/user/login"）
        
    Returns:
        Redis Key 字符串，格式：api:params:<HTTP_METHOD>:<URL_PATH>
    """
    # 规范化 URL 路径
    # 从 "paths./v1/cl/user/login" 或 "/v1/cl/user/login" 提取路径
    if url_path.startswith("paths."):
        url_path = url_path.replace("paths.", "", 1)
    if not url_path.startswith("/"):
        url_path = "/" + url_path
    
    return f"api:params:{http_method}:{url_path}"


def get_redis_client(config) -> redis.Redis:
    """
    创建 Redis 客户端连接
    
    Args:
        config: RedisConfig 配置对象
        
    Returns:
        Redis 客户端实例
    """
    return redis.Redis(
        host=config.host,
        port=config.port,
        password=config.password,
        db=config.db,
        decode_responses=config.decode_responses
    )


def store_api_to_redis(
    redis_client: redis.Redis,
    http_method: str,
    url_path: str,
    input_params: List[Dict[str, Any]],
    output_params: List[Dict[str, Any]]
) -> bool:
    """
    将 API 参数存储到 Redis
    
    Args:
        redis_client: Redis 客户端实例
        http_method: HTTP 方法
        url_path: URL 路径
        input_params: 输入参数列表（已转换格式）
        output_params: 输出参数列表（已转换格式）
        
    Returns:
        是否成功存储
    """
    try:
        # 构建 Redis Key
        key = build_redis_key(http_method, url_path)
        
        # 将参数列表序列化为 JSON 字符串
        input_params_json = json.dumps(input_params, ensure_ascii=False)
        output_params_json = json.dumps(output_params, ensure_ascii=False)
        
        # 使用 Hash 结构存储
        redis_client.hset(
            key,
            mapping={
                "input_params": input_params_json,
                "output_params": output_params_json
            }
        )
        
        return True
    except Exception as e:
        logger.error(f"存储 API 到 Redis 失败: {http_method} {url_path}, 错误: {e}")
        return False


def process_api(
    api_title: str,
    api_data: Dict[str, Dict[str, Any]],
    redis_client: redis.Redis,
    ignore_titles: Optional[set] = None
) -> bool:
    """
    处理单个 API：提取参数并存储到 Redis
    
    Args:
        api_title: API 的 title（如 "paths./v1/cl/user/login"）
        api_data: API 数据映射
        redis_client: Redis 客户端实例
        ignore_titles: 需要忽略的 title 集合
        
    Returns:
        是否成功处理
    """
    try:
        # 提取参数
        params = extract_api_params_from_title(api_title, api_data, ignore_titles)
        
        if not params:
            logger.warning(f"API {api_title} 没有提取到参数，跳过")
            return False
        
        # 从 api_title 提取 HTTP 方法和路径
        api_item = api_data.get(api_title)
        if not api_item:
            logger.warning(f"API {api_title} 在数据中不存在")
            return False
        
        content = api_item.get("content", {})
        api_path = api_title.replace("paths.", "")
        
        # 提取 HTTP 方法
        http_method = "POST"  # 默认
        for method in ["get", "post", "put", "delete", "patch"]:
            if method in content:
                http_method = method.upper()
                break
        
        # 分离输入和输出参数
        input_params_raw = [p for p in params if p.get("direction") == "input"]
        output_params_raw = [p for p in params if p.get("direction") == "output"]
        
        # 转换为 Redis 格式
        input_params = convert_to_redis_format(input_params_raw)
        output_params = convert_to_redis_format(output_params_raw)
        
        # 存储到 Redis
        success = store_api_to_redis(
            redis_client,
            http_method,
            api_path,
            input_params,
            output_params
        )
        
        if success:
            logger.info(
                f"成功处理 API: {http_method} {api_path} "
                f"(输入参数: {len(input_params)}, 输出参数: {len(output_params)})"
            )
        
        return success
        
    except Exception as e:
        logger.error(f"处理 API {api_title} 时出错: {e}", exc_info=True)
        return False


def main():
    """主函数：遍历所有 API 并存储到 Redis"""
    config = get_config()
    logger.info("开始构建 API 正向索引到 Redis")
    
    # 加载 API 数据
    api_data_file = config.files.api_openapi_file
    logger.info(f"正在加载 API 数据: {api_data_file}")
    api_data = load_api_data(api_data_file)
    logger.info(f"已加载 {len(api_data)} 个 API 定义")
    
    # 连接 Redis
    logger.info(f"正在连接 Redis: {config.redis.host}:{config.redis.port}")
    try:
        redis_client = get_redis_client(config.redis)
        # 测试连接
        redis_client.ping()
        logger.info("Redis 连接成功")
    except Exception as e:
        logger.error(f"Redis 连接失败: {e}")
        return
    
    # 筛选出所有路径定义（以 "paths." 开头的 title）
    path_titles = [title for title in api_data.keys() if title.startswith("paths.")]
    logger.info(f"找到 {len(path_titles)} 个 API 路径")
    
    # 处理每个 API
    success_count = 0
    fail_count = 0
    
    for i, api_title in enumerate(path_titles, 1):
        logger.info(f"处理进度: {i}/{len(path_titles)} - {api_title}")
        
        if process_api(api_title, api_data, redis_client):
            success_count += 1
        else:
            fail_count += 1
    
    # 输出统计信息
    logger.info("=" * 60)
    logger.info("处理完成！")
    logger.info(f"成功: {success_count} 个 API")
    logger.info(f"失败: {fail_count} 个 API")
    logger.info(f"总计: {len(path_titles)} 个 API")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
