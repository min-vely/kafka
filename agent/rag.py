import os
import json
import re
from typing import Any, Dict, List, Tuple, Optional

from langchain_upstage import UpstageEmbeddings, ChatUpstage
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

# ✅ LangChain 버전 차이(패키지/경로) 호환 처리
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

from agent.prompts import QUERY_REWRITE_PROMPT, RERANK_PROMPT


# -----------------------------
# 1) Vectorstore / Query Rewrite
# -----------------------------
def build_vectorstore(text: str) -> FAISS:
    """기사 원문을 청크로 쪼개 임베딩한 뒤, FAISS 벡터스토어를 생성합니다."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=120,
        separators=["\n\n", "\n", ". ", "? ", "! ", " "],
    )
    chunks = splitter.split_text(text or "")

    embeddings = UpstageEmbeddings(
        model="solar-embedding-1-large",
        api_key=os.environ["UPSTAGE_API_KEY"],
    )
    return FAISS.from_texts(chunks, embeddings)


def _clean_llm_query_output(s: str, max_len: int = 160) -> str:
    """rewrite_query 출력에서 메타 텍스트/따옴표/마크다운 제거"""
    s = (s or "").strip()

    s = re.sub(r"^\*+\s*쿼리\s*\*+\s*:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*query\s*:\s*", "", s, flags=re.IGNORECASE)

    cut_markers = ["\n", "citations:", "**최종", "최종 출력", "시스템 요구사항", "(※"]
    for m in cut_markers:
        if m in s:
            s = s.split(m, 1)[0].strip()

    if ' "' in s:
        s = s.split(' "', 1)[0].strip()
    if '"' in s and s.count('"') >= 1:
        s = s.split('"', 1)[0].strip()

    s = re.sub(r"\*\*최종\s*답변\*\*|최종\s*답변|실제\s*답변", "", s).strip()

    s = s.strip().strip('"').strip("'")
    s = re.sub(r"\s+", " ", s).strip()

    if len(s) > max_len:
        s = s[:max_len].rstrip(" ,.;")

    return s


def rewrite_query(llm: ChatUpstage, article_text: str) -> str:
    """기사 일부를 바탕으로 검색 최적화 쿼리를 1문장으로 재작성합니다."""
    snippet = (article_text or "")[:1800]
    prompt = QUERY_REWRITE_PROMPT.strip() + "\n\n" + snippet

    resp = llm.invoke(prompt)

    try:
        content = (resp.content or "").strip()
    except Exception:
        content = str(resp).strip()

    content = content.strip().strip('"').strip("'").strip()

    if not content:
        content = "기사 핵심(수치/비교/기능/조건/발언)을 요약하기 위한 근거 문장 검색 쿼리"

    return _clean_llm_query_output(content)


def _to_relevance(score: float) -> float:
    """FAISS score를 0~1 relevance로 변환."""
    try:
        return 1.0 / (1.0 + float(score))
    except Exception:
        return 0.0


# -----------------------------
# 2) Retriever (optional rerank)
# -----------------------------
def retrieve_candidates(vs: FAISS, query: str, k: int = 8) -> List[Dict[str, Any]]:
    pairs = vs.similarity_search_with_score(query, k=k)
    cands: List[Dict[str, Any]] = []
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


def rerank_with_llm(
    llm: ChatUpstage,
    query: str,
    candidates: List[Dict[str, Any]],
    take: int = 4,
) -> List[Dict[str, Any]]:
    """
    LLM으로 후보를 재정렬합니다.
    RERANK_PROMPT는 ["C3","C1",...] 같은 id 리스트를 반환하도록 설계되어야 함.
    실패 시 relevance 순으로 fallback.
    """
    payload = {
        "query": query,
        "candidates": [
            {"id": c["id"], "text": (c["text"][:400] if c.get("text") else "")}
            for c in candidates
        ],
    }

    resp = llm.invoke(RERANK_PROMPT + "\n\n" + json.dumps(payload, ensure_ascii=False))

    picked_ids: List[str] = []
    try:
        picked = json.loads(resp.content)
        if isinstance(picked, list):
            picked_ids = [x for x in picked if isinstance(x, str)]
    except Exception:
        picked_ids = []

    if not picked_ids:
        picked_ids = [
            c["id"]
            for c in sorted(candidates, key=lambda x: x["relevance"], reverse=True)[:take]
        ]

    id2 = {c["id"]: c for c in candidates}
    ranked = [id2[i] for i in picked_ids if i in id2]
    return ranked[:take]


def pack_context(
    ranked: List[Dict[str, Any]],
    max_chars: int = 2800,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    선정된 근거를 [C#] 마커와 함께 프롬프트에 넣기 좋은 문자열로 합칩니다.
    반환: (context_str, citations=[{"id": "C1", "text": "..."}...])
    """
    seen = set()
    packed: List[Dict[str, Any]] = []
    total = 0

    for c in ranked:
        t = (c.get("text") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)

        piece = f"[{c['id']}] {t}"
        if total + len(piece) > max_chars:
            break

        packed.append({"id": c["id"], "text": t})
        total += len(piece)

    context = "\n\n".join([f"[{p['id']}] {p['text']}" for p in packed])
    return context, packed


