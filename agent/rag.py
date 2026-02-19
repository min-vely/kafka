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
    cut_markers = [
        "\n",
        "citations:",
        "**최종",
        "최종 출력",
        "시스템 요구사항",
        "(※",
    ]
    for m in cut_markers:
        if m in s:
            s = s.split(m, 1)[0].strip()

    # 3) 따옴표로 시작하는 '두 번째 덩어리'가 붙는 경우 잘라내기
    if ' "' in s:
        s = s.split(' "', 1)[0].strip()
    if '"' in s and s.count('"') >= 1:
        s = s.split('"', 1)[0].strip()

    # 4) 메타 문구 제거
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


def rerank_with_llm(
    llm: ChatUpstage, query: str, candidates: List[Dict[str, Any]], take: int = 4
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
    ranked: List[Dict[str, Any]], max_chars: int = 2800
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

        ranked = rerank_with_llm(
            self.llm, query=query, candidates=filtered, take=self.rerank_top
        )

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
# (NEW) 3.5) A/B helpers
# -----------------------------
def _make_rag_summary(llm: ChatUpstage, context: str) -> str:
    """
    CONTEXT만을 근거로 간결 요약을 생성합니다.
    (규칙: 컨텍스트 외 정보 추가 금지)
    """
    context = (context or "").strip()
    if not context:
        return ""

    prompt = (
        "당신은 주어진 CONTEXT만을 근거로 요약하는 시스템입니다.\n"
        "규칙:\n"
        "- CONTEXT에 없는 내용은 절대 추가하지 마세요.\n"
        "- 3문장으로 간결하게 요약하세요.\n"
        "- 과장/추측/일반론 금지.\n\n"
        f"CONTEXT:\n{context}\n\n"
        "출력: 3문장 요약"
    )

    resp = llm.invoke(prompt)
    try:
        return (resp.content or "").strip()
    except Exception:
        return str(resp).strip()
    
def _clean_summary_meta(text: str) -> str:
    """
    요약 본문만 남기고 LLM이 붙인 메타 문구 제거.
    - 앞: "수정된 3문장 요약:", "3문장 요약:" 등
    - 뒤: "(※ 최종 요약은 ...)", "(※ 참고: ...)" 등
    """
    s = (text or "").strip()
    # 앞쪽 라벨 제거 (수정된 3문장 요약: / 3문장 요약: 등)
    s = re.sub(r"^(수정된\s*)?3\s*문장\s*요약\s*:?\s*", "", s, flags=re.IGNORECASE)
    # ※ 주석 블록 제거 (괄호 안 ※ ... ) 전부
    s = re.sub(r"\s*\(\s*※[^)]*\)", "", s)
    s = re.sub(r"\s*※\s*참고:[^\n]*(?:\n|$)", "", s)
    return s.strip()


def _strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"```json\s*", "", s, flags=re.IGNORECASE)
    s = s.replace("```", "")
    return s.strip()

def _extract_first_json_obj(raw: str) -> Optional[Dict[str, Any]]:
    """
    LLM 응답에서 '첫 번째 JSON 객체'를 안정적으로 추출합니다.
    (중괄호가 여러 번 등장하거나, 앞/뒤로 잡텍스트가 붙어도 깨지지 않게)
    """
    if not raw:
        return None
    s = _strip_code_fences(raw)

    # 가장 앞쪽의 '{'부터 시작해서 밸런스 맞는 첫 객체를 추출
    start = s.find("{")
    if start < 0:
        return None

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = s[start : i + 1].strip()
                try:
                    obj = json.loads(candidate)
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
    return None







