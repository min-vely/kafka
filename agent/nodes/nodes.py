# agent/nodes/nodes.py
import os
import json
import re
from typing import Any, Dict
from dotenv import load_dotenv
from langchain_upstage import ChatUpstage
from langchain_core.tools import tool
from pydantic import TypeAdapter, HttpUrl

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

from agent.prompts import (
    SAFETY_PROMPT, #extract_content 노드에서 콘텐츠 안전도 검사하는 프롬프트 추가
    SUMMARY_DRAFT_PROMPT,
    QUIZ_FROM_SUMMARY_PROMPT,
    JUDGE_PROMPT,
    IMPROVE_DRAFT_PROMPT,
    CLASSIFY_PROMPT,
    THOUGHT_QUESTION_PROMPT,
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
    get_article_content,
    calculate_ebbinghaus_dates
)
from agent.rag import verify_summary_with_rag
from agent.database import get_db

load_dotenv()

# -----------------------------
# Tools
# -----------------------------
@tool
def get_latest_update_analysis(summary_text: str) -> str:
    """
    주어진 요약(summary_text)에 대해 최신 정보를 웹에서 검색하고, 
    과거 정보와 현재 상황을 비교 분석한 한 줄 소식을 반환합니다.
    최신 트렌드, 뉴스, 인물 현황 등의 업데이트가 필요할 때 사용합니다.
    """
    try:
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if not (tavily_key and TavilyClient):
            return "Tavily API Key가 없거나 라이브러리가 설치되지 않았습니다."
            
        client = TavilyClient(api_key=tavily_key)
        
        # 1. 최신 정보를 찾기 위한 전용 검색어 생성
        print("   - 전용 검색어 생성 중...")
        query_gen_prompt = TAVILY_QUERY_GENERATOR_PROMPT.format(summary_text=summary_text)
        search_query_resp = llm.invoke(query_gen_prompt)
        search_query = (search_query_resp.content or "").strip()
        print(f"   - 검색어: {search_query}")
        
        # 2. Tavily 검색
        print("   - Tavily 웹 검색 중...")
        response = client.search(query=search_query, search_depth="advanced", max_results=3)
        results = response.get("results", [])
        
        if not results:
            return "최신 정보를 검색해 보았으나, 현재로서는 업데이트된 내용이 발견되지 않았습니다."
            
        search_results_text = ""
        for res in results:
            search_results_text += f"- 제목: {res['title']}\n  내용: {res['content']}\n  URL: {res['url']}\n\n"
        
        # 3. 분석
        print("   - 검색 결과와 원문 비교 분석 중...")
        analysis_prompt = UPDATE_ANALYSIS_PROMPT.format(
            summary_text=summary_text,
            search_results=search_results_text
        )
        analysis_resp = llm.invoke(analysis_prompt)
        return (analysis_resp.content or "").strip()
        
    except Exception as e:
        return f"(웹 서치 및 분석 중 오류 발생: {str(e)})"


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
                content = get_article_content(url)
        except Exception as e:
            return {
                "input_text": f"Error: {str(e)}",
                "is_valid": False,
                "messages": "콘텐츠 추출 중 오류가 발생했습니다."
            }

    # 3. 추출된 내용이 아예 없는 경우 방어
    if not content:
        return {"is_valid": False, "messages": "분석할 콘텐츠가 없습니다."}

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
                "messages": "안전하지 않은 콘텐츠로 판단되어 중단합니다."
            }

        # 성공적으로 통과한 경우 리턴 (딕셔너리 형태 권장)
        return {
            "input_text": content,
            "is_valid": True,
            "is_safe": True,
            "messages": "콘텐츠 추출 및 안전성 검사 완료!"
        }

    except Exception as e:
        return {"is_valid": False, "is_safe": False, "messages": f"Safety Check 에러: {str(e)}"}

def classify_node(state):
    """3) 콘텐츠 성격을 분석하여 '지식형' 또는 '힐링형'으로 분류 (CoT 적용)"""
    print("\n[Node] classify_node: 콘텐츠 분류 중...")
    article = state["input_text"]
    resp = llm.invoke(CLASSIFY_PROMPT + "\n\n[CONTENT]\n" + article[:2000])
    raw_output = (resp.content or "").strip()
    
    # "Category: [지식형]" 또는 "Category: [힐링형]"에서 추출
    if "지식형" in raw_output:
        category = "지식형"
    elif "힐링형" in raw_output:
        category = "힐링형"
    else:
        category = "지식형"
        
    state["category"] = category
    return state


