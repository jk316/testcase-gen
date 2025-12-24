import json
import re
from langchain_core.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models import ChatTongyi
from sentence_transformers import CrossEncoder
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from utils.logger import get_logger
from utils.file_process import load_jinja_template
import os


class ApiIntentIndex:
    def __init__(
        self,
        llm: ChatTongyi,
        embedding: DashScopeEmbeddings,
        prompt_template: str,
        logger=None,
        recall_size: int = 50, # recall的数量
        rerank_size: int = 10, # rerank的数量
        top_k: int = 3,       # 最终返回的数量
        cross_encoder_model: str = "models/ms-marco-MiniLM-L-6-v2"  # cross-encoder模型
    ):
        self.llm = llm
        self.embedding = embedding
        self.logger = logger or get_logger()

        # 初始化 api description prompt 生成模板
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
        
        # 初始化 rerank prompt 模板
        rerank_template_str = load_jinja_template("prompts/rerank.jinja")
        self.rerank_prompt = PromptTemplate(
            input_variables=["query", "candidate_info"],
            template=rerank_template_str,
            template_format="jinja2"
        )
        
        # 初始化 cross-encoder 模型
        self.logger.info(f"Loading cross-encoder model: {cross_encoder_model}")
        self.cross_encoder = CrossEncoder(cross_encoder_model)
        self.logger.info("Cross-encoder model loaded successfully")

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

    def search(self, intent: str, recall_size: int = None):
        """
        根据测试意图检索相关 API
        
        Args:
            intent: 测试意图查询文本
            recall_size: 召回数量，如果为None则使用初始化时的recall_size
            
        Returns:
            重排序后的top_k个API结果
        """
        if self.vector_store is None:
            raise RuntimeError("Vector store not initialized. Call build_from_apis() first.")

        # 使用向量检索召回候选集
        recall_k = recall_size if recall_size is not None else self.recall_size
        self.logger.info(f"Recalling top {recall_k} candidates from vector store")
        
        candidates = self.vector_store.similarity_search(
            query=intent,
            k=recall_k
        )
        
        self.logger.info(f"Recalled {len(candidates)} candidates")
        
        # 使用cross-encoder重排序
        reranked_results = self.rerank_with_cross_encoder(intent, candidates)
        
        # 使用LLM进一步重排序（作为cross-encoder的下一步）
        if reranked_results:
            reranked_results = self.rerank_with_llm(intent, reranked_results)
        
        return reranked_results

    def rerank_with_cross_encoder(self, query: str, candidates: List) -> List[Tuple[Dict, float]]:
        """
        使用 Cross-Encoder 对候选结果进行重排序
        
        Args:
            query: 查询文本（测试意图）
            candidates: 候选API列表（FAISS检索结果）
            
        Returns:
            按相关性得分排序后的结果列表，每个元素为(candidate, score)元组
        """
        if not candidates:
            self.logger.warning("No candidates to rerank")
            return []
        
        self.logger.info(f"Reranking {len(candidates)} candidates with cross-encoder")
        
        # 准备cross-encoder的输入对：(query, document)
        pairs = []
        for candidate in candidates:
            # 从候选结果中提取文本内容
            doc_text = candidate.page_content
            pairs.append([query, doc_text])
        
        # 使用cross-encoder计算相关性分数
        scores = self.cross_encoder.predict(pairs)
        
        # 将候选结果和分数配对
        scored_candidates = []
        for i, candidate in enumerate(candidates):
            score = float(scores[i])
            scored_candidates.append((candidate, score))
            self.logger.debug(
                f"API: {candidate.metadata.get('title', 'N/A')} | "
                f"Score: {score:.4f}"
            )
        
        # 按分数降序排序
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 返回top_k个结果
        top_results = scored_candidates[:self.top_k]
        
        self.logger.info(
            f"Reranking complete. Top {len(top_results)} results selected. "
            f"Score range: [{top_results[-1][1]:.4f}, {top_results[0][1]:.4f}]"
        )
        
        return top_results
    
    def rerank_with_llm(self, query: str, candidates: List[Tuple]) -> List[Tuple]:
        """
        使用 LLM 对候选结果进行重排序（作为 cross-encoder 的下一步）
        
        Args:
            query: 查询文本（测试意图）
            candidates: 候选结果列表，每个元素为 (candidate, score) 元组
                       其中 candidate 是 FAISS 检索结果，包含 page_content 和 metadata
            
        Returns:
            重排序后的候选结果列表，格式与输入相同
        """
        if not candidates:
            self.logger.warning("No candidates to rerank with LLM")
            return []
        
        self.logger.info(f"Reranking {len(candidates)} candidates with LLM")
        
        # 准备候选结果的格式化信息
        candidate_info = []
        for idx, (candidate, score) in enumerate(candidates):
            api_title = candidate.metadata.get('title', 'N/A')
            api_id = candidate.metadata.get('id', 'N/A')
            description = candidate.page_content[:500]  # 限制长度避免 prompt 过长
            
            candidate_info.append({
                'index': idx,
                'id': api_id,
                'title': api_title,
                'description': description,
                'cross_encoder_score': float(score)
            })
        
        # 构建 LLM reranking prompt
        rerank_prompt = self._build_rerank_prompt(query, candidate_info)
        
        try:
            # 调用 LLM 进行重排序
            response = self.llm.invoke(rerank_prompt)
            result_text = response.content.strip()
            
            # 解析 LLM 返回的排序结果
            reranked_indices = self._parse_llm_rerank_result(result_text, len(candidates))
            
            # 根据 LLM 的排序重新组织候选结果
            reranked_candidates = []
            for idx in reranked_indices:
                if 0 <= idx < len(candidates):
                    reranked_candidates.append(candidates[idx])
                else:
                    self.logger.warning(f"Invalid index {idx} from LLM, skipping")
            
            # 如果解析失败，返回原始顺序
            if not reranked_candidates:
                self.logger.warning("Failed to parse LLM rerank result, returning original order")
                return candidates
            
            # 确保所有候选结果都被包含（处理 LLM 可能遗漏的情况）
            included_indices = set(reranked_indices)
            for idx, candidate in enumerate(candidates):
                if idx not in included_indices:
                    reranked_candidates.append(candidate)
            
            self.logger.info(
                f"LLM reranking complete. Reordered {len(reranked_candidates)} candidates"
            )
            
            return reranked_candidates
            
        except Exception as e:
            self.logger.error(f"Error during LLM reranking: {e}", exc_info=True)
            self.logger.warning("Falling back to original order")
            return candidates
    
    def _build_rerank_prompt(self, query: str, candidate_info: List[Dict]) -> str:
        """
        构建 LLM 重排序的 prompt
        
        Args:
            query: 查询文本
            candidate_info: 候选结果信息列表
            
        Returns:
            prompt 文本
        """
        return self.rerank_prompt.format(
            query=query,
            candidate_info=candidate_info  # 直接传递列表，模板会迭代处理
        )
    
    def _parse_llm_rerank_result(self, result_text: str, num_candidates: int) -> List[int]:
        """
        解析 LLM 返回的排序结果
        
        Args:
            result_text: LLM 返回的文本
            num_candidates: 候选结果总数
            
        Returns:
            排序后的索引列表
        """
        # 方法1: 优先尝试逗号分隔的列表（最符合 prompt 要求）
        # 匹配类似 "2,0,1,3" 或 "2, 0, 1, 3" 的格式
        comma_pattern = r'\b(?:\d+\s*,\s*)+\d+\b'
        comma_match = re.search(comma_pattern, result_text)
        if comma_match:
            parts = comma_match.group().split(',')
            indices = []
            for part in parts:
                part = part.strip()
                if part.isdigit():
                    idx = int(part)
                    if 0 <= idx < num_candidates:
                        indices.append(idx)
            # 验证：索引不重复且有效
            if indices and len(set(indices)) == len(indices):
                return indices
        
        # 方法2: 尝试解析 JSON 格式（备用方案）
        try:
            json_match = re.search(r'\[[\d\s,]+\]', result_text)
            if json_match:
                indices = json.loads(json_match.group())
                indices = [int(i) for i in indices if 0 <= int(i) < num_candidates]
                # 验证：去重且不重复
                unique_indices = []
                seen = set()
                for idx in indices:
                    if idx not in seen:
                        seen.add(idx)
                        unique_indices.append(idx)
                if unique_indices and len(unique_indices) == len(indices):
                    return unique_indices
        except Exception:
            pass
        
        # 如果所有方法都失败，返回空列表
        self.logger.warning(
            f"Failed to parse LLM result. Expected comma-separated indices, got: {result_text[:200]}"
        )
        return []
    


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