class KafkaMiniRetriever(BaseRetriever):
    """현재 프로젝트 RAG 검색 로직을 LangChain Retriever 형태로 래핑."""
    model_config = {"arbitrary_types_allowed": True}

    vectorstore: FAISS
    llm: ChatUpstage
    top_k: int = 8
    relevance_threshold: float = 0.20
    rerank_top: int = 4

    def _get_relevant_documents(self, query: str) -> List[Document]:
        candidates = retrieve_candidates(self.vectorstore, query=query, k=self.top_k)
        filtered = [c for c in candidates if c["relevance"] >= self.relevance_threshold]
        if not filtered:
            return []

        ranked = rerank_with_llm(self.llm, query=query, candidates=filtered, take=self.rerank_top)

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


def _strip_citation_markers(text: str) -> str:
    """[C1] 같은 마커 제거 (eval/비교용)."""
    t = (text or "")
    t = re.sub(r"\s*\[C\d+\]\s*", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _build_rag_candidate(
    llm: ChatUpstage,
    article_text: str,
    draft_summary: str,
    top_k: int,
    rerank_top: int,
    relevance_threshold: float,
    max_context_chars: int,
) -> Dict[str, Any]:
    """
    [RAG 후보 생성] 근거(context) 기반으로 요약을 '새로 작성'하고 [C#] 마커 포함.
    draft_summary는 참고만(coverage 방향)하고, 사실은 context로 제한.
    """
    vs = build_vectorstore(article_text)
    global_query = rewrite_query(llm, article_text)

    candidates = retrieve_candidates(vs, query=global_query, k=top_k)
    filtered = [c for c in candidates if c["relevance"] >= relevance_threshold]
    ranked = rerank_with_llm(llm, query=global_query, candidates=filtered, take=rerank_top) if filtered else []

    context_str, citations = pack_context(ranked, max_chars=max_context_chars)

    if not context_str:
        return {
            "query": global_query,
            "context": "",
            "citations": [],
            "rag_candidate_summary": "",
            "rag_candidate_plain": "",
        }

    rag_gen_prompt = f"""
당신은 뉴스 요약 전문가입니다. 아래 [근거 문장들]을 사용하여 기사를 요약하세요.

[필수 지침]
1. 반드시 제공된 [근거 문장들]의 내용만 사용하세요.
2. 문장 중간이나 끝에 해당 정보의 근거 ID(예: [C1])를 **반드시 포함**하세요.
3. 정보를 임의로 지어내지 마세요.
4. 요약은 3문장 정도로 핵심만 전달하세요.

[선택 지침]
- 아래 초안(draft)은 논점/범위 참고용이며, 사실은 근거에서만 뽑으세요.

[초안(draft)]
{draft_summary}

[근거 문장들]
{context_str}

최종 요약:
""".strip()

    try:
        resp = llm.invoke(rag_gen_prompt)
        rag_summary = (resp.content or "").strip()
    except Exception:
        rag_summary = ""

    return {
        "query": global_query,
        "context": context_str,
        "citations": citations,
        "rag_candidate_summary": rag_summary,
        "rag_candidate_plain": _strip_citation_markers(rag_summary),
    }


def select_best_summary_with_fallback(
    llm: ChatUpstage,
    article_text: str,
    draft_summary: str,
    max_retry: int = 2,
    max_context_chars: int = 2800,
) -> Dict[str, Any]:
    """
    - RAG 후보를 여러 파라미터로 생성하며 best candidate를 고름
    - eval_pairwise로 draft(A) vs rag_plain(B) 평가하여 winner 산출
    """
    attempts = [
        dict(top_k=8,  rerank_top=4, relevance_threshold=0.20),
        dict(top_k=12, rerank_top=6, relevance_threshold=0.12),
        dict(top_k=16, rerank_top=8, relevance_threshold=0.08),
    ]
    max_retry = max(0, min(int(max_retry), len(attempts) - 1))

    try:
        from agent.eval_pairwise import eval_rag_vs_llm
    except Exception:
        eval_rag_vs_llm = None  # type: ignore

    best: Dict[str, Any] = {
        "winner": "UNKNOWN",
        "winner_reason": "",
        "rag_attempt_used": 0,
        "pairwise_report": None,
        "rag_pack": None,
    }
    best_b = -10

    for i in range(0, max_retry + 1):
        cfg = attempts[i]
        rag_pack = _build_rag_candidate(
            llm=llm,
            article_text=article_text,
            draft_summary=draft_summary,
            top_k=int(cfg["top_k"]),
            rerank_top=int(cfg["rerank_top"]),
            relevance_threshold=float(cfg["relevance_threshold"]),
            max_context_chars=int(max_context_chars),
        )

        rag_plain = rag_pack.get("rag_candidate_plain", "")

        winner = "UNKNOWN"
        reason = ""
        report = None
        b_score = -10

        if eval_rag_vs_llm and draft_summary and rag_plain:
            report = eval_rag_vs_llm(
                llm=llm,
                article_text=article_text,
                draft_summary=draft_summary,
                rag_summary=rag_plain,
            )
            try:
                w = (((report or {}).get("overall") or {}).get("winner") or "").upper()
                if w == "A":
                    winner = "LLM"
                elif w == "B":
                    winner = "RAG"
                elif w == "TIE":
                    winner = "TIE"
                else:
                    winner = "UNKNOWN"
                reason = (((report or {}).get("overall") or {}).get("reason") or "")
            except Exception:
                winner = "UNKNOWN"

            try:
                b_score = int(((report.get("overall") or {}).get("b")) or 0)
            except Exception:
                b_score = 0

        # best 업데이트
        if b_score > best_b:
            best_b = b_score
            best = {
                "winner": winner,
                "winner_reason": reason,
                "rag_attempt_used": i,
                "pairwise_report": report,
                "rag_pack": rag_pack,
            }

        # RAG가 이긴 순간 빠른 종료 (성공 시도 우선)
        if winner == "RAG":
            break

    return best


def verify_summary_with_rag(
    llm: ChatUpstage,
    article_text: str,
    summary_draft: str,
    max_retry: int = 2,
    max_context_chars: int = 2800,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    ✅ 최종 정책(서비스 목표 반영):
    - 후보 A: LLM-only draft_summary
    - 후보 B: RAG 후보(근거 기반 새 요약) => rag_candidate_summary(+ [C#]) / rag_candidate_plain
    - pairwise winner에 따라 최종 요약(verified_summary)을 결정
      * RAG or TIE => RAG 채택(근거와 함께)
      * LLM => LLM 채택(근거/인용은 최종 출력용으로는 비움)
      * UNKNOWN => 안전하게 LLM 채택
    - 단, 튜닝/개선 루프용으로 rag_context/rag_citations는 항상 함께 반환
    """
    picked = select_best_summary_with_fallback(
        llm=llm,
        article_text=article_text,
        draft_summary=summary_draft,
        max_retry=max_retry,
        max_context_chars=max_context_chars,
    )

    rag_pack = picked.get("rag_pack") or {}
    winner = (picked.get("winner") or "UNKNOWN").upper()

    rag_candidate_summary = rag_pack.get("rag_candidate_summary", "") or ""
    rag_candidate_plain = rag_pack.get("rag_candidate_plain", "") or ""
    rag_query = rag_pack.get("query", "") or ""
    rag_context = rag_pack.get("context", "") or ""
    rag_citations = rag_pack.get("citations", []) or []

    # ✅ 최종 선택
    if winner in ["RAG", "TIE"]:
        final_source = "RAG"
        final_summary = rag_candidate_summary or summary_draft
        final_citations = rag_citations
        final_context = rag_context
        used_citations = [c.get("id") for c in rag_citations if isinstance(c, dict)]
    elif winner == "LLM":
        final_source = "LLM"
        final_summary = summary_draft or ""
        # 🔥 최종 출력은 LLM이면 citations/context 비움 (노출 리스크 차단)
        final_citations = []
        final_context = ""
        used_citations = []
    else:
        # UNKNOWN => 안전하게 LLM 채택
        final_source = "LLM"
        final_summary = summary_draft or ""
        final_citations = []
        final_context = ""
        used_citations = []

    return {
        # 후보들
        "llm_candidate_summary": summary_draft or "",
        "rag_candidate_summary": rag_candidate_summary,
        "rag_candidate_plain": rag_candidate_plain,

        # RAG 재료(튜닝/디버그/개선루프용)
        "rag_query": rag_query,
        "rag_context": rag_context,
        "rag_citations": rag_citations,

        # 최종 출력(서비스용)
        "query": rag_query,               # 로그/디버그 목적(원하면 final_source가 LLM일 때 숨겨도 됨)
        "context": final_context,
        "citations": final_citations,
        "used_citations": used_citations,
        "verified_summary": final_summary,

        # 선택 정보
        "winner": winner,
        "final_source": final_source,
        "winner_reason": picked.get("winner_reason") or "",
        "rag_attempt_used": picked.get("rag_attempt_used", 0),
        "pairwise_report": picked.get("pairwise_report"),
        "unsupported_sentences": [],  # 현재는 새로 생성이라 문장 단위 unsupported 의미 낮음
    }
