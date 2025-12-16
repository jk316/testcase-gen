import json
from typing import List, Dict, Optional
from pathlib import Path
from utils.logger import get_logger
import os
from langchain_core.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models import ChatTongyi


class ApiIntentIndex:
    def __init__(
        self,
        llm: ChatTongyi,
        embedding: DashScopeEmbeddings,
        prompt_template: str,
        logger=None,
        recall_size: int = 50, # recall的数量
        rerank_size: int = 10, # rerank的数量
        top_k: int = 3       # 最终返回的数量
    ):
        self.llm = llm
        self.embedding = embedding
        self.logger = logger or get_logger()

        self.prompt = PromptTemplate(
            input_variables=["id", "title", "content"],
            template=prompt_template,
            template_format="jinja2" 
        )
        self.recall_size = recall_size
        self.rerank_size = rerank_size
        self.top_k = top_k
        self.chain = self.prompt | self.llm
        self.vector_store: FAISS | None = None

    # ----------- 构建阶段 -----------

    def generate_descriptions(
        self,
        apis: List[Dict],
        output_path: str = "outputs/api_descriptions.jsonl"
    ) -> List[Dict]:

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 已存在的结果，用于断点续跑
        existed = {}
        if os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                for line in f:
                    item = json.loads(line)
                    existed[item["id"]] = item

        total = len(apis)
        self.logger.info(
            f"Generating descriptions for {total} APIs "
            f"(existing: {len(existed)})"
        )

        results = list(existed.values())

        with open(output_path, "a", encoding="utf-8") as fw:
            for i, api in enumerate(apis, start=1):
                if api["id"] in existed:
                    self.logger.info(
                        f"[SKIP] {i}/{total} {api['title']}"
                    )
                    continue

                self.logger.info(
                    f"[LLM] {i}/{total} {api['title']}"
                )

                desc = self._generate_description(api)

                item = {
                    "id": api["id"],
                    "title": api["title"],
                    "description": desc
                }

                fw.write(json.dumps(item, ensure_ascii=False) + "\n")
                fw.flush()   # 关键
                os.fsync(fw.fileno())

                results.append(item)

        self.logger.info("All API descriptions generated")
        return results

    def build_index_from_descriptions(self, items: List[Dict]):
        """
        从 description 构建向量索引
        """
        self.logger.info("Building FAISS index from descriptions")

        texts = [item["description"] for item in items]
        metadatas = [
            {"id": item["id"], "title": item["title"]}
            for item in items
        ]

        self.vector_store = FAISS.from_texts(
            texts=texts,
            embedding=self.embedding,
            metadatas=metadatas
        )

        self.logger.info("FAISS index built successfully")

    def build_from_apis(self, 
                        apis: List[Dict],
                        description_path: str = "outputs/api_descriptions.jsonl"
        ):
        """
        从 API jsonl 数据构建向量索引
        """
        descriptions = self._load_descriptions_if_exists(description_path)
        if descriptions is None or len(descriptions) < len(apis):
            self.logger.info("Descriptions incomplete, regenerating missing ones...")
            descriptions = self.generate_descriptions(apis, description_path)
        else:
            self.logger.info("Existing descriptions found, skipping generation.")
        self.build_index_from_descriptions(descriptions)
    
    def _load_descriptions_if_exists(self, path: str) -> Optional[List[Dict]]:
        if not os.path.exists(path):
            return None

        self.logger.info(f"Loading API descriptions from {path}")

        items = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                items.append(json.loads(line))

        self.logger.info(f"Loaded {len(items)} API descriptions")
        return items
    
    def _generate_description(self, api: Dict) -> str:
        """
        调用 LLM 为单个 API 生成语义描述
        """
        self.logger.info(f"API content: {api['content']}")
        prompt_text = self.prompt.format(
            id=api["id"],
            title=api["title"],
            content=api["content"]
        )
        self.logger.info(f"FINAL PROMPT:\n{prompt_text}")

        result = self.chain.invoke({
            "id": api["id"],
            "title": api["title"],
            "content": api["content"]
        })
        return result.content.strip()

    # ----------- 查询阶段 -----------

    def search(self, intent: str, recall_size: int):
        """
        根据测试意图检索相关 API
        """
        if self.vector_store is None:
            raise RuntimeError("Vector store not initialized. Call build_from_apis() first.")

        candidates = self.vector_store.similarity_search(
            query=intent,
            k=self.recall_size
        )
        best_api = self.rerank_with_llm(intent, candidates)
        return best_api

    def rerank_with_llm(self, query: str, candidates: List):
        """
        使用 LLM 对候选结果进行重排序
        """
        # 这里可以实现更复杂的重排序逻辑
        return candidates  # 暂时返回原始顺序
    


    def save(self, path: str):
        self.logger.info(f"Saving FAISS index to {path}")
        if self.vector_store is None:
            raise RuntimeError("No vector store to save.")
        Path(path).mkdir(parents=True, exist_ok=True)
        self.vector_store.save_local(path)
        self.logger.info("FAISS index saved successfully")

    def load(self, path: str):
        self.logger.info(f"Loading FAISS index from {path}")
        self.vector_store = FAISS.load_local(
            path,
            self.embedding,
            allow_dangerous_deserialization=True
        )
        self.logger.info("FAISS index loaded successfully")