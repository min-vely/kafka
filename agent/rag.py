import os
import json
from typing import List, Dict, Tuple

from langchain_upstage import UpstageEmbeddings, ChatUpstage
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

# ✅ LangChain 버전 차이(패키지/경로) 호환 처리
try:
    # 구버전/일부 환경
    from langchain.text_splitter import CharacterTextSplitter
except Exception:
    # 최신 환경(분리 패키지)
    from langchain_text_splitters import CharacterTextSplitter

from agent.prompts import QUERY_REWRITE_PROMPT, RERANK_PROMPT


def build_vectorstore(text: str) -> FAISS:
    """기사 원문을 청크로 쪼개 임베딩한 뒤, FAISS 벡터스토어(=벡터DB)를 생성합니다.

    NOTE: 현재 MVP에서는 '기사 1편'이 곧 지식베이스이며, 실행마다 벡터스토어를 새로 만듭니다.
    """
    splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text(text)

    embeddings = UpstageEmbeddings(
        model="solar-embedding-1-large",
        api_key=os.environ["UPSTAGE_API_KEY"],
    )
    return FAISS.from_texts(chunks, embeddings)


def rewrite_query(llm: ChatUpstage, article_text: str) -> str:
    """기사 일부를 바탕으로 검색 최적화 쿼리를 1문장으로 재작성합니다."""
    snippet = article_text[:1800]
    resp = llm.invoke(QUERY_REWRITE_PROMPT + "\n\n" + snippet)
    return (resp.content or "").strip()


def _to_relevance(score: float) -> float:
    """FAISS 거리/유사도 score를 0~1 범위의 relevance로 변환합니다."""
    try:
        return 1.0 / (1.0 + float(score))
    except Exception:
        return 0.0


def retrieve_candidates(vs: FAISS, query: str, k: int = 8) -> List[Dict]:
    """(Retriever 내부용) score를 포함한 후보를 수집합니다."""
    pairs = vs.similarity_search_with_score(query, k=k)
    cands: List[Dict] = []
    for idx, (doc, score) in enumerate(pairs, start=1):
        cid = f"C{idx}"
        cands.append(
            {
                "id": cid,
                "text": doc.page_content,
                "score": float(score),
                "relevance": _to_relevance(score),
            }
        )
    return cands


def rerank_with_llm(llm: ChatUpstage, query: str, candidates: List[Dict], top_n: int = 4) -> List[Dict]:
    """LLM으로 후보를 재정렬하고, 선택된 순서대로 candidates를 반환합니다."""
    payload = {
        "query": query,
        "candidates": [{"id": c["id"], "text": c["text"][:400]} for c in candidates],
    }
    resp = llm.invoke(RERANK_PROMPT + "\n\n" + json.dumps(payload, ensure_ascii=False))

    try:
        picked = json.loads(resp.content)
        picked_ids = [x for x in picked if isinstance(x, str)] if isinstance(picked, list) else []
    except Exception:
        picked_ids = []

    # fallback: relevance 높은 순으로 top_n
    if not picked_ids:
        picked_ids = [c["id"] for c in sorted(candidates, key=lambda x: x["relevance"], reverse=True)[:top_n]]

    id2 = {c["id"]: c for c in candidates}
    ranked = [id2[i] for i in picked_ids if i in id2]
    return ranked[:top_n]


def pack_context(ranked: List[Dict], max_chars: int = 2800) -> Tuple[str, List[Dict]]:
    """선정된 근거를 [C#] 마커와 함께 프롬프트에 넣기 좋은 문자열로 합칩니다."""
    seen = set()
    packed: List[Dict] = []
    total = 0

    for c in ranked:
        t = c["text"].strip()
        if not t or t in seen:
            continue
        seen.add(t)

        piece = f"[{c['id']}] " + t
        if total + len(piece) > max_chars:
            break

        packed.append({"id": c["id"], "text": t})
        total += len(piece)

    context = "\n\n".join([f"[{p['id']}] {p['text']}" for p in packed])
    return context, packed