def synthesize_node(state):
    """4) 기사 원문으로 요약 초안(draft_summary)만 생성 (RAG 사용 X)"""
    print("[Node] synthesize_node: 요약 초안 생성 중...")
    article = state["input_text"]

    resp = llm.invoke(SUMMARY_DRAFT_PROMPT + "\n\n[ARTICLE]\n" + article)
    draft = (resp.content or "").strip()

    state["draft_summary"] = draft
    return state


def verify_node(state):
    """5) 요약 초안을 RAG로 검증(근거 문맥 구성/문장 검증 결과 저장)"""
    print("[Node] verify_node: RAG 검증 및 벡터 DB 생성 중 (시간이 소요될 수 있습니다)...")
    article = state["input_text"]
    draft = state.get("draft_summary", "")

    # rag.py의 원본 verify_summary_with_rag 호출 (시그니처에 맞춰 직접 전달)
    verified = verify_summary_with_rag(
        llm=llm,
        article_text=article,
        summary_draft=draft,
        per_sentence_k=3,
        relevance_threshold=0.12,
        max_context_chars=2800
    )

    state["query"] = verified.get("query", "")
    state["context"] = verified.get("context", "")
    state["citations"] = verified.get("citations", [])
    state["unsupported_sentences"] = verified.get("unsupported_sentences", [])

    verified_summary = verified.get("verified_summary", "")

    # 🔧 공백 정리 (이상한 이중 공백 제거)
    verified_summary = re.sub(r"\s+", " ", verified_summary).strip()

    state["summary"] = json.dumps(
        {
            "Summary": verified_summary,
            "UsedCitations": verified.get("used_citations", []),
            "Citations": verified.get("citations", []),
        },
        ensure_ascii=False,
    )

    # 컨텍스트가 비었거나 unsupported가 있으면 개선 루프
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

    resp = llm.invoke(
        JUDGE_PROMPT
        + "\n\n[CONTEXT]\n"
        + str(context)
        + "\n\n[SUMMARY]\n"
        + str(summary_text)
    )

    try:
        parsed = json.loads(resp.content)
    except Exception:
        parsed = {"score": 0, "needs_improve": True, "notes": "채점 JSON 파싱 실패"}

    score = int(parsed.get("score", 0))
    needs_improve = bool(parsed.get("needs_improve", score < 7))

    if state.get("unsupported_sentences"):
        needs_improve = True
        score = min(score, 6)

    state["judge_score"] = score
    state["needs_improve"] = needs_improve
    return state


def improve_node(state):
    """7) CONTEXT 기반으로 draft_summary(초안) 개선"""
    max_improve = int(state.get("max_improve", 2))
    count = int(state.get("improve_count", 0))

    if count >= max_improve:
        state["needs_improve"] = False
        return state

    context = state.get("context", "")
    draft = state.get("draft_summary", "")

    resp = llm.invoke(
        IMPROVE_DRAFT_PROMPT
        + "\n\n[CONTEXT]\n"
        + str(context)
        + "\n\n[SUMMARY_DRAFT]\n"
        + str(draft)
    )

    improved_draft = (resp.content or "").strip()
    state["draft_summary"] = improved_draft
    state["improve_count"] = count + 1

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
        resp_quiz = llm.invoke(QUIZ_FROM_SUMMARY_PROMPT + "\n\n[SUMMARY]\n" + str(summary_text))
        try:
            quiz_obj = json.loads(resp_quiz.content)
            if isinstance(quiz_obj, dict) and "questions" in quiz_obj:
                state["quiz"] = json.dumps(quiz_obj, ensure_ascii=False)
        except Exception:
            pass
    
    # 2. 힐링형: 생각 유도 질문만 생성
    else:
        resp_thought = llm.invoke(
            THOUGHT_QUESTION_PROMPT 
            + f"\n\n[CATEGORY]: {category}"
            + "\n\n[SUMMARY]\n" + str(summary_text)
        )
        try:
            thought_questions = json.loads(resp_thought.content)
            state["thought_questions"] = thought_questions if isinstance(thought_questions, list) else []
        except Exception:
            pass

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
    
    resp = llm.invoke(prompt)
    styled_content = (resp.content or "").strip()
    
    # 상태 업데이트
    state["persona_style"] = persona_def["name"]
    state["styled_content"] = styled_content
    state["persona_count"] = persona_count + 1
    
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
    - 일일 최대 4회 (알림 스트레스 방지 - 듀오링고 문제점 개선)
    - DB 저장: 프로그램 재시작 후에도 스케줄 유지
    """
    schedule_dates = calculate_ebbinghaus_dates()
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
    
    return state
