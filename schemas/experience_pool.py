import json
import numpy as np
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from typing import List, Dict, Optional, Callable


class ExperiencePool:
    """
    Human-validated intent -> API experience memory.
    Backed by jsonl files (append-only).
    """

    def __init__(
        self,
        data_path: str,
        label_path: Optional[str] = None,
        similarity_threshold: float = 0.9,
        embedding_loader: Optional[Callable[[str], List[float]]] = None,
    ):
        self.data_path = Path(data_path)
        self.label_path = Path(label_path) if label_path else None
        self.similarity_threshold = similarity_threshold
        # 用于在内存中动态计算 embedding（例如通过外部 embedding 模型）
        self.embedding_loader = embedding_loader

        self.records: List[Dict] = []
        self.emb_matrix: Optional[np.ndarray] = None

    # ---------- public APIs ----------

    def load(self):
        """Load jsonl records and build in-memory index."""
        raw_records = self._load_jsonl(self.data_path)

        if self.label_path and self.label_path.exists():
            labels = self._load_jsonl(self.label_path)
            raw_records = self.merge(raw_records, labels)

        # only confirmed records participate in lookup
        confirmed = [r for r in raw_records if r.get("status") == "confirmed"]

        # 为了支持“不在 jsonl 中存 embedding”，这里对每条记录做一次处理：
        # 1. 如果记录里有 intent_embedding（旧数据），直接使用
        # 2. 如果没有且提供了 embedding_loader，则现算（只存在内存中，不写回文件）
        emb_list: List[List[float]] = []
        kept_records: List[Dict] = []
        for r in confirmed:
            emb = r.get("intent_embedding")
            if emb is None and self.embedding_loader is not None:
                try:
                    emb = self.embedding_loader(r.get("intent_text", ""))
                except Exception:
                    emb = None
            if emb is None:
                continue
            kept_records.append(r)
            emb_list.append(emb)

        self.records = kept_records
        if emb_list:
            self.emb_matrix = np.array(emb_list, dtype="float32")
            self._normalize_embeddings()
        else:
            self.emb_matrix = None

    def lookup(self, query_embedding: List[float]) -> Optional[Dict]:
        """
        Lookup a confirmed experience by cosine similarity.
        Return the full record if hit, else None.
        """
        if self.emb_matrix is None:
            return None

        q = np.asarray(query_embedding, dtype="float32")
        q = q / np.linalg.norm(q)

        sims = self.emb_matrix @ q
        idx = int(np.argmax(sims))
        score = float(sims[idx])

        if score >= self.similarity_threshold:
            hit = dict(self.records[idx])
            hit["_similarity"] = score
            return hit
        return None

    def append(
        self,
        intent_text: str,
        intent_embedding: Optional[List[float]],
        retrieved_apis: List[Dict],
        model_version: str,
    ) -> str:
        """
        Append a new pending experience to jsonl.
        """
        record = {
            "id": str(uuid4())[:8],
            "intent_text": intent_text,
            "retrieved_apis": retrieved_apis,
            "final_api": None,
            "status": "pending",
            "model_version": model_version,
            "created_at": datetime.utcnow().isoformat(),
        }

        with self.data_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return record["id"]

    def merge(self, records: List[Dict], labels: List[Dict]) -> List[Dict]:
        """
        Merge human labels into raw records (by id).
        Raw records are not modified on disk.
        """
        label_map = {l["id"]: l for l in labels}

        merged = []
        for r in records:
            rid = r.get("id")
            if rid in label_map:
                merged.append({**r, **label_map[rid]})
            else:
                merged.append(r)
        return merged

    # ---------- internal helpers ----------

    def _load_jsonl(self, path: Path) -> List[Dict]:
        records = []
        if not path.exists():
            return records
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))
        return records

    def _normalize_embeddings(self):
        norms = np.linalg.norm(self.emb_matrix, axis=1, keepdims=True)
        self.emb_matrix = self.emb_matrix / norms
