import urllib.parse
from datetime import datetime, timedelta
from langchain_core.tools import tool

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
