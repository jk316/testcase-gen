1. API → LLM
   生成：
   - 高层业务描述（embedding 用）
   - 结构化摘要（method/path/输入输出，用于精排）  #TODO

2. Intent → embedding
   FAISS recall top-50 

或许删掉
3. Cross-encoder
   输入：intent vs「结构化摘要」 #TODO
   输出 score 10  

4. 候选合并
   cross-encoder top-10
 + FAISS top-5（兜底）  #TODO

5. LLM rerank
   以“是否能完成测试意图”为判断标准
   输出 top-3 API
API
告诉它上一轮这些api打了多少分,
生成一轮即可，正确性靠代码执行判断