class KafkaMiniRetriever(BaseRetriever):
    """현재 프로젝트의 RAG 검색 로직을 LangChain Retriever 형태로 래핑한 커스텀 리트리버."""

    model_config = {"arbitrary_types_allowed": True}

    vectorstore: FAISS
    llm: ChatUpstage
    top_k: int = 8
    relevance_threshold: float = 0.20
    rerank_top: int = 4

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # 1) Vector Retrieval (score 포함)
        candidates = retrieve_candidates(self.vectorstore, query=query, k=self.top_k)

        # 2) Threshold Filtering
        filtered = [c for c in candidates if c["relevance"] >= self.relevance_threshold]
        if not filtered:
            return []

        # 3) LLM Reranking (rerank_top 개 선택)
        ranked = rerank_with_llm(self.llm, query=query, candidates=filtered, top_n=self.rerank_top)

        # 4) Document 형태로 반환 (metadata에 citation id 유지)
        docs: List[Document] = []
        for c in ranked:
            docs.append(
                Document(
                    page_content=c["text"],
                    metadata={
                        "cid": c["id"],
                        "score": c["score"],
                        "relevance": c["relevance"],
                    },
                )
            )
        return docs


def retrieve_context(
    llm: ChatUpstage,
    article_text: str,
    top_k: int = 8,
    rerank_top: int = 4,
    relevance_threshold: float = 0.20,
) -> Tuple[str, str, List[Dict]]:
    """기사 → (청크/임베딩/벡터DB) → Retriever 검색 → (pack) → (query, context, citations) 반환."""
    import re

    # 벡터DB(FAISS) 생성
    vs = build_vectorstore(article_text)

    # 검색용 쿼리 재작성
    query = rewrite_query(llm, article_text)

    # Retriever 호출
    retriever = KafkaMiniRetriever(
        vectorstore=vs,
        llm=llm,
        top_k=top_k,
        relevance_threshold=relevance_threshold,
        rerank_top=rerank_top,
    )

    # LangChain 버전 차이 대비 invoke / get_relevant_documents 호환
    try:
        docs = retriever.invoke(query)
    except Exception:
        docs = retriever.get_relevant_documents(query)

    # retriever 결과를 기존 파이프라인(dict list) 형태로 변환
    ranked: List[Dict] = []
    for d in (docs or []):
        ranked.append(
            {
                "id": (d.metadata.get("cid") or "C?"),
                "text": d.page_content,
                "score": float(d.metadata.get("score", 0.0)),
                "relevance": float(d.metadata.get("relevance", 0.0)),
            }
        )

    if not ranked:
        print("\n========== DEBUG (RAG CONTEXT) ==========")
        print("query:", query)
        print("docs_count_from_retriever: 0")
        print("ranked_ids: []")
        print("packed_citations_ids: []")
        print("num_[C#]_blocks_in_context: 0")
        print("----- CONTEXT START -----")
        print("")
        print("----- CONTEXT END -----")
        print("========== END DEBUG ==========\n")
        return "", "", []

    # Context packing
    context, citations = pack_context(ranked, max_chars=2800)
    if not context.strip():
        print("\n========== DEBUG (RAG CONTEXT) ==========")
        print("query:", query)
        print("docs_count_from_retriever:", len(docs or []))
        print("ranked_ids:", [r["id"] for r in ranked])
        print("packed_citations_ids: []")
        print("num_[C#]_blocks_in_context: 0")
        print("----- CONTEXT START -----")
        print("")
        print("----- CONTEXT END -----")
        print("========== END DEBUG ==========\n")
        return "", "", []

    # ===== DEBUG: 최종 Context / Citation 확인 =====
    print("\n========== DEBUG (RAG CONTEXT) ==========")
    print("query:", query)
    print("docs_count_from_retriever:", len(docs or []))
    print("ranked_ids:", [r["id"] for r in ranked])
    print("packed_citations_ids:", [c["id"] for c in citations])

    num_blocks = len(re.findall(r"\[C\d+\]", context))
    print("num_[C#]_blocks_in_context:", num_blocks)

    print("\n----- CONTEXT START -----")
    print(context)
    print("----- CONTEXT END -----\n")
    print("========== END DEBUG ==========\n")

    return query, context, citations
