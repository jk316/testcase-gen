from langchain_core.prompts import PromptTemplate
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import FAISS
from api_intent_index import ApiIntentIndex
import json
from utils.logger import get_logger
import os
from dotenv import load_dotenv
from utils.file_process import load_api_jsonl, load_jinja_template

load_dotenv()

def main():
    logger = get_logger("Main")
    logger.info("Loading API jsonl...")
    apis = load_api_jsonl("inputs/xrt_openapi.jsonl")
    logger.info(f"Loaded {len(apis)} APIs")

    INDEX_DIR = "indexes/api_intent_faiss"

    template_str = load_jinja_template("prompts/intent.jinja")

    llm = ChatTongyi(
        model="qwen-max"
    )
    
    embeddings = DashScopeEmbeddings(model="text-embedding-v1")

    logger.info("Initializing ApiIntentIndex...")
    index = ApiIntentIndex(
        llm=llm,
        embedding=embeddings,
        prompt_template=template_str
    )
    logger.info("Checking FAISS index...")
    if os.path.exists(INDEX_DIR):
        print("Loading FAISS index from disk...")
        index.load(INDEX_DIR)
    else:
        print("Building FAISS index...")
        index.build_from_apis(apis)
        index.save(INDEX_DIR)

    query = "创建udp flood攻击测试用例"
    logger.info("Index ready, start intent search")
    results = index.search(
        intent=query,
        recall_size=50
    )

    for res in results:
        print("API Path:",res.metadata["title"])
        print("ID", res.metadata["id"])
        print("匹配描述: ", res.page_content)
        print("-----")

if __name__ == "__main__":
    main()