"""
[Agent Tools Module]
이 모듈은 Upstage Solar 모델을 사용하여 텍스트 내 일정을 추출하고 
구글 캘린더 등록 링크를 생성하는 에이전트 도구를 포함합니다.

필요 라이브러리 설치:
pip install -U langchain langchain-community langchain-upstage langchainhub
"""

import os
import urllib.parse
from datetime import datetime, timedelta
from langchain_upstage import ChatUpstage
from langchain_core.tools import tool

@tool
def calendar_event_adder(event_name: str, date_str: str, time_str: str = "09:00", details: str = ""):
    """
    텍스트에서 실제 행사/이벤트가 열리는 일시를 추출하여 구글 캘린더 링크를 생성합니다.
    기사 작성일이 아닌, 실제 '행사 개최일'을 사용해야 합니다.
    date_str: YYYY-MM-DD 형식
    time_str: HH:MM 형식 (기본값 09:00)
    """
    try:
        # 날짜와 시간 결합
        normalized_date = date_str.replace(".", "-").strip()
        full_datetime_str = f"{normalized_date} {time_str}"
        base_date = datetime.strptime(full_datetime_str, "%Y-%m-%d %H:%M")
        
        # 구글 캘린더 형식 (UTC 기준 Z를 붙이지만, 여기서는 단순화하여 생성)
        start_time = base_date.strftime("%Y%m%dT%H%M%S")
        end_time = (base_date + timedelta(hours=2)).strftime("%Y%m%dT%H%M%S")
        
        params = {
            "action": "TEMPLATE",
            "text": event_name,
            "dates": f"{start_time}/{end_time}",
            "details": details,
            "output": "xml"
        }
        gcal_url = f"https://www.google.com/calendar/render?{urllib.parse.urlencode(params)}"
        
        return f"\n\n📅 **[에이전트 알림]** 관련 일정을 찾았습니다!\n[구글 캘린더에 등록하기]({gcal_url})"
    except Exception:
        return ""

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