from langchain_core.prompts import PromptTemplate
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import FAISS
from api_intent_index_new import ApiIntentIndexNew
import json
from utils.logger import get_logger
import os
from dotenv import load_dotenv
from schemas.dto import ApiItem
from utils.file_process import load_api_jsonl, load_jinja_template
import logging

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),                    # 控制台
        logging.FileHandler("logs/app.log",  mode="a", encoding="utf-8"),  # 文件
    ],
)

def main():
    logger = get_logger("Main")
    logger.info("Loading API jsonl...")
    api_jsonl = load_api_jsonl("inputs/xrt_openapi.jsonl")
    apis = [ApiItem(id=api_dict["id"], title=api_dict["title"], content=api_dict["content"]) for api_dict in api_jsonl]
    logger.info(f"Loaded {len(apis)} APIs")
    FORCE_REBUILD = False
    INDEX_DIR = "indexes/api_intent_faiss"

    template_str = load_jinja_template("prompts/intent.jinja")

    llm = ChatTongyi(
        model="qwen-max"
    )
    
    embeddings = DashScopeEmbeddings(model="text-embedding-v1")

    logger.info("Initializing ApiIntentIndex...")
    index = ApiIntentIndexNew(
        llm=llm,
        embedding=embeddings,
        prompt_template=template_str
    )
    logger.info("Checking FAISS index...")
    if os.path.exists(INDEX_DIR) and not FORCE_REBUILD:
        logger.info("Loading FAISS index from disk...")
        index.load(INDEX_DIR)
    else:
        logger.info("Building FAISS index...")
        index.build_from_apis(apis, force_rebuild=FORCE_REBUILD)
        index.save(INDEX_DIR)

    # 从 steps.txt 读取查询列表
    steps_file = "steps.txt"
    logger.info(f"Reading queries from {steps_file}")
    
    queries = []
    if os.path.exists(steps_file):
        with open(steps_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:  # 跳过空行
                    queries.append(line)
        logger.info(f"Loaded {len(queries)} queries from {steps_file}")

    
    # 遍历每一行查询
    logger.info("Index ready, start intent search")
    for idx, query in enumerate(queries, start=1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Query {idx}/{len(queries)}: {query}")
        logger.info(f"{'='*60}")
        
        results = index.search(
            intent=query,
            recall_size=50
        )

        logger.info(f"Found {len(results)} results for query: {query}")

        for res_idx, res in enumerate(results, start=1):
            print(f"\n[Query {idx}] Result {res_idx}:")
            print("API Path:", res.candidate.metadata["title"])
            print("ID:", res.candidate.metadata["id"])
            print("匹配描述:", res.candidate.content)
            print("Score:", res.score)
            print("-" * 60)

if __name__ == "__main__":
    main()