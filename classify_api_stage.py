"""
扫描 xrt_openapi.jsonl 前504行，使用 stage.jinja 模板进行分类
输出格式符合 resource.json 的 schema 约束
"""
import asyncio
import json
import re
from typing import Dict, Any, Optional, Literal
from pathlib import Path
from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import PromptTemplate
from utils.file_process import load_jinja_template, load_api_jsonl
from utils.logger import get_logger
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

load_dotenv()
def extract_api_info(api_item: Dict[str, Any]) -> Dict[str, str]:
    """
    从API项中提取信息用于模板填充
    
    Returns:
        dict with keys: api_path, http_method, api_description, 
                       request_schema_summary, response_schema_summary
    """
    content_str = api_item.get("content", "{}")
    try:
        content = json.loads(content_str)
    except json.JSONDecodeError:
        content = {}
    
    # 提取API路径
    api_path = content.get("name", api_item.get("title", ""))
    if api_path.startswith("paths."):
        api_path = api_path.replace("paths.", "")
    
    # 提取HTTP方法和操作信息
    http_method = None
    operation = None
    
    for method in ["get", "post", "put", "delete", "patch"]:
        if method in content:
            http_method = method.upper()
            operation = content[method]
            break
    
    if not operation:
        # 如果没有找到方法，尝试从title推断
        title = api_item.get("title", "")
        if "post" in title.lower() or "/create" in title.lower() or "/save" in title.lower():
            http_method = "POST"
        elif "get" in title.lower() or "/list" in title.lower() or "/fetch" in title.lower():
            http_method = "GET"
        else:
            http_method = "POST"  # 默认值
        operation = {}
    
    # 提取描述
    api_description = operation.get("summary", "")
    
    # 提取请求参数摘要
    parameters = operation.get("parameters", [])
    request_summary_parts = []
    for param in parameters:
        param_name = param.get("name", "")
        param_type = param.get("type", "")
        param_desc = param.get("description", "")
        if param_name:
            if param_desc:
                request_summary_parts.append(f"{param_name}({param_type}): {param_desc}")
            else:
                request_summary_parts.append(f"{param_name}({param_type})")
    
    # 检查是否有body参数
    body_params = [p for p in parameters if p.get("in") == "body"]
    if body_params:
        for body_param in body_params:
            schema = body_param.get("schema", {})
            if "$ref" in schema:
                ref = schema["$ref"]
                request_summary_parts.append(f"body: {ref}")
            else:
                request_summary_parts.append("body: JSON object")
    
    request_schema_summary = "; ".join(request_summary_parts) if request_summary_parts else "无请求参数"
    
    # 提取响应字段摘要
    responses = operation.get("responses", {})
    response_summary_parts = []
    if "200" in responses:
        response_200 = responses["200"]
        schema = response_200.get("schema", {})
        if "$ref" in schema:
            ref = schema["$ref"]
            response_summary_parts.append(f"响应结构: {ref}")
        elif "type" in schema:
            response_summary_parts.append(f"响应类型: {schema['type']}")
        else:
            response_summary_parts.append("响应: JSON对象")
    
    response_schema_summary = "; ".join(response_summary_parts) if response_summary_parts else "无响应信息"
    
    return {
        "api_path": api_path,
        "http_method": http_method or "POST",
        "api_description": api_description,
        "request_schema_summary": request_schema_summary,
        "response_schema_summary": response_schema_summary
    }


class ResourceClassification(BaseModel):
    """API分类结果模型，符合resource.json的schema"""
    api_path: str = Field(..., description="API路径")
    resource: str = Field(..., description="逻辑资源名称")
    capability: Literal[
        "login", "logout", "list", "search", "fetch", "create", "update",
        "update_param", "save", "save_as", "reserve", "release", "run",
        "stop", "stats_query", "other"
    ] = Field(..., description="能力类型")
    stage: Literal[
        "authentication", "port_prepare", "port_reserve", "testcase_prepare",
        "network_config", "load_profile_config", "component_config",
        "testcase_finalize", "testcase_execute", "stats_collect",
        "resource_cleanup", "logout"
    ] = Field(..., description="阶段")
    affects_workflow: bool = Field(..., description="是否影响工作流结构")
    confidence: Literal["high", "medium", "low"] = Field(..., description="置信度")


