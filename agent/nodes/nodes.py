# agent/nodes/nodes.py
import os
import json
import re
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from langchain_upstage import ChatUpstage
from agent.tools.get_latest_update_analysis import get_latest_update_analysis
from agent.tools.get_article_content_tool import get_article_content_tool

from agent.prompts import (
    SAFETY_PROMPT, #extract_content 노드에서 콘텐츠 안전도 검사하는 프롬프트 추가
    SUMMARY_DRAFT_PROMPT,
    QUIZ_FROM_SUMMARY_PROMPT,
    JUDGE_PROMPT,
    IMPROVE_DRAFT_PROMPT,
    CLASSIFY_PROMPT,
    THOUGHT_QUESTION_PROMPT,
    QUIZ_JUDGE_PROMPT,
    QUIZ_IMPROVE_PROMPT,
    KNOWLEDGE_TYPE_CLASSIFY_PROMPT,
    TAVILY_QUERY_GENERATOR_PROMPT,
    UPDATE_ANALYSIS_PROMPT,
    PERSONA_DEFINITIONS,
    PERSONA_APPLY_PROMPT,
)
#input_url노드, extract_content노드 추가하면서 유틸리티 목록 수정
from agent.utils import (
    is_valid_url,
    is_youtube_url,
    extract_youtube_video_id,
    get_youtube_transcript,
    calculate_ebbinghaus_dates,
    validate_schedule_dates,
    extract_json
)
from agent.utils.cache import load_cache, save_cache
from agent.rag import verify_summary_with_rag
from agent.database import get_db

load_dotenv()

def _safe_parse_quiz(raw: str) -> Optional[Dict[str, Any]]:
    """
    LLM 응답을 안전하게:
    1) code fence 제거
    2) 첫 JSON 추출
    3) 스키마 정규화
    실패 시 None
    """

    if not raw:
        return None

    # fence 제거 + strip
    s = re.sub(r"```.*?```", "", raw, flags=re.DOTALL).strip()

    # 첫 JSON object 추출 (greedy 방지)
    match = re.search(r"\{[\s\S]*\}", s)
    if not match:
        return None

    try:
        obj = json.loads(match.group())
    except Exception:
        return None

    questions = obj.get("questions")
    if not isinstance(questions, list) or len(questions) != 5:
        return None

    normalized = []
    letters = ["A", "B", "C", "D"]

    for q in questions:
        text = q.get("text") or q.get("question")
        options = q.get("options")
        answer = q.get("answer")

        if not text or not isinstance(options, list) or len(options) != 4:
            return None

        # 옵션 A) prefix 강제
        fixed_opts = []
        for i, opt in enumerate(options):
            opt = opt.strip()
            if not opt.startswith(letters[i]):
                opt = f"{letters[i]}) {opt}"
            fixed_opts.append(opt)

        # answer 정규화
        if answer not in letters:
            for i, opt in enumerate(options):
                if answer and answer in opt:
                    answer = letters[i]
                    break
            else:
                return None

        normalized.append({
            "text": text.strip(),
            "options": fixed_opts,
            "answer": answer
        })

    return {"questions": normalized}


def _fallback_quiz(summary: str) -> Dict[str, Any]:
    text = re.sub(r"\s+", " ", (summary or "").strip())
    if not text:
        # 요약이 비어도 기본 5문항 반환 (웹 퀴즈 페이지 에러 방지)
        letters = ["A", "B", "C", "D"]
        placeholders = [
            "위 콘텐츠의 핵심 내용을 다시 한번 확인해보세요.",
            "다음 복습에서 더 나은 퀴즈가 제공됩니다.",
            "에빙하우스 망각 곡선에 따라 복습해보세요.",
            "콘텐츠를 꼼꼼히 읽어보시는 것을 권장합니다.",
            "오늘 학습 내용을 정리해보세요.",
        ]
        return {
            "questions": [
                {
                    "text": p,
                    "options": [f"{letters[j]}) 내용 확인" for j in range(4)],
                    "answer": "A"
                }
                for p in placeholders
            ]
        }

    words = re.findall(r"[가-힣A-Za-z]{3,}", text)
    words = list(dict.fromkeys(words))[:20]

    questions = []
    letters = ["A", "B", "C", "D"]

    for i in range(5):
        target = words[i] if i < len(words) else f"핵심{i+1}"
        opts = [target] + words[i+1:i+4]
        while len(opts) < 4:
            opts.append("해당 없음")

        questions.append({
            "text": f"요약문과 가장 관련 깊은 키워드는 무엇인가?",
            "options": [f"{letters[j]}) {opts[j]}" for j in range(4)],
            "answer": "A"
        })

    return {"questions": questions}


# -----------------------------
# LLM
# -----------------------------
llm = ChatUpstage(
    model=os.getenv("KAFKA_MODEL", "solar-pro2"),
    temperature=0.2,
    api_key=os.environ["UPSTAGE_API_KEY"],
)


