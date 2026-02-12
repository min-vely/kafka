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
    from langchain.text_splitter import CharacterTextSplitter  # 구버전
except Exception:
    from langchain_text_splitters import CharacterTextSplitter  # 최신 분리 패키지

from agent.prompts import QUERY_REWRITE_PROMPT, RERANK_PROMPT


# -----------------------------
# 1) Vectorstore / Query Rewrite
# -----------------------------

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

def build_vectorstore(text: str) -> FAISS:
    """기사 원문을 청크로 쪼개 임베딩한 뒤, FAISS 벡터스토어를 생성합니다."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=250,
        chunk_overlap=60,
        separators=["\n\n", "\n", ". ", "? ", "! ", " "],
    )
    chunks = splitter.split_text(text or "")

    embeddings = UpstageEmbeddings(
        model="solar-embedding-1-large",
        api_key=os.environ["UPSTAGE_API_KEY"],
    )
    return FAISS.from_texts(chunks, embeddings)




def rewrite_query(llm: ChatUpstage, article_text: str) -> str:
    """기사 일부를 바탕으로 검색 최적화 쿼리를 1문장으로 재작성합니다."""
    snippet = (article_text or "")[:1800]
    prompt = QUERY_REWRITE_PROMPT.strip() + "\n\n" + snippet

    resp = llm.invoke(prompt)

    content = ""
    try:
        content = (resp.content or "").strip()
    except Exception:
        content = str(resp).strip()

    # 따옴표/잡음 제거
    content = content.strip().strip('"').strip("'").strip()

    # 빈 값 fallback
    if not content:
        content = "기사 핵심(수치/비교/기능/조건/발언)을 요약하기 위한 근거 문장 검색 쿼리"

    # ✅ 여기서 반드시 정리
    content = _clean_llm_query_output(content)

    return content



def _to_relevance(score: float) -> float:
    """FAISS score를 0~1 relevance로 변환."""
    try:
        return 1.0 / (1.0 + float(score))
    except Exception:
        return 0.0


# ✅ rewrite_query 출력에서 메타 텍스트/따옴표/마크다운 제거
def _clean_llm_query_output(s: str, max_len: int = 160) -> str:
    s = (s or "").strip()

    # 1) 라벨 제거
    s = re.sub(r"^\*+\s*쿼리\s*\*+\s*:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*query\s*:\s*", "", s, flags=re.IGNORECASE)

    # 2) 큰 블록이 시작되는 지점에서 '잘라내기'
    #    (아래 키워드가 나오면 그 이전까지만 남김)
    cut_markers = [
        "\n",                # 여러 줄이면 첫 줄만
        "citations:",        # citations 블록 제거
        "**최종",            # **최종 출력**, **최종 답변** 제거
        "최종 출력",         # 한글 최종 출력
        "시스템 요구사항",    # 시스템 요구사항 준수... 제거
        "(※",                # 주석/설명 제거
    ]
    for m in cut_markers:
        if m in s:
            s = s.split(m, 1)[0].strip()

    # 3) 따옴표로 시작하는 '두 번째 덩어리'가 붙는 경우(너 로그 케이스) 잘라내기
    if ' "' in s:
        s = s.split(' "', 1)[0].strip()
    if '"' in s and s.count('"') >= 1:
        # 중간에 따옴표가 나오면 뒤는 버리기 (LLM이 "..." 블록을 붙일 때)
        s = s.split('"', 1)[0].strip()

    # 4) 메타 문구 제거 (남아 있으면)
    s = re.sub(r"\*\*최종\s*답변\*\*|최종\s*답변|실제\s*답변", "", s).strip()

    # 5) 공백/따옴표 정리
    s = s.strip().strip('"').strip("'")
    s = re.sub(r"\s+", " ", s).strip()

    # 6) 길이 제한
    if len(s) > max_len:
        s = s[:max_len].rstrip(" ,.;")

    return s



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


def rerank_with_llm(llm: ChatUpstage, query: str, candidates: List[Dict[str, Any]], take: int = 4) -> List[Dict[str, Any]]:
    """
    LLM으로 후보를 재정렬합니다.
    RERANK_PROMPT는 ["C3","C1",...] 같은 id 리스트를 반환하도록 설계되어야 함.
    실패 시 relevance 순으로 fallback.
    """
    payload = {
        "query": query,
        "candidates": [{"id": c["id"], "text": (c["text"][:400] if c.get("text") else "")} for c in candidates],
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
        # fallback: relevance 높은 순
        picked_ids = [c["id"] for c in sorted(candidates, key=lambda x: x["relevance"], reverse=True)[:take]]

    id2 = {c["id"]: c for c in candidates}
    ranked = [id2[i] for i in picked_ids if i in id2]
    return ranked[:take]


def pack_context(ranked: List[Dict[str, Any]], max_chars: int = 2800) -> Tuple[str, List[Dict[str, Any]]]:
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


# -----------------------------
# 3) Public: retrieve_context()
# -----------------------------
def retrieve_context(
    llm: ChatUpstage,
    article_text: str,
    top_k: int = 8,
    rerank_top: int = 4,
    relevance_threshold: float = 0.20,
    max_context_chars: int = 2800,
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """
    기사 → (FAISS) → 쿼리 재작성 → Retriever 검색 → pack → 반환
    반환: (query, context, citations)
    """
    vs = build_vectorstore(article_text)
    query = rewrite_query(llm, article_text)

    # 디버그 (공백/줄바꿈 포함 확인)

    retriever = KafkaMiniRetriever(
        vectorstore=vs,
        llm=llm,
        top_k=top_k,
        relevance_threshold=relevance_threshold,
        rerank_top=rerank_top,
    )

    try:
        docs = retriever.invoke(query)
    except Exception:
        docs = retriever.get_relevant_documents(query)

    ranked = [
        {
            "id": (d.metadata.get("cid") or "C?"),
            "text": d.page_content,
            "score": float(d.metadata.get("score", 0.0)),
            "relevance": float(d.metadata.get("relevance", 0.0)),
        }
        for d in (docs or [])
    ]

    if not ranked:
        return query, "", []

    context, citations = pack_context(ranked, max_chars=max_context_chars)
    return query, context, citations



# -----------------------------
# 4) Public: verify_summary_with_rag()
#    (nodes.py가 기대하는 반환 형태로 맞춤)
# -----------------------------
def _split_sentences_ko(text: str) -> List[str]:
    """
    러프 문장 분리. (너무 완벽할 필요 없음: 검증/근거부착용)
    """
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[\.\?\!。！？])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def verify_summary_with_rag(
    llm: ChatUpstage,
    article_text: str,
    summary_draft: str,
    per_sentence_k: int = 3,
    top_k: int = 8,
    rerank_top: int = 4,
    relevance_threshold: float = 0.20,
    max_context_chars: int = 2800,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    요약 검증(RAG):
    - 요약을 문장 단위로 쪼갬
    - 각 문장을 쿼리로 FAISS에서 근거 청크 검색
    - 근거가 있는 문장은 [C#]를 붙여 verified_summary 생성
    - 전체 context/citations/used_citations/unsupported_sentences 반환

    nodes.py가 기대하는 키:
    - verified_summary
    - context
    - citations
    - used_citations
    - unsupported_sentences
    """
    vs = build_vectorstore(article_text)
    # 관측/디버깅용: 기사 전체 기반 1문장 검색 쿼리(verify 루프에서 직접 사용하진 않음)
    global_query = rewrite_query(llm, article_text)


    # 🔧 수정 사항/주석 블록 제거 (최종 요약만 검증)
    summary_draft = (summary_draft or "").split("※ 수정 사항:")[0].strip()
    #

    sentences = _split_sentences_ko(summary_draft)
    if not sentences:
        return {
            "query": global_query,
            "verified_summary": "",
            "context": "",
            "citations": [],
            "used_citations": [],
            "unsupported_sentences": [],
        }

    # 전역 근거 풀 (텍스트 중복 방지, C# 재사용)
    cite_text_to_id: Dict[str, str] = {}
    citations: List[Dict[str, Any]] = []
    used_citations: List[str] = []
    unsupported_sentences: List[str] = []

    def _get_or_make_cid(text: str) -> str:
        t = text.strip()
        if t in cite_text_to_id:
            return cite_text_to_id[t]
        cid = f"C{len(citations) + 1}"
        cite_text_to_id[t] = cid
        citations.append({"id": cid, "text": t})
        return cid

    # 문장별 근거 찾기
    verified_lines: List[str] = []
    for sent in sentences:
        # 1) 후보 검색
        cands = retrieve_candidates(vs, query=sent, k=max(top_k, per_sentence_k))
        filtered = [c for c in cands if c["relevance"] >= relevance_threshold]

        if not filtered:
            unsupported_sentences.append(sent)
            verified_lines.append(sent)
            continue

        # 2) rerank (가능하면) → per_sentence_k만큼 선택
        try:
            ranked = rerank_with_llm(llm, query=sent, candidates=filtered, take=max(per_sentence_k, 1))
        except Exception:
            ranked = sorted(filtered, key=lambda x: x["relevance"], reverse=True)[: max(per_sentence_k, 1)]

        # 3) citations 등록 + 문장에 부착
        #    - 중복 chunk로 쏠림을 줄이기 위해 '서로 다른 텍스트'를 우선적으로 채택
        #    - per_sentence_k만큼 못 채우면 threshold를 낮춰(완화) 추가 채택
        cids: List[str] = []

        def _add_unique_from(rows: List[Dict[str, Any]], limit: int, relax_factor: float = 1.0):
            nonlocal cids
            if not rows:
                return
            min_rel = relevance_threshold * relax_factor
            for r in rows:
                if len(cids) >= limit:
                    break
                if float(r.get("relevance", 0.0)) < min_rel:
                    continue
                t = (r.get("text") or "").strip()
                if not t:
                    continue
                cid = _get_or_make_cid(t)
                # 같은 citation id가 반복 부착되는 건 허용하되, 한 문장 내에서는 중복 제거
                if cid not in cids:
                    cids.append(cid)

        # 1차: rerank 결과에서 우선 채택
        _add_unique_from(ranked, per_sentence_k, relax_factor=1.0)

        # 2차: 여전히 부족하면 (rerank 전에) filtered 후보에서 다양성 보충 (threshold 완화)
        if len(cids) < max(1, per_sentence_k):
            # relevance 내림차순
            backup = sorted(filtered, key=lambda x: x["relevance"], reverse=True)
            _add_unique_from(backup, per_sentence_k, relax_factor=0.6)

        if not cids:
            unsupported_sentences.append(sent)
            verified_lines.append(sent)
            continue

        # used_citations 누적
        for cid in cids:
            if cid not in used_citations:
                used_citations.append(cid)

        # 문장 뒤에 [C#] 부착
        verified_lines.append(sent + " " + " ".join([f"[{cid}]" for cid in cids]))

    # 전체 context 만들기 (max_context_chars 제한)
    context_blocks: List[str] = []
    total = 0
    for c in citations:
        block = f"[{c['id']}] {c['text']}"
        if total + len(block) > max_context_chars:
            break
        context_blocks.append(block)
        total += len(block)

    context = "\n\n".join(context_blocks)
    verified_summary = "\n".join(verified_lines).strip()


    return {
        "query": global_query,
        "verified_summary": verified_summary,
        "context": context,
        "citations": citations,
        "used_citations": used_citations,
        "unsupported_sentences": unsupported_sentences,
    }