def _judge_pick_best(
    llm: ChatUpstage, llm_summary: str, rag_summary: str, context: str
) -> Dict[str, Any]:
    """
    LLM 요약 vs RAG 요약 중 더 나은 것을 선택합니다.
    우선순위: 근거일치/사실성 > 핵심 커버리지 > 간결성
    """
    llm_summary = (llm_summary or "").strip()
    rag_summary = (rag_summary or "").strip()
    context = (context or "").strip()

    if llm_summary and not rag_summary:
        return {"winner": "llm", "reason": "rag_summary_empty"}
    if rag_summary and not llm_summary:
        return {"winner": "rag", "reason": "llm_summary_empty"}
    if not llm_summary and not rag_summary:
        return {"winner": "llm", "reason": "both_empty"}

    prompt = (
        "너는 요약 심사위원이다. CONTEXT만을 기준으로 두 요약을 평가해 더 좋은 것을 고른다.\n"
        "평가 기준(중요도 순):\n"
        "1) 사실성/근거일치: CONTEXT에 없는 내용을 말하면 큰 감점\n"
        "2) 핵심 커버리지: 중요한 정보가 빠지면 감점\n"
        "3) 간결성: 불필요한 말이 많으면 감점\n\n"
        "반드시 JSON으로만 답하라.\n"
        '형식: {"winner":"A"|"B","scoreA":0-10,"scoreB":0-10,"reason":"짧게"}\n\n'
        f"CONTEXT:\n{context}\n\n"
        f"A (LLM_SUMMARY):\n{llm_summary}\n\n"
        f"B (RAG_SUMMARY):\n{rag_summary}\n"
    )

    resp = llm.invoke(prompt)

    raw = ""
    try:
        raw = (resp.content or "").strip()
    except Exception:
        raw = str(resp).strip()

    data = _extract_first_json_obj(raw)

    def _valid(d: Dict[str, Any]) -> bool:
        # 점수 누락은 허용(=None), winner만 확실하면 파싱 성공으로 간주
        return isinstance(d, dict) and d.get("winner") in ("A", "B")

    if not data or not _valid(data):
        # 1회 재시도: 더 짧고 강한 프롬프트
        retry_prompt = (
            "JSON 한 줄만 출력해라. 다른 텍스트/마크다운/코드펜스 절대 금지.\n"
            '키는 정확히 winner, scoreA, scoreB, reason.\n'
            '형식: {"winner":"A"|"B","scoreA":0-10,"scoreB":0-10,"reason":"짧게"}\n\n'
            f"CONTEXT:\n{context}\n\n"
            f"A:\n{llm_summary}\n\n"
            f"B:\n{rag_summary}\n"
        )
        resp2 = llm.invoke(retry_prompt)
        try:
            raw2 = (resp2.content or "").strip()
        except Exception:
            raw2 = str(resp2).strip()

        data = _extract_first_json_obj(raw2)

        if not data or not _valid(data):
            # ✅ 원인 고정용 로그: 다음에 보면 100% 잡힘
            print(f"[RAG-A/B] judge_parse_failed_raw_head={_strip_code_fences(raw)[:300]!r}")
            return {"winner": "rag", "reason": "judge_parse_failed"}

    winner = data.get("winner")
    if winner == "A":
        return {"winner": "llm", "scoreA": data.get("scoreA"), "scoreB": data.get("scoreB"), "reason": data.get("reason", "")}
    else:
        return {"winner": "rag", "scoreA": data.get("scoreA"), "scoreB": data.get("scoreB"), "reason": data.get("reason", "")}



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
    요약 검증(RAG) + (NEW) LLM요약 vs RAG요약 A/B 선택:
    - LLM 요약(summary_draft) 후보와, CONTEXT 기반 RAG 요약 후보를 각각 생성
    - 심판 LLM이 더 좋은 후보를 선택
    - 선택된 요약을 문장 단위로 쪼개 각 문장별 근거를 찾아 [C#] 부착
    - 반환: verified_summary/context/citations/used_citations/unsupported_sentences (+디버그 키)
    """
    vs = build_vectorstore(article_text)
    global_query = rewrite_query(llm, article_text)

    # 🔧 수정 사항/주석 블록 제거 (최종 요약만 검증)
    summary_draft = (summary_draft or "").split("※ 수정 사항:")[0].strip()
    summary_draft = _clean_summary_meta(summary_draft)

    # -----------------------------
    # (NEW) A/B: LLM 요약 vs RAG 요약 생성 & 선택
    # -----------------------------
    llm_summary_candidate = summary_draft

    # 기사 전체 기반 context 구성 (전역 RAG 요약 생성용)
    _q, global_context, _global_citations = retrieve_context(
        llm=llm,
        article_text=article_text,
        top_k=top_k,
        rerank_top=rerank_top,
        relevance_threshold=relevance_threshold,
        max_context_chars=max_context_chars,
    )

    rag_summary_candidate = _clean_summary_meta(_make_rag_summary(llm, global_context))

    judge_ab = _judge_pick_best(
        llm=llm,
        llm_summary=llm_summary_candidate,
        rag_summary=rag_summary_candidate,
        context=global_context,
    )

    if judge_ab.get("winner") == "rag":
        summary_draft = rag_summary_candidate or llm_summary_candidate
        chosen_source = "rag"
    else:
        summary_draft = llm_summary_candidate or rag_summary_candidate
        chosen_source = "llm"

    # ✅ 디버그 로그 (A/B 선택 확인용)
    print(
        f"[RAG-A/B] chosen={chosen_source} "
        f"scoreA={judge_ab.get('scoreA')} "
        f"scoreB={judge_ab.get('scoreB')} "
        f"reason={judge_ab.get('reason')}"
    )
    

    sentences = _split_sentences_ko(summary_draft)
    if not sentences:
        return {
            "query": global_query,
            "verified_summary": "",
            "context": "",
            "citations": [],
            "used_citations": [],
            "unsupported_sentences": [],
            # (NEW)
            "llm_summary": llm_summary_candidate,
            "rag_summary": rag_summary_candidate,
            "chosen_summary_source": chosen_source,
            "judge_ab": judge_ab,
        }

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

    verified_lines: List[str] = []
    for sent in sentences:
        cands = retrieve_candidates(vs, query=sent, k=max(top_k, per_sentence_k))
        filtered = [c for c in cands if c["relevance"] >= relevance_threshold]

        if not filtered:
            unsupported_sentences.append(sent)
            verified_lines.append(sent)
            continue

        try:
            ranked = rerank_with_llm(
                llm, query=sent, candidates=filtered, take=max(per_sentence_k, 1)
            )
        except Exception:
            ranked = sorted(filtered, key=lambda x: x["relevance"], reverse=True)[
                : max(per_sentence_k, 1)
            ]

        cids: List[str] = []

        def _add_unique_from(
            rows: List[Dict[str, Any]], limit: int, relax_factor: float = 1.0
        ):
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
                if cid not in cids:
                    cids.append(cid)

        _add_unique_from(ranked, per_sentence_k, relax_factor=1.0)

        if len(cids) < max(1, per_sentence_k):
            backup = sorted(filtered, key=lambda x: x["relevance"], reverse=True)
            _add_unique_from(backup, per_sentence_k, relax_factor=0.6)

        if not cids:
            unsupported_sentences.append(sent)
            verified_lines.append(sent)
            continue

        for cid in cids:
            if cid not in used_citations:
                used_citations.append(cid)

        verified_lines.append(sent + " " + " ".join([f"[{cid}]" for cid in cids]))

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
    verified_summary = _clean_summary_meta(verified_summary)

    return {
        "query": global_query,
        "verified_summary": verified_summary,
        "context": context,
        "citations": citations,
        "used_citations": used_citations,
        "unsupported_sentences": unsupported_sentences,
        # (NEW) 관찰/디버그용 (호출자 깨지지 않음)
        "llm_summary": llm_summary_candidate,
        "rag_summary": rag_summary_candidate,
        "chosen_summary_source": chosen_source,
        "judge_ab": judge_ab,
    }