# -----------------------------
# Nodes
# -----------------------------
def input_url_node(state):
    """1) 입력이 URL이면 검증하고, 텍스트면 그대로 통과시키는 지능형 노드"""
    # main에서 던져준 'user_input'을 가져옵니다.
    user_input = state.get("user_input", "").strip()

    # www.로 시작하면 앞에 https:// 를 붙여서 URL로 만들어줍니다.
    # 이렇게 해야 아래 1번 IF문(http 시작 체크)에 걸립니다!
    if user_input.startswith("www."):
        user_input = "https://" + user_input

    # 1. URL 형태인지 확인
    if user_input.startswith(("http://", "https://")):
        if is_valid_url(user_input):
            # 유효한 URL인 경우
            return {
                "url": user_input,
                "is_valid": True,
                "messages": "URL 확인 완료! 본문을 추출하러 갑니다."
            }
        else:
            # URL 형태인데 가짜인 경우 (진짜 에러)
            return {
                "is_valid": False,
                "messages": "유효하지 않은 URL 형식입니다. 주소를 확인해주세요."
            }

    # 2. URL이 아니고 진짜 텍스트인 경우
    elif len(user_input) > 0:
        # 일반 텍스트인 경우 (통과!)
        # input_text 칸이 비어있을 수도 있으니 여기에 채워줍니다.
        return {
            "input_text": user_input,
            "is_valid": True,
            "messages": "텍스트 입력을 확인했습니다. 추출 단계를 건너뛰고 분석합니다."
        }

    # 3. 아무것도 안 들어온 경우
    return {
        "is_valid": False,
        "messages": "입력된 내용이 없습니다."
    }

def extract_content_node(state):
    """
    2) 콘텐츠 확보 및 LLM 유해성 검증 노드

    진행 단계:
    1. 데이터 확인:
       - URL이 있으면 YouTube/아티클에서 본문 추출
       - 이미 input_text가 있으면 추출 단계 건너뜀 (직접 입력/파일 대응)
    2. 콘텐츠 검증:
       - 추출되거나 입력된 텍스트 상위 2,000자를 바탕으로 LLM Safety 검사 수행
    3. 상태 업데이트:
       - 검증 결과에 따라 is_safe 플래그 설정 및 최종 본문 저장
    """
    url = state.get("url")
    content = state.get("input_text", "").strip()

    # 1. 이미 본문이 있다면 (직접 입력 or 파일) 추출 건너뛰기
    if content and not url:
        print("이미 본문 텍스트가 존재합니다. 추출 단계를 생략합니다.")

    # 2. URL이 있는 경우에만 추출 실행
    elif url:
        try:
            if is_youtube_url(url):
                video_id = extract_youtube_video_id(url)
                content = get_youtube_transcript(video_id)
            else:
                # 🔵 [변경] 노드에서 직접 호출 대신 도구 호출(Tool-calling) 방식 사용
                llm_with_tools = llm.bind_tools([get_article_content_tool])
                print(f"🌐 [Tool-calling] Jina Reader를 사용하여 본문 추출 시도: {url}")
                
                tool_resp = llm_with_tools.invoke([
                    ("system", "당신은 웹 콘텐츠 추출 전문가입니다. 주어진 URL에서 본문을 추출하기 위해 도구를 사용하세요."),
                    ("human", f"이 URL의 내용을 추출해줘: {url}")
                ])
                
                if tool_resp.tool_calls:
                    for tool_call in tool_resp.tool_calls:
                        if tool_call["name"] == "get_article_content_tool":
                            content = get_article_content_tool.invoke(tool_call["args"])
                            print("✅ 도구 호출을 통해 본문 추출 완료.")
                            break
                
                # 도구 호출이 전혀 수행되지 않았거나 실패한 경우 처리
                if not content or content.startswith("Error:"):
                    error_msg = content.replace("Error: ", "") if content else "본문을 추출할 수 없습니다. LLM이 도구 호출을 수행하지 않았습니다."
                    return {
                        "input_text": f"Error: {error_msg}",
                        "is_valid": False,
                        "messages": "콘텐츠 추출 실패"
                    }

        except Exception as e:
            err_msg = str(e)
            return {
                "input_text": f"Error: {err_msg}",
                "is_valid": False,
                "messages": f"콘텐츠 추출 중 오류: {err_msg}"
            }

    # 3. 추출된 내용이 아예 없거나 너무 짧은 경우 (요약 불가 URL)
    content_stripped = (content or "").strip()
    if not content_stripped:
        return {"is_valid": False, "is_safe": False, "messages": "분석할 콘텐츠가 없습니다. 요약할 수 없는 URL이거나 접근이 제한된 페이지일 수 있습니다."}
    if content_stripped.startswith("Error:"):
        return {"is_valid": False, "is_safe": False, "messages": content_stripped.replace("Error: ", "")}
    min_content_len = 100
    if len(content_stripped) < min_content_len:
        return {
            "is_valid": False,
            "is_safe": False,
            "messages": f"추출된 본문이 너무 짧습니다({len(content_stripped)}자). 유효한 기사/동영상 링크인지 확인해주세요."
        }

    # 4. Safety Check (LLM활용)
    try:
        check_text = content[:2000]
        safety_llm = llm.invoke(SAFETY_PROMPT + "\n\n[CONTENT]\n" + check_text)
        safety_response = (safety_llm.content or "").strip().upper()

        if "UNSAFE" in safety_response:
            return {
                "input_text": "Error: 유해 콘텐츠 감지",
                "is_valid": False,
                "is_safe": False,
                "messages": "안전하지 않은 콘텐츠(예: 스팸, 광고)로 판단되어 중단합니다."
            }

        # 성공적으로 통과한 경우 리턴
        return {
            "input_text": content,
            "is_valid": True,
            "is_safe": True,
            "messages": "콘텐츠 추출 및 안전성 검사 완료!"
        }

    except Exception as e:
        return {"is_valid": False, "is_safe": False, "messages": f"Safety Check 에러: {str(e)}"}

