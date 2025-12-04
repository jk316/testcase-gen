import os
from langchain_community.chat_models import ChatTongyi
from dotenv import load_dotenv

load_dotenv()

model = ChatTongyi(model="qwen-max")

print(model.invoke("天空是什么颜色的").content)