def validate_output(output_dict: Dict[str, Any]) -> Optional[ResourceClassification]:
    """
    验证输出是否符合resource.json的schema
    返回验证后的模型对象，如果验证失败返回None
    """
    try:
        return ResourceClassification.model_validate(output_dict)
    except ValidationError:
        return None


def parse_llm_output(llm_output: str) -> Optional[Dict[str, Any]]:
    """
    解析LLM输出为JSON格式
    """
    # 尝试提取JSON部分
    # 移除可能的markdown代码块标记
    text = llm_output.strip()
    
    # 尝试找到JSON对象
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # 如果没找到，尝试直接解析整个文本
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def classify_api(api_item: Dict[str, Any], llm_chain, logger) -> Optional[Dict[str, Any]]:
    """
    对单个API进行分类
    """
    # 提取API信息
    api_info = extract_api_info(api_item)
    
    logger.info("处理API: %s (%s)", api_info['api_path'], api_info['http_method'])
    
    try:
        # 调用LLM
        result = await llm_chain.ainvoke({
            "api_path": api_info["api_path"],
            "http_method": api_info["http_method"],
            "api_description": api_info["api_description"],
            "request_schema_summary": api_info["request_schema_summary"],
            "response_schema_summary": api_info["response_schema_summary"]
        })
        
        llm_output = result.content.strip()
        logger.debug("LLM输出: %s", llm_output)
        
        # 解析输出
        output_dict = parse_llm_output(llm_output)
        
        if not output_dict:
            logger.warning("无法解析LLM输出: %s", api_info['api_path'])
            return None
        
        # 添加api_path（如果LLM没有输出）
        if "api_path" not in output_dict:
            output_dict["api_path"] = api_info["api_path"]
        
        return output_dict
        
    except Exception as e:
        logger.error("处理API时出错 %s: %s", api_info['api_path'], str(e))
        return None


async def main():
    logger = get_logger("ClassifyAPIStage")
    
    # 配置
    input_file = "inputs/xrt_openapi.jsonl"
    template_path = "prompts/stage.jinja"
    output_file = "outputs/api_stage_classification.jsonl"
    max_lines = 504
    
    logger.info("开始处理，读取前%d行API", max_lines)
    
    # 加载模板
    template_str = load_jinja_template(template_path)
    
    # 初始化LLM
    llm = ChatTongyi(model="qwen-max")
    
    # 创建PromptTemplate和chain
    prompt_template = PromptTemplate(
        input_variables=["api_path", "http_method", "api_description", 
                        "request_schema_summary", "response_schema_summary"],
        template=template_str,
        template_format="jinja2"
    )
    chain = prompt_template | llm
    
    # 读取API数据
    apis = load_api_jsonl(input_file)
    apis_to_process = apis[:max_lines]
    
    logger.info("共需处理 %d 个API", len(apis_to_process))
    
    # 处理每个API
    results = []
    success_count = 0
    fail_count = 0
    
    for idx, api_item in enumerate(apis_to_process, 1):
        logger.info("处理进度: %d/%d", idx, len(apis_to_process))
        
        result = await classify_api(api_item, chain, logger)
        
        if result:
            # 验证结果
            validated = validate_output(result)
            if validated:
                # 转换为字典保存
                result_dict = validated.model_dump()
                results.append(result_dict)
                success_count += 1
                logger.info("✓ API %d 分类成功: %s", idx, result_dict.get('api_path', 'unknown'))
            else:
                fail_count += 1
                logger.error("✗ API %d 验证失败", idx)
                logger.error("  结果: %s", json.dumps(result, ensure_ascii=False))
        else:
            fail_count += 1
            logger.warning("✗ API %d 处理失败", idx)
    
    # 保存结果
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    
    logger.info("处理完成!")
    logger.info("成功: %d, 失败: %d", success_count, fail_count)
    logger.info("结果已保存到: %s", output_file)


if __name__ == "__main__":
    asyncio.run(main())