def classify_content(text: str) -> str:
    """
    텍스트를 지식형/힐링형으로 분류합니다.
    classify_node 및 정확도 평가(evaluate_classify_accuracy)에서 공통 사용.
    """
    try:
        resp = llm.invoke(CLASSIFY_PROMPT + "\n\n[CONTENT]\n" + (text or "")[:2000])
        raw_output = (resp.content or "").strip()
    except Exception:
        return "지식형"
    if "지식형" in raw_output:
        return "지식형"
    if "힐링형" in raw_output:
        return "힐링형"
    return "지식형"


def classify_node(state):
    """3) 콘텐츠 성격을 분석하여 '지식형' 또는 '힐링형'으로 분류 (CoT 적용)"""
    print("\n[Node] classify_node: 콘텐츠 분류 중...")
    article = state.get("input_text", "")
    try:
        category = classify_content(article)
    except Exception as e:
        print(f"⚠️ 분류 중 오류: {e}. 기본값(지식형) 사용.")
        category = "지식형"
    state["category"] = category
    return state


def synthesize_node(state):
    """4) 기사 원문으로 요약 초안(draft_summary)만 생성 (RAG 사용 X)"""
    print("[Node] synthesize_node: 요약 초안 생성 중...")
    article = state.get("input_text", "")

    try:
        resp = llm.invoke(SUMMARY_DRAFT_PROMPT + "\n\n[ARTICLE]\n" + article)
        draft = (resp.content or "").strip()
        if not draft:
            draft = (article[:500] + "...") if len(article) > 500 else article
            print("⚠️ LLM 요약이 비어 있어 원문 발췌를 사용합니다.")
    except Exception as e:
        print(f"⚠️ 요약 생성 중 오류: {e}")
        draft = (article[:500] + "...") if len(article) > 500 else article
        draft = f"{draft}\n\n(요약 생성 중 오류 발생, 원문 발췌)"

    state["draft_summary"] = draft
    return state


def verify_node(state):
    """5) 요약 초안을 RAG로 검증(근거 문맥 구성/문장 검증 결과 저장)"""
    print("[Node] verify_node: RAG 검증 및 벡터 DB 생성 중 (시간이 소요될 수 있습니다)...")
    article = state.get("input_text", "")
    draft = state.get("draft_summary", "")

    try:
        verified = verify_summary_with_rag(
            llm=llm,
            article_text=article,
            summary_draft=draft,
            per_sentence_k=3,
            relevance_threshold=0.12,
            max_context_chars=2800
        )
    except Exception as e:
        print(f"⚠️ RAG 검증 중 오류: {e}. 초안을 그대로 사용합니다.")
        verified_summary = re.sub(r"\s+", " ", (draft or "").strip())
        state["query"] = ""
        state["context"] = ""
        state["citations"] = []
        state["unsupported_sentences"] = []
        state["summary"] = json.dumps(
            {"Summary": verified_summary, "UsedCitations": [], "Citations": []},
            ensure_ascii=False,
        )
        state["needs_improve"] = False  # 검증 실패 시 개선 루프 생략
        return state

    state["query"] = verified.get("query", "")
    state["context"] = verified.get("context", "")
    state["citations"] = verified.get("citations", [])
    state["unsupported_sentences"] = verified.get("unsupported_sentences", [])

    verified_summary = verified.get("verified_summary", "")
    verified_summary = re.sub(r"\s+", " ", verified_summary).strip()

    state["summary"] = json.dumps(
        {
            "Summary": verified_summary,
            "UsedCitations": verified.get("used_citations", []),
            "Citations": verified.get("citations", []),
        },
        ensure_ascii=False,
    )

    state["needs_improve"] = (not str(state["context"]).strip()) or (len(state["unsupported_sentences"]) > 0)
    return state


