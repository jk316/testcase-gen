from dataclasses import dataclass
from typing import Dict, Any, NamedTuple, Literal
from pydantic import BaseModel, Field, ValidationError


@dataclass(frozen=True)
class ApiItem:
    id: str
    title: str
    content: str

@dataclass(frozen=True)
class DescriptionItem:
    id: str
    title: str
    description: str
   
@dataclass(frozen=True)
class IndexDocument:
    id: str
    title: str
    description: str
    metadata: Dict[str, Any] | None = None

@dataclass(frozen=True) #只读属性
class Candidate:
    content: str
    metadata: Dict[str, Any]


class RerankResult(NamedTuple):
    candidate: Candidate
    score: float

class ApiSemanticDescription(BaseModel):
    high_level_description: str = Field(
        ...,
        description="一句话高层业务描述，用于 embedding"
    )
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = Field(
        ...,
        description="HTTP 方法，必须是标准方法"
    )
    http_path: str = Field(
        ...,
        description="HTTP 路径，例如 /v1/user/login"
    )
    input_summary: str = Field(
        ...,
        description="接口输入的业务语义概括"
    )
    output_summary: str = Field(
        ...,
        description="接口输出的业务语义概括"
    )