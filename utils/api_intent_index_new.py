import json
import re
import shutil
from dataclasses import asdict
from langchain_core.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models import ChatTongyi
from langchain_core.documents import Document
from sentence_transformers import CrossEncoder
from typing import List, Dict, Optional
from pathlib import Path
from utils.logger import get_logger
from utils.file_process import load_jinja_template
from schemas.dto import ApiItem, DescriptionItem, Candidate, RerankResult, ApiSemanticDescription
from schemas.experience_pool import ExperiencePool
import os


class ApiIntentIndexNew:
    def __init__(
        self,
        llm: ChatTongyi,
        embedding: DashScopeEmbeddings,
        prompt_template: str,
        logger=None,
        recall_size: int = 50, # recall的数量
        rerank_size: int = 10, # rerank的数量
        top_k: int = 3,       # 最终返回的数量
        cross_encoder_model: str = r"C:\Users\fanzx\Documents\code\ms-marco-MiniLM-L6-v2",  # cross-encoder模型
        description_path: str = "outputs/api_descriptions.jsonl",  # description 文件路径
        experience_data_path: Optional[str] = None,
        experience_label_path: Optional[str] = None,
        experience_similarity_threshold: float = 0.9,
        experience_model_version: str = "unknown",
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
        self.description_path = description_path
        self.model_version = experience_model_version
        self.chain = self.prompt | self.llm
        self.vector_store: FAISS | None = None
        # 人类经验池（可选）
        self.experience_pool: Optional[ExperiencePool] = None
        if experience_data_path:
            self.experience_pool = ExperiencePool(
                data_path=experience_data_path,
                label_path=experience_label_path,
                similarity_threshold=experience_similarity_threshold,
            )
        
        # 初始化 rerank prompt 模板
        rerank_template_str = load_jinja_template("prompts/rerank.jinja")
        self.rerank_prompt = PromptTemplate(
            input_variables=["query", "candidate_info"],
            template=rerank_template_str,
            template_format="jinja2"
        )
        
        # 初始化简化的 rerank prompt 模板（用于直接对 Candidate 列表排序）
        rerank_simple_template_str = load_jinja_template("prompts/rerank_simple.jinja")
        self.rerank_simple_prompt = PromptTemplate(
            input_variables=["query", "candidate_info"],
            template=rerank_simple_template_str,
            template_format="jinja2"
        )

        if not os.path.isdir(cross_encoder_model):
            self.logger.error(
                f"CrossEncoder model path not found: {cross_encoder_model}"
            )
            raise ValueError(
                f"CrossEncoder model path not found: {cross_encoder_model}"
            )
        
        # 初始化 cross-encoder 模型
        self.logger.info(f"Loading cross-encoder model: {cross_encoder_model}")
        self.cross_encoder = CrossEncoder(cross_encoder_model, local_files_only=True)
        self.logger.info("Cross-encoder model loaded successfully")

    # ----------- 构建阶段 -----------

    async def generate_descriptions(
        self,
        apis: List[ApiItem],
        force_regenerate: bool = False
    ) -> List[DescriptionItem]:

        os.makedirs(os.path.dirname(self.description_path), exist_ok=True)

        # 如果强制重新生成，删除已有文件
        if force_regenerate and os.path.exists(self.description_path):
            self.logger.info(f"Force regenerate enabled, deleting existing file: {self.description_path}")
            os.remove(self.description_path)

        # 已存在的结果，用于断点续跑
        existed = {}
        if os.path.exists(self.description_path):
            with open(self.description_path, "r", encoding="utf-8") as f:
                for line in f:
                    item = json.loads(line)
                    existed[item["id"]] = item

        total = len(apis)
        self.logger.info(
            f"Generating descriptions for {total} APIs "
            f"(existing: {len(existed)})"
        )

        results = list(existed.values())

        with open(self.description_path, "a", encoding="utf-8") as fw:
            for i, api in enumerate(apis, start=1):
                # 过滤：只处理 paths 开头的 API，跳过 definitions 开头的
                title = api.title
                if not title.startswith("paths."):
                    self.logger.info(
                        f"[SKIP] {i}/{total} {api.title} (not paths, skipped)"
                    )
                    continue
                
                if api.id in existed:
                    self.logger.info(
                        f"[SKIP] {i}/{total} {api.title}"
                    )
                    continue

                self.logger.info(
                    f"[LLM] {i}/{total} {api.title}"
                )

                semantic_description = await self._generate_description(api)

                item = DescriptionItem(
                    id=api.id,
                    title=api.title,
                    description=semantic_description.high_level_description
                )

                fw.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
                fw.flush()   # 关键
                os.fsync(fw.fileno())

                results.append(item)

        self.logger.info(f"All API descriptions generated and saved to {self.description_path}")
        return results

    def build_index_from_descriptions(self, items: List[DescriptionItem]):
        """
        从 description 构建向量索引
        """
        self.logger.info("Building FAISS index from descriptions")

        texts = [item.description for item in items]
        metadatas = [
            {"id": item.id, "title": item.title}
            for item in items
        ]
        # 向量数据库中的内容是description，metadata是id和title
        self.vector_store = FAISS.from_texts(
            texts=texts,
            embedding=self.embedding,
            metadatas=metadatas
        )

        self.logger.info("FAISS index built successfully")

    async def build_from_apis(self, 
                        apis: List[ApiItem],
                        force_rebuild: bool = False
        ):
        """
        从 API jsonl 数据构建向量索引
        
        Args:
            apis: API 列表
            force_rebuild: 是否强制重新生成（删除已有文件）
        """
        if force_rebuild:
            self.logger.info("Force rebuild enabled, cleaning existing files...")
            self.clean()
        
        descriptions = self._load_descriptions_if_exists()
        if descriptions is None or len(descriptions) < len(apis):
            self.logger.info("Descriptions incomplete, regenerating missing ones...")
            descriptions = await self.generate_descriptions(apis, force_regenerate=force_rebuild)
        else:
            self.logger.info("Existing descriptions found, skipping generation.")
        self.build_index_from_descriptions(descriptions)
    
    def _load_descriptions_if_exists(self) -> Optional[List[DescriptionItem]]:
        if not os.path.exists(self.description_path):
            return None

        self.logger.info(f"Loading API descriptions from {self.description_path}")

        items = []
        with open(self.description_path, "r", encoding="utf-8") as f:
            for line in f:
                item_dict = json.loads(line)
                items.append(DescriptionItem(id=item_dict["id"], title=item_dict["title"], description=item_dict["description"]))

        self.logger.info(f"Loaded {len(items)} API descriptions")
        return items
    
    async def _generate_description(self, api: ApiItem) -> ApiSemanticDescription:
        """
        调用 LLM 为单个 API 生成语义描述
        """
        self.logger.info(f"API content: {api.content}")
        prompt_text = self.prompt.format(
            id=api.id,
            title=api.title,
            content=api.content
        )
        self.logger.info(f"FINAL PROMPT:\n{prompt_text}")

        result = await self.chain.ainvoke({
            "id": api.id,
            "title": api.title,
            "content": api.content
        })
        return ApiSemanticDescription.model_validate_json(result.content.strip(), strict=True)

    # ----------- 查询阶段 -----------

    async def search(self, intent: str, with_cross_encoder: bool = True) -> List[Candidate]:
        """
        根据测试意图检索相关 API
        
        Args:
            intent: 测试意图查询文本
            recall_size: 召回数量，如果为None则使用初始化时的recall_size
            with_cross_encoder: 是否使用 cross-encoder 进行重排序
                - True: 向量数据库 recall → cross-encoder 排序 → LLM 排序
                - False: 向量数据库 recall → 直接 LLM 排序
            
        Returns:
            重排序后的top_k个API结果
        """
        if self.vector_store is None:
            raise RuntimeError("Vector store not initialized. Call build_from_apis() first.")

        # 使用向量检索召回候选集
        self.logger.info(f"Recalling top {self.recall_size} candidates from vector store")
        
        docs: List[Document] = self.vector_store.similarity_search(
            query=intent,
            k=self.recall_size
        )

        self.logger.debug(f"Recalled docs: {docs}")
        
        candidates = [Candidate(content=doc.page_content, metadata=doc.metadata) for doc in docs]
        
        self.logger.info(f"Recalled {len(candidates)} candidates")
        
        if with_cross_encoder:
            # 使用cross-encoder重排序
            ce_reranked_results = self.rerank_with_cross_encoder(intent, candidates)
            
            # 使用LLM进一步重排序（作为cross-encoder的下一步）
            if ce_reranked_results:
                llm_reranked_results = await self.rerank_with_llm(intent, ce_reranked_results)
                # 将 RerankResult 转换为 Candidate
                final_results = [result.candidate for result in llm_reranked_results]
            else:
                final_results = []
        else:
            # 直接使用LLM排序
            final_results = await self.rerank(intent, candidates[:self.rerank_size])
            # 按 top_k 截取最终结果
            final_results = final_results[:self.top_k]

        # 将当前 intent 与 LLM 排序结果写入 ExperiencePool
        # self._log_experience(intent, final_results)

        return final_results

    def rerank_with_cross_encoder(self, query: str, candidates: List[Candidate]) -> List[RerankResult]:
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
            doc_text = candidate.content
            pairs.append([query, doc_text])
        
        # 使用cross-encoder计算相关性分数
        scores = self.cross_encoder.predict(pairs)
        
        # 将候选结果和分数配对
        scored_candidates = []
        for i, candidate in enumerate(candidates):
            score = float(scores[i])
            scored_candidates.append(RerankResult(candidate, score))
            self.logger.debug(
                f"API: {candidate.metadata.get('title', 'N/A')} | "
                f"Score: {score:.4f}"
            )
        
        # 按分数降序排序
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 返回top_k个结果
        top_results = scored_candidates[:self.rerank_size] # 重排序后的数量
        
        self.logger.debug(
            f"Cross-encoder reranking complete. Top {len(top_results)} results selected. "
            f"Score range: [{top_results[-1][1]:.4f}, {top_results[0][1]:.4f}]"
            f"Cross-encoder reranked_results: {top_results}"
        )
        

        return top_results
    
    async def rerank_with_llm(self, query: str, candidates: List[RerankResult]) -> List[RerankResult]:
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
        for idx, result in enumerate(candidates):
            candidate = result.candidate
            api_title = candidate.metadata.get('title', 'N/A')
            api_id = candidate.metadata.get('id', 'N/A')
            description = candidate.content[:500]  # 限制长度避免 prompt 过长
            score = result.score
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
            response = await self.llm.ainvoke(rerank_prompt)
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
            
            # 如果解析失败，返回原始顺序的前 top_k 个
            if not reranked_candidates:
                self.logger.warning("Failed to parse LLM rerank result, returning top_k from original order")
                return candidates[:self.top_k]
            
            # 确保所有候选结果都被包含（处理 LLM 可能遗漏的情况）
            included_indices = set[int](reranked_indices)
            for idx, candidate in enumerate(candidates):
                if idx not in included_indices:
                    reranked_candidates.append(candidate)
            
            # 按 top_k 截取最终结果
            top_k_results = reranked_candidates[:self.top_k]
            
            self.logger.info(
                f"LLM reranking complete. Reordered {len(reranked_candidates)} candidates, "
                f"returning top {len(top_k_results)} results. "
                f"LLM reranked_results: {top_k_results}"
            )
            
            return top_k_results
            
        except Exception as e:
            self.logger.error(f"Error during LLM reranking: {e}", exc_info=True)
            self.logger.warning("Falling back to original order, returning top_k results")
            # 异常情况下也返回 top_k 个结果
            return candidates[:self.top_k]
    
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
    
    def _log_experience(self, intent: str, ranked_candidates: List[Candidate]) -> None:
        """
        将当前 intent 与 LLM 排序后的结果写入 ExperiencePool 对应的 jsonl 文件。
        仅在初始化时配置了 experience_data_path 时生效。
        """
        if not self.experience_pool:
            return

        if not ranked_candidates:
            return

        try:
            # 计算 intent 的 embedding，作为经验向量
            intent_embedding = self.embedding.embed_query(intent)
        except Exception as e:
            self.logger.error(f"Failed to compute intent embedding for experience pool: {e}", exc_info=True)
            return

        # 将 LLM 排序后的候选结果转换为可序列化的结构
        retrieved_apis: List[Dict] = []
        for idx, cand in enumerate(ranked_candidates):
            api_id = cand.metadata.get("id")
            api_title = cand.metadata.get("title")
            retrieved_apis.append(
                {
                    "rank": idx,
                    "id": api_id,
                    "title": api_title
                }
            )

        try:
            record_id = self.experience_pool.append(
                intent_text=intent,
                intent_embedding=intent_embedding,
                retrieved_apis=retrieved_apis,
                model_version=self.model_version,
            )
            self.logger.info(f"Appended experience record to pool, id={record_id}")
        except Exception as e:
            # 写入失败不应影响主流程
            self.logger.error(f"Failed to append experience to pool: {e}", exc_info=True)
    
    async def rerank(self, query: str, candidates: List[Candidate]) -> List[Candidate]:
        """
        使用 LLM 对候选结果进行相关性排序
        
        Args:
            query: 查询文本（测试意图）
            candidates: 候选 API 列表（从向量数据库 recall 出来的结果）
            
        Returns:
            按相关性排序后的候选 API 列表
        """
        if not candidates:
            self.logger.warning("No candidates to rerank")
            return []
        
        self.logger.info(f"Reranking {len(candidates)} candidates with LLM")
        
        # 准备候选结果的格式化信息
        candidate_info = []
        for idx, candidate in enumerate(candidates):
            api_title = candidate.metadata.get('title', 'N/A')
            api_id = candidate.metadata.get('id', 'N/A')
            description = candidate.content[:500]  # 限制长度避免 prompt 过长
            candidate_info.append({
                'index': idx,
                'id': api_id,
                'title': api_title,
                'description': description
            })
        
        # 构建 LLM reranking prompt
        rerank_prompt = self.rerank_simple_prompt.format(
            query=query,
            candidate_info=candidate_info
        )
        
        try:
            # 调用 LLM 进行重排序
            response = await self.llm.ainvoke(rerank_prompt)
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
                f"LLM reranking complete. Reordered {len(reranked_candidates)} candidates. "
                f"Reranked results: {[c.metadata.get('title', 'N/A') for c in reranked_candidates]}"
            )
            
            return reranked_candidates
            
        except Exception as e:
            self.logger.error(f"Error during LLM reranking: {e}", exc_info=True)
            self.logger.warning("Falling back to original order")
            # 异常情况下返回原始顺序
            return candidates
    
    def clean(self, faiss_index_path: str = None):
        """
        清理已有的 description 文件和 FAISS 索引
        
        Args:
            faiss_index_path: FAISS 索引目录路径，如果为 None 则不清理索引
        """
        # 删除 description 文件
        if os.path.exists(self.description_path):
            self.logger.info(f"Deleting description file: {self.description_path}")
            os.remove(self.description_path)
        else:
            self.logger.info(f"Description file not found: {self.description_path}")
        
        # 删除 FAISS 索引目录
        if faiss_index_path is not None:
            if os.path.exists(faiss_index_path):
                self.logger.info(f"Deleting FAISS index directory: {faiss_index_path}")
                shutil.rmtree(faiss_index_path)
            else:
                self.logger.info(f"FAISS index directory not found: {faiss_index_path}")
        
        # 清空内存中的向量存储
        if self.vector_store is not None:
            self.logger.info("Clearing in-memory vector store")
            self.vector_store = None
        
        self.logger.info("Cleanup completed")


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