def judge_node(state):
    """6) 검증된 CONTEXT vs SUMMARY faithfulness 채점"""
    context = state.get("context", "")
    summary_json = state.get("summary", "")

    try:
        s_obj = json.loads(summary_json)
        summary_text = s_obj.get("Summary", "")
    except Exception:
        summary_text = str(summary_json)

    try:
        resp = llm.invoke(
            JUDGE_PROMPT
            + "\n\n[CONTEXT]\n"
            + str(context)
            + "\n\n[SUMMARY]\n"
            + str(summary_text)
        )
        parsed = extract_json(resp.content or "")
        if not parsed:
            parsed = {"score": 0, "needs_improve": True, "notes": "채점 JSON 추출 실패"}
    except Exception as e:
        print(f"⚠️ 채점 중 오류: {e}. needs_improve=False로 진행.")
        parsed = {"score": 7, "needs_improve": False, "notes": "채점 실패로 통과 처리"}

    score = int(parsed.get("score", 0))
    needs_improve = bool(parsed.get("needs_improve", score < 7))
    notes = parsed.get("notes", "")

    if state.get("unsupported_sentences"):
        needs_improve = True
        score = min(score, 6)
        notes += " (미지원 문장 존재)"

    print(f"\n⚖️ [요약 평가] 점수: {score}/10 | 개선 필요: {needs_improve}")
    if notes:
        print(f"   📝 피드백: {notes}")

    state["judge_score"] = score
    state["needs_improve"] = needs_improve
    return state


def improve_node(state):
    """7) CONTEXT 기반으로 draft_summary(초안) 개선. max_improve회 초과 시 마지막 요약으로 확정."""
    max_improve = int(state.get("max_improve", 3))
    count = int(state.get("improve_count", 0))

    if count >= max_improve:
        state["needs_improve"] = False
        print(f"⚠️ 요약 개선 {max_improve}회 도달. 마지막 요약으로 확정합니다.")
        return state

    context = state.get("context", "")
    draft = state.get("draft_summary", "")

    try:
        resp = llm.invoke(
            IMPROVE_DRAFT_PROMPT
            + "\n\n[CONTEXT]\n"
            + str(context)
            + "\n\n[SUMMARY_DRAFT]\n"
            + str(draft)
        )
        improved_draft = (resp.content or "").strip()
    except Exception as e:
        print(f"⚠️ 요약 개선 중 오류: {e}. 기존 초안 유지.")
        improved_draft = draft
    state["draft_summary"] = improved_draft
    state["improve_count"] = count + 1

    return state


def save_summary_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    기획서 6번: 확정된 3줄 요약본 저장 (quiz/thought 생성 전)
    judge 통과 후, augment/quiz 노드로 가기 전에 요약을 saved_summary로 확정.
    LLM 사용 없음, 상태만 업데이트.
    """
    summary = state.get("summary", "")
    state["saved_summary"] = summary
    print("[Node] save_summary: 확정된 요약 저장 완료")
    return state


def knowledge_augmentation_node(state: Dict[str, Any]):
    """
    지식형 콘텐츠에 대해 추가 정보를 보강합니다. (Tool-calling 방식)
    1. 최신 정보형 (Dynamic): get_latest_update_analysis 도구 자동 호출
    2. 고정 지식형 (Static): 개인 URL DB에서 비슷한 정보 추천
    """
    category = state.get("category", "지식형")
    
    # 힐링형은 보강 없이 통과
    if category != "지식형":
        return state
        
    summary_json = state.get("summary", "")
    try:
        s_obj = json.loads(summary_json)
        summary_text = s_obj.get("Summary", "")
    except Exception:
        summary_text = str(summary_json)
    
    # 도구가 바인딩된 LLM 생성
    llm_with_tools = llm.bind_tools([get_latest_update_analysis])
    
    # 1. 정보 유형 분석 및 도구 호출 판단
    print("🧠 콘텐츠 유형 분석 및 웹 검색 여부 판단 중...")
    resp = llm_with_tools.invoke([
        ("system", KNOWLEDGE_TYPE_CLASSIFY_PROMPT),
        ("human", f"이 요약본에 대해 최신 정보 검색이 필요할까? 필요하면 도구를 호출하고, 아니면 'Static'이라고 답해.\n\n[SUMMARY]\n{summary_text}")
    ])
    
    augmentation_info = ""
    
    # 2-1. LLM이 도구를 호출한 경우 (Dynamic)
    if resp.tool_calls:
        print(f"🔍 [Dynamic] 최신 정보 업데이트 필요: {resp.tool_calls[0]['name']} 실행 중...")
        for tool_call in resp.tool_calls:
            if tool_call["name"] == "get_latest_update_analysis":
                # 도구 실행 및 결과 획득
                result = get_latest_update_analysis.invoke(tool_call["args"])
                augmentation_info = "\n\n" + str(result)
                print("✅ 웹 검색 및 분석 완료.")
    
    # 2-2. 도구 호출이 없는 경우 (Static 등)
    else:
        print("📚 [Static] 고정 지식형 콘텐츠: 관련 콘텐츠 추천 진행...")
        try:
            db = get_db()
            recommends = db.get_similar_recommendations(category="지식형", limit=2)
            if recommends:
                info_list = []
                for rec in recommends:
                    info_list.append(f"- {rec['url']} (페르소나: {rec['persona_style']})")
                augmentation_info = "\n\n[함께 보면 좋은 콘텐츠]\n" + "\n".join(info_list)
            else:
                augmentation_info = "\n\n[함께 보면 좋은 콘텐츠]\n아직 저장된 비슷한 콘텐츠가 없습니다."
        except Exception as e:
            augmentation_info = f"\n\n(추천 정보를 가져오는 중 오류 발생: {str(e)})"
            
    state["augmentation_info"] = augmentation_info
    return state


def quiz_node(state):
    """(옵션) 최종 verified summary 기반 퀴즈 및 생각유도질문 생성"""
    category = state.get("category", "지식형")

    # -----------------------------
    # 1️⃣ Summary 추출
    # -----------------------------
    try:
        s_obj = json.loads(state.get("summary", ""))
        summary_text = s_obj.get("Summary", "")
    except Exception:
        summary_text = ""

    # 🔥 퀴즈 생성용에서는 citation 태그 제거
    summary_text = re.sub(r"\s*\[C\d+\]\s*", " ", summary_text).strip()
    
    # 초기화
    state["thought_questions"] = []
    state["quiz"] = json.dumps({"questions": []}, ensure_ascii=False)

    # 1. 지식형: 퀴즈만 생성
    if category == "지식형":
        try:
            # 1) "JSON만" 강제하는 래퍼 프롬프트 (최소 diff: 기존 prompt 위에 덧씌움)
            strict_wrapper = (
                "반드시 JSON만 출력해라. 다른 텍스트/설명/마크다운/코드펜스 절대 금지.\n"
                "스키마는 정확히 다음을 따른다:\n"
                '{"questions":[{"question":"...","options":["...","...","...","..."],"answer":"...","explanation":"..."}]}\n'
                "- questions는 3~5개\n"
                "- options는 항상 4개\n"
                "- answer는 options 중 하나의 값(문자열)\n"
            )

            resp_quiz = llm.invoke(
                strict_wrapper
                + "\n\n"
                + QUIZ_FROM_SUMMARY_PROMPT
                + "\n\n[SUMMARY]\n"
                + str(summary_text)
            )

            raw = (resp_quiz.content or "").strip()

            # 🔵 1) 새 안전 파서 사용
            quiz_obj = _safe_parse_quiz(raw)

            # 🔵 2) 실패 시 1회 재시도 (기존 로직 유지)
            if not quiz_obj:
                retry_prompt = (
                    "JSON만 출력.\n"
                    '{"questions":[{"question":"...","options":["A","B","C","D"],"answer":"A","explanation":"..."}]}\n\n'
                    + "[SUMMARY]\n" + str(summary_text)
                )
                resp2 = llm.invoke(retry_prompt)
                quiz_obj = _safe_parse_quiz(resp2.content or "")

            # 🔵 3) 그래도 실패하면 fallback (5문항 보장)
            if not quiz_obj:
                print("⚠️ 퀴즈 JSON 파싱 실패 → fallback 사용")
                quiz_obj = _fallback_quiz(summary_text)

            state["quiz"] = json.dumps(quiz_obj, ensure_ascii=False)
            state["questions"] = quiz_obj.get("questions", [])

        except Exception as e:
            print(f"⚠️ 퀴즈 생성 중 오류: {e}. fallback 퀴즈를 생성합니다.")
            quiz_obj = _fallback_quiz(summary_text)
            state["quiz"] = json.dumps(quiz_obj, ensure_ascii=False)
            state["questions"] = quiz_obj.get("questions", [])


    # 2. 힐링형: 생각 유도 질문만 생성
    else:
        try:
            resp_thought = llm.invoke(
                THOUGHT_QUESTION_PROMPT
                + f"\n\n[CATEGORY]: {category}"
                + "\n\n[SUMMARY]\n"
                + str(summary_text)
            )
            
            content = (resp_thought.content or "").strip()
            # develop에 추가된 마크다운 및 정규식 제거 로직 적용
            content = re.sub(r"```json\s*(.*?)\s*```", r"\1", content, flags=re.DOTALL)
            content = re.sub(r"```\s*(.*?)\s*```", r"\1", content, flags=re.DOTALL)
            
            match = re.search(r"(\[.*\])", content, re.DOTALL)
            if match:
                thought_questions = json.loads(match.group(1))
                state["thought_questions"] = thought_questions if isinstance(thought_questions, list) else []
            else:
                thought_questions = extract_json(content)
                if isinstance(thought_questions, list):
                    state["thought_questions"] = thought_questions
        except Exception as e:
            print(f"⚠️ 생각 유도 질문 생성 중 오류: {e}")

    return state


def quiz_judge_node(state):
    """(🆕) 생성된 퀴즈/생각유도질문 품질 평가"""
    category = state.get("category", "지식형")
    summary_raw = state.get("summary", "")
    
    label = "퀴즈 평가" if category == "지식형" else "생각 유도 질문 평가"
    
    try:
        s_obj = json.loads(summary_raw)
        summary_text = s_obj.get("Summary", summary_raw)
    except:
        summary_text = str(summary_raw)

    # 평가할 콘텐츠 준비
    if category == "지식형":
        content_to_judge = state.get("quiz", "")
    else:
        content_to_judge = json.dumps(state.get("thought_questions", []), ensure_ascii=False)

    if not content_to_judge or content_to_judge in ('{"questions": []}', '[]'):
        state["quiz_judge_score"] = 0
        state["quiz_needs_improve"] = True
        print(f"\n📊 [{label}] 점수: 0/10 | 개선 필요: True (콘텐츠 없음)")
        return state

    resp = llm.invoke(
        QUIZ_JUDGE_PROMPT
        + "\n\n[요약본]\n" + summary_text
        + "\n\n[콘텐츠]\n" + content_to_judge
    )

    parsed = extract_json(resp.content or "")
    if parsed:
        state["quiz_judge_score"] = int(parsed.get("score", 0))
        state["quiz_needs_improve"] = bool(parsed.get("needs_improve", state["quiz_judge_score"] < 7))
        state["quiz_notes"] = parsed.get("notes", "")
    else:
        state["quiz_judge_score"] = 0
        state["quiz_needs_improve"] = True
        state["quiz_notes"] = "평가 결과 JSON 추출 실패"

    print(f"\n📊 [{label}] 점수: {state['quiz_judge_score']}/10 | 개선 필요: {state['quiz_needs_improve']}")
    if state["quiz_notes"]:
        print(f"   📝 피드백: {state['quiz_notes']}")

    return state


def quiz_improve_node(state):
    """(🆕) 평가 결과를 바탕으로 퀴즈/질문 재작성"""
    max_improve = 2 # 총 3회 시도 (초기 생성 1회 + 재시도 2회)
    count = int(state.get("quiz_improve_count", 0))

    # 이미 최대 횟수에 도달했으면 개선 중단
    if count >= max_improve:
        state["quiz_needs_improve"] = False
        print(f"⚠️ 퀴즈/질문 최대 재시도 횟수({max_improve}회) 도달. 마지막 버전을 사용합니다.")
        return state

    print(f"🔄 퀴즈/질문 재작성 중... (시도 횟수: {count + 1}/{max_improve})")
    
    category = state.get("category", "지식형")
    summary_raw = state.get("summary", "")
    try:
        s_obj = json.loads(summary_raw)
        summary_text = s_obj.get("Summary", summary_raw)
    except:
        summary_text = str(summary_raw)

    if category == "지식형":
        original_content = state.get("quiz", "")
    else:
        original_content = json.dumps(state.get("thought_questions", []), ensure_ascii=False)

    prompt = QUIZ_IMPROVE_PROMPT.format(
        summary_text=summary_text,
        notes=state.get("quiz_notes", "품질 개선 필요"),
        original_content=original_content
    )

    resp = llm.invoke(prompt)
    improved_content = (resp.content or "").strip()

    # 업데이트 및 카운트 증가
    if category == "지식형":
        try:
            quiz_obj = _safe_parse_quiz(improved_content)

            if not quiz_obj:
                retry = (
                    "JSON만 출력.\n"
                    '{"questions":[{"question":"...","options":["A","B","C","D"],"answer":"A","explanation":"..."}]}\n\n'
                    + improved_content
                )
                resp2 = llm.invoke(retry)
                quiz_obj = _safe_parse_quiz(resp2.content or "")

            if not quiz_obj:
                quiz_obj = _fallback_quiz(summary_text)

            state["quiz"] = json.dumps(quiz_obj, ensure_ascii=False)
            state["questions"] = quiz_obj.get("questions", [])

        except Exception:
            quiz_obj = _fallback_quiz(summary_text)
            state["quiz"] = json.dumps(quiz_obj, ensure_ascii=False)
            state["questions"] = quiz_obj.get("questions", [])

    else:
        try:
            thought_questions = json.loads(improved_content)
            state["thought_questions"] = thought_questions if isinstance(thought_questions, list) else []
        except:
            pass

    state["quiz_improve_count"] = count + 1
    return state


# ============================================================
# 페르소나 적용 노드
# ============================================================

def persona_node(state):
    """
    확정된 요약과 퀴즈/질문에 페르소나를 입힙니다.
    
    동작:
    1. 현재 페르소나 카운터를 확인 (0-9 순환)
    2. 콘텐츠 유형에 따라 퀴즈형/문장형 페르소나 선택
    3. 페르소나 스타일을 적용한 메시지 생성
    
    이유:
    - 매번 같은 말투로 알림이 오면 사용자가 지루해져 알림을 차단할 수 있습니다.
    - 10가지 페르소나를 순차적으로 적용하여 '친구가 안부를 묻는' 느낌을 줍니다.
    """
    category = state.get("category", "지식형")
    persona_count = int(state.get("persona_count", 0))
    
    # 페르소나 선택 (0-9 순환)
    if category == "지식형":
        persona_key = f"quiz_{persona_count % 5}"
    else:
        persona_key = f"thought_{persona_count % 5}"
    
    persona_def = PERSONA_DEFINITIONS.get(persona_key, PERSONA_DEFINITIONS["quiz_0"])
    
    # 적용할 콘텐츠 준비
    try:
        s_obj = json.loads(state.get("summary", ""))
        summary_text = s_obj.get("Summary", "")
    except Exception:
        summary_text = state.get("summary", "")
    
    if category == "지식형":
        quiz_text = state.get("quiz", "")
        aug_info = state.get("augmentation_info", "")
        content_to_style = f"[요약]\n{summary_text}\n\n[퀴즈]\n{quiz_text}"
        if aug_info:
            content_to_style += f"\n\n{aug_info}"
    else:
        thought_text = "\n".join(state.get("thought_questions", []))
        content_to_style = f"[요약]\n{summary_text}\n\n[생각 유도 질문]\n{thought_text}"
    
    # 페르소나 적용
    prompt = PERSONA_APPLY_PROMPT.format(
        persona_definition=json.dumps(persona_def, ensure_ascii=False),
        content=content_to_style
    )

    try:
        resp = llm.invoke(prompt)
        styled_content = (resp.content or "").strip()
    except Exception as e:
        print(f"⚠️ 페르소나 적용 중 오류: {e}. 원본 요약 사용.")
        styled_content = content_to_style
    
    # 상태 업데이트
    state["persona_style"] = persona_def["name"]
    state["styled_content"] = styled_content
    state["persona_count"] = persona_count + 1
    
    return state


# ============================================================
# 페르소나 후 안전 검사 노드 (기획서: persona Llama Guard)
# ============================================================

def persona_safety_check_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    페르소나 적용된 styled_content에 대한 유해성 검사.
    UNSAFE 시 페르소나 스타일을 제거한 원본 콘텐츠로 대체하여 schedule로 진행.
    """
    styled_content = state.get("styled_content", "")
    if not styled_content:
        return state

    check_text = styled_content[:2000]
    try:
        safety_llm = llm.invoke(SAFETY_PROMPT + "\n\n[CONTENT]\n" + check_text)
        safety_response = (safety_llm.content or "").strip().upper()

        if "UNSAFE" in safety_response:
            print("⚠️ [persona_safety_check] 페르소나 적용 콘텐츠가 유해로 판정됨. 원본으로 대체합니다.")
            # 페르소나 미적용 원본 콘텐츠로 대체
            try:
                s_obj = json.loads(state.get("summary", ""))
                summary_text = s_obj.get("Summary", "")
            except Exception:
                summary_text = str(state.get("summary", ""))

            category = state.get("category", "지식형")
            if category == "지식형":
                quiz_text = state.get("quiz", "")
                aug_info = state.get("augmentation_info", "")
                fallback = f"[요약]\n{summary_text}\n\n[퀴즈]\n{quiz_text}"
                if aug_info:
                    fallback += f"\n\n{aug_info}"
            else:
                thought_text = "\n".join(state.get("thought_questions", []))
                fallback = f"[요약]\n{summary_text}\n\n[생각 유도 질문]\n{thought_text}"

            state["styled_content"] = fallback
            state["persona_style"] = "(안전 검사 통과용 기본형)"
        else:
            print("✅ [persona_safety_check] 페르소나 콘텐츠 안전 검사 통과")

    except Exception as e:
        print(f"⚠️ [persona_safety_check] 검사 중 오류: {e}. 원본 유지.")

    return state


# ============================================================
# 에빙하우스 스케줄링 노드
# ============================================================

def schedule_node(state):
    """
    에빙하우스 망각 곡선에 따라 복습 알림 날짜를 계산하고 팝업 알림을 발송합니다.
    
    동작:
    1. 오늘 날짜를 기준으로 D+1, D+4, D+7, D+11 계산
    2. 계산된 날짜를 상태에 저장
    3. 데이터베이스에 스케줄 영구 저장
    4. 크로스 플랫폼 팝업 알림 발송 (macOS + Windows)
    
    이유: 
    - 에빙하우스 망각 곡선 이론:
      학습 직후 망각이 급격히 일어나지만,
      적절한 시점(1일, 4일, 7일, 11일)에 복습하면
      정보가 장기 기억으로 전환됩니다.
    - 발송 시간: 오전 8시 출근길 (인지 부하가 적은 시간)
    - 에빙하우스 겹침 시 하루 최대 4회, 퀴즈 오답 시 +1 (최대 5회)
    - DB 저장: 프로그램 재시작 후에도 스케줄 유지
    """
    schedule_dates = calculate_ebbinghaus_dates()
    is_valid, validated_dates, err_msg = validate_schedule_dates(schedule_dates)
    if not is_valid:
        print(f"⚠️ [schedule] 날짜 검증 실패: {err_msg}. 재계산 후 진행합니다.")
        schedule_dates = calculate_ebbinghaus_dates()
        is_valid, validated_dates, _ = validate_schedule_dates(schedule_dates)
        if not is_valid:
            print(f"❌ [schedule] 날짜 검증 재실패. 스케줄 저장을 건너뜁니다.")
            return state
    schedule_dates = validated_dates
    state["schedule_dates"] = schedule_dates

    print(f"\n📅 에빙하우스 알림 예약 완료:")
    for i, date in enumerate(schedule_dates, 1):
        print(f"  {i}차 알림: {date} 오전 8시")
    
    # 🆕 데이터베이스에 스케줄 저장
    schedule_id = None  # 초기화 (DB 저장 실패 시를 대비)
    try:
        from agent.database import get_db
        
        db = get_db()
        
        # URL 추출 (input_text 또는 별도 url 필드)
        url = state.get("url", "") or state.get("input_text", "")
        
        # 요약 추출 (summary는 JSON 문자열일 수 있음)
        summary_raw = state.get("summary", "")
        try:
            # JSON 형태면 파싱
            summary_obj = json.loads(summary_raw)
            summary_text = summary_obj.get("Summary", str(summary_obj))
        except:
            summary_text = str(summary_raw)
        
        # 퀴즈 문제 추출 (questions는 리스트 형태)
        questions = state.get("questions", [])
        
        schedule_id = db.save_schedule(
            user_id="default_user",  # 향후 실제 사용자 ID로 대체
            schedule_dates=schedule_dates,
            styled_content=state.get("styled_content", ""),
            persona_style=state.get("persona_style", ""),
            persona_count=state.get("persona_count", 0),
            url=url,
            summary=summary_text,
            category=state.get("category", "지식형"),
            questions=questions  # ✅ 퀴즈 문제 DB에 저장
        )
        state["schedule_id"] = schedule_id  # 큐 처리 시 활용
        print(f"💾 데이터베이스 저장 완료 (Schedule ID: {schedule_id})")
        print(f"   - URL: {url[:50] if url else '(텍스트 입력)'}...")
        print(f"   - 요약: {summary_text[:50] if summary_text else '(없음)'}...")
        print(f"   - 퀴즈: {len(questions)}개 문제 저장됨" if questions else "   - 퀴즈: (없음)")
    except Exception as e:
        print(f"\n⚠️  DB 저장 중 오류: {e}")
        print("   (알림은 계속 진행됩니다)")
    
    # 🆕 크로스 플랫폼 팝업 알림 발송
    try:
        from agent.notification.popup import schedule_popup_notifications
        
        schedule_popup_notifications(
            schedule_dates=schedule_dates,
            styled_content=state.get("styled_content", ""),
            persona_style=state.get("persona_style", ""),
            category=state.get("category", "지식형"),
            schedule_id=schedule_id  # ✅ DB에서 생성된 ID 전달
        )
    except ImportError as e:
        print(f"\n⚠️  알림 모듈을 찾을 수 없습니다: {e}")
        print("   해결: pip3 install plyer")
    except Exception as e:
        print(f"\n⚠️  알림 발송 중 오류: {e}")

    # 윈도우에서 알림이 사라지는 문제 해결을 위해 잠시 대기
    if os.name == "nt":
        print("\n🔔 [Windows] 알림이 화면에 나타날 때까지 기다리는 중입니다...")
        print("   (알림이 뜨지 않는다면 엔터를 눌러 진행하세요)")

    return state


