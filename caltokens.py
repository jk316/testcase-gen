import tiktoken

def count_tokens(text, model="gpt-4"):
    """
    根据指定模型计算文本的 token 数量
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("警告：未找到模型，使用默认 cl100k_base")
        encoding = tiktoken.get_encoding("cl100k_base")
        
    num_tokens = len(encoding.encode(text))
    return num_tokens

# 测试
my_text = '''
'''

print(f"Token 数量: {count_tokens(my_text)}")