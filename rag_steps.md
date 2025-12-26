1. OpenAPI → LLM
   生成：
   - 高层业务描述（embedding 用）
   - 结构化摘要（method/path/输入输出，用于精排）

2. Intent → embedding
   FAISS recall top-50

3. Cross-encoder
   输入：intent vs「结构化摘要」
   输出 score

4. 候选合并
   cross-encoder top-10
 + FAISS top-5（兜底）

5. LLM rerank
   以“是否能完成测试意图”为判断标准
   输出 top-3 API