def check_cache_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    URL 또는 본문을 기준으로 기존 캐시 데이터가 있는지 확인하고,
    있다면 상태에 채워 무거운 노드들을 건너뛸 수 있도록 합니다.
    """

    if state.get("skip_cache") is True:
        state["is_cached"] = False
        return state

    url = state.get("url")
    text = state.get("input_text")
    
    if not url and not text:
        return state
    
    cached_data = load_cache(url, text)
    if cached_data:
        print(f"\n✨ [Cache] 기존 분석 결과를 발견했습니다! ('{url if url else '텍스트 입력'[:20]}...')")
        
        # 퀴즈 데이터 복원
        quiz_raw = cached_data.get("quiz")
        questions = []
        if quiz_raw:
            try:
                if isinstance(quiz_raw, str):
                    quiz_obj = json.loads(quiz_raw)
                else:
                    quiz_obj = quiz_raw
                questions = quiz_obj.get("questions", [])
            except:
                pass

        # 캐시된 데이터로 상태 업데이트
        state.update({
            "category": cached_data.get("category"),
            "saved_summary": cached_data.get("saved_summary"),
            "summary": cached_data.get("summary"),
            "quiz": quiz_raw,
            "questions": questions,
            "thought_questions": cached_data.get("thought_questions"),
            "augmentation_info": cached_data.get("augmentation_info"),
            "context": cached_data.get("context"),
            "citations": cached_data.get("citations"),
            "styled_content": cached_data.get("styled_content"),
            "persona_style": cached_data.get("persona_style"),
            "is_cached": True
        })
    else:
        state["is_cached"] = False
        
    return state


def save_cache_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """모든 프로세스가 완료된 후 분석 결과를 캐시에 저장합니다."""
    # 이미 캐시를 사용한 경우 중복 저장하지 않음
    if state.get("is_cached"):
        return state
        
    if save_cache(state):
        print("💾 [Cache] 분석 결과 캐시 저장 완료")
    return state
