import json
from docx import Document

def split_by_headings(doc_path):
    doc = Document(doc_path)
    # print(doc.paragraphs)

    # 用于存储结构：[{h1:..., children:[{h2... children:[...]}]}]
    result = []
    current_chap_title = None
    current_h1 = None
    current_h2 = None
    current_h3 = None
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style = para.style.name
        # line = f"{style} === {text}\n"
        # f.write(line)
        print(style, "====", text)

        if style == "章标题":
            current_chap_title = {"章节标题": text, "content": [], "children": []}
            result.append(current_chap_title)
            current_h1 = None
            current_h2 = None
            current_h3 = None
        # 识别一级标题
        elif style == "一级条标题":
            if current_chap_title is None:
                continue
            current_h1 = {"一级标题": text, "content": [], "children": []}
            current_chap_title["children"].append(current_h1)
            current_h2 = None
            current_h3 = None

        # 二级标题
        elif style == "二级条标题":
            if current_h1 is None:
                continue
            current_h2 = {"二级标题": text, "content": [], "children": []}
            current_h1["children"].append(current_h2)
            current_h3 = None

        # 三级标题
        elif style == "三级条标题":
            if current_h2 is None:
                continue
            current_h3 = {"三级标题": text, "content": []}
            current_h2["children"].append(current_h3)

        # 普通正文
        else:
            if current_h3:
                current_h3["content"].append(text)
            elif current_h2:
                current_h2["content"].append(text)
            elif current_h1:
                current_h1["content"].append(text)
            elif current_chap_title:
                current_chap_title["content"].append(text)

    return result


# 测试
if __name__ == "__main__":
    structure = split_by_headings("inputs/requirement.docx")
    with open("outputs/split_requirement.json", "w", encoding="utf-8") as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)