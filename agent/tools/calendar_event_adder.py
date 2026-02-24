import urllib.parse
from datetime import datetime, timedelta
from langchain_core.tools import tool
import os
from langchain_upstage import ChatUpstage

@tool
def calendar_event_adder(
    event_name: str,
    date_str: str,
    time_str: str = "09:00",
    end_time_str: str = "",
    details: str = "",
):
    """
    기사에서 추출한 행사 정보를 바탕으로 구글 캘린더 등록 링크를 생성합니다.

    Args:
      event_name: 일정 제목
      date_str: YYYY-MM-DD
      time_str: HH:MM (시작)
      end_time_str: HH:MM (종료) - 없으면 기본 2시간
      details: 일정 설명
    """
    try:
        date_norm = date_str.replace(".", "-").strip()

        start_dt = datetime.strptime(f"{date_norm} {time_str}", "%Y-%m-%d %H:%M")

        if end_time_str and end_time_str.strip():
            end_dt = datetime.strptime(f"{date_norm} {end_time_str.strip()}", "%Y-%m-%d %H:%M")
            # 종료가 시작보다 이르면(자정 넘어가는 케이스 등) 다음날로 보정
            if end_dt <= start_dt:
                end_dt = end_dt + timedelta(days=1)
        else:
            end_dt = start_dt + timedelta(hours=2)

        start_str = start_dt.strftime("%Y%m%dT%H%M%S")
        end_str = end_dt.strftime("%Y%m%dT%H%M%S")

        params = {
            "action": "TEMPLATE",
            "text": event_name,
            "dates": f"{start_str}/{end_str}",
            "details": details,
            "output": "xml",
        }

        base = "https://www.google.com/calendar/render"
        query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        link = f"{base}?{query}"

        return (
            "📅 **[에이전트 알림]** 관련 일정을 찾았습니다!\n"
            f"[구글 캘린더에 등록하기]({link})"
        )

    except Exception as e:
        return f"⚠️ 캘린더 링크 생성 실패: {repr(e)}"


def run_calendar_agent(text_content: str):
    llm = ChatUpstage(
        model=os.getenv("KAFKA_MODEL", "solar-pro"),
        temperature=0
    )
    
    tools = [calendar_event_adder]
    llm_with_tools = llm.bind_tools(tools)
    
    # 지시사항 강화: 작성일과 행사일 구분 명시
    prompt_instruction = f"""
    당신은 일정을 등록하는 엄격한 비서입니다. 다음 지침을 반드시 지키세요:

    1. 텍스트 내에서 '행사 일시', '일정', 'Event Date'와 같은 문구 바로 옆에 있는 날짜를 찾으세요.
    2. 절대(NEVER) 'Published Time', '작성일', '게시일'과 같은 메타데이터 날짜를 행사 날짜로 쓰지 마세요.
    3. 만약 오늘({datetime.now().strftime('%Y-%m-%d')})보다 이전의 날짜(예: 2025년)가 추출된다면, 그건 행사 날짜가 아닐 확률이 높습니다. 그럴 땐 도구를 호출하지 말고 "NONE"을 반환하세요.
    4. 텍스트에 "2026.01.30"이나 "1월 30일" 같은 미래 날짜가 있는지 눈을 크게 뜨고 찾으세요.
    
    분석할 텍스트:
    {text_content}
    """
    
    try:
        msg = llm_with_tools.invoke(prompt_instruction)
        
        if msg.tool_calls:
            # 여러 개가 나올 수 있으므로 첫 번째 호출 사용
            tool_call = msg.tool_calls[0]
            result = calendar_event_adder.invoke(tool_call["args"])
            return text_content + result
        
        return text_content
        
    except Exception as e:
        print(f"⚠️ 에이전트 실행 중 오류: {e}")
        return text_content
