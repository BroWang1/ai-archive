from kalm_t5gemma2_vllm_plugin import KaLMVLLMReranker


query = "What is the capital of China?"
documents = [
    "The capital of China is Beijing.",
    "Gravity attracts bodies toward one another.",
]

with KaLMVLLMReranker(
    "KaLM-Embedding/KaLM-Reranker-V1-Nano",
    encoder_chunk_size=4,
    query_max_length=512,
    document_max_length=1024,
) as reranker:
    print(reranker.predict([(query, document) for document in documents]))
    print(reranker.rank(query, documents))
