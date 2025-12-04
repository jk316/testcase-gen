#粗粒度测试用例生成
from utils.file_process import read_json

def gen_Coarse():
    attacks = read_json("outputs/unique_attacks.json")
    