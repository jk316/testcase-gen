from dataclasses import dataclass
from typing import Dict, Any, NamedTuple


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