import json
import numpy as np
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from typing import List, Dict, Optional


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
    ):
        self.data_path = Path(data_path)
        self.label_path = Path(label_path) if label_path else None
        self.similarity_threshold = similarity_threshold

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

        self.records = confirmed
        if confirmed:
            self.emb_matrix = np.array(
                [r["intent_embedding"] for r in confirmed], dtype="float32"
            )
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
        intent_embedding: List[float],
        retrieved_apis: List[Dict],
        model_version: str,
    ) -> str:
        """
        Append a new pending experience to jsonl.
        """
        record = {
            "id": str(uuid4())[:8],
            "intent_text": intent_text,
            "intent_embedding": intent_embedding,
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
