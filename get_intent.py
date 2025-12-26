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

    query = "创建测试用例"
    logger.info("Index ready, start intent search")
    results = index.search(
        intent=query,
        recall_size=50
    )

    logger.info(f"Search results: {results}")

    for res in results:
        print("API Path:",res.candidate.metadata["title"])
        print("ID", res.candidate.metadata["id"])
        print("匹配描述: ", res.candidate.content)
        print("Score: ", res.score)
        print("-----")

if __name__ == "__main__":
    main()