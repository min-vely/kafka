# agent/notification/popup.py
"""
크로스 플랫폼 알림 시스템 (macOS + Windows)

기획서 기반 요구사항:
- 에빙하우스 망각 곡선 주기 (D+1, 4, 7, 11)
- 일일 최대 4회 알림
- 오전 8시 출근길 발송 권장
- 페르소나 말투 적용
- 오답 시 다음날 예비 문제 재발송
- 클릭 시 웹페이지 자동 실행
"""

import platform
from typing import List, Optional
from datetime import datetime
import subprocess

# 플랫폼 감지
OS_TYPE = platform.system()

# macOS용 클릭 가능한 알림
try:
    import pync
    PYNC_AVAILABLE = True
except ImportError:
    PYNC_AVAILABLE = False

# Windows용 클릭 가능한 알림
try:
    from win10toast import ToastNotifier
    WIN10TOAST_AVAILABLE = True
except ImportError:
    WIN10TOAST_AVAILABLE = False

# 기본 알림 (클릭 불가)
try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    print("⚠️  알림 라이브러리가 설치되지 않았습니다.")
    print("   macOS: pip3 install pync")
    print("   Windows: pip3 install win10toast")
    print("   기타: pip3 install plyer")


def send_popup_notification(
    title: str, 
    message: str, 
    timeout: int = 10,
    url: Optional[str] = None,
    app_icon: str = None
):
    """
    크로스 플랫폼 클릭 가능한 팝업 알림 발송 (macOS, Windows 모두 지원)
    
    Args:
        title: 알림 제목 (예: "🎓 카프카 1차 복습 알림")
        message: 알림 내용 (페르소나가 적용된 메시지)
        timeout: 알림 표시 시간 (초)
        url: 클릭 시 열릴 URL (선택)
        app_icon: 앱 아이콘 경로 (선택)
    
    동작:
        - macOS: pync 알림 (클릭 시 URL 열기)
        - Windows: win10toast 알림 (클릭 시 URL 열기)
        - 기타: plyer 알림 (클릭 불가)
    
    이유:
        - 사용자가 팝업을 클릭하면 바로 웹 퀴즈 페이지로 이동
        - 수동으로 URL 복사할 필요 없음
        - 사용자 경험 개선
    """
    try:
        platform_name = {
            'Darwin': 'macOS',
            'Windows': 'Windows',
            'Linux': 'Linux'
        }.get(OS_TYPE, OS_TYPE)
        
        # macOS: pync 사용 (클릭 시 URL 열기)
        if OS_TYPE == 'Darwin' and PYNC_AVAILABLE and url:
            pync.notify(
                message,
                title=title,
                open=url,  # 클릭 시 이 URL 열기
                sound='default',  # 알림 소리
                contentImage=app_icon
            )
            print(f"✅ [macOS - 클릭 가능] 알림 발송 성공!")
            print(f"   제목: {title}")
            print(f"   클릭 시 열림: {url}")
        
        # Windows: win10toast 사용 (클릭 시 URL 열기)
        elif OS_TYPE == 'Windows' and WIN10TOAST_AVAILABLE and url:
            import webbrowser
            
            def open_url():
                """알림 클릭 시 실행될 콜백"""
                webbrowser.open(url)
            
            toaster = ToastNotifier()
            toaster.show_toast(
                title,
                message,
                duration=timeout,
                threaded=True,
                callback_on_click=open_url
            )
            print(f"✅ [Windows - 클릭 가능] 알림 발송 성공!")
            print(f"   제목: {title}")
            print(f"   클릭 시 열림: {url}")
        
        # 기타 플랫폼 또는 라이브러리 없을 때: plyer 사용
        elif PLYER_AVAILABLE:
            notification.notify(
                title=title,
                message=message,
                app_name='카프카',
                timeout=timeout
            )
            print(f"✅ [{platform_name}] 알림 발송 성공!")
            print(f"   제목: {title}")
            print(f"   내용: {message[:80]}...")
            
            if url:
                print(f"   ⚠️  클릭 불가 - URL 수동 입력: {url}")
        
        else:
            # 모든 라이브러리 없을 때
            print(f"⚠️  알림 라이브러리 없음. 메시지만 출력:")
            print(f"   제목: {title}")
            print(f"   내용: {message[:100]}...")
            if url:
                print(f"   URL: {url}")
        
    except Exception as e:
        print(f"❌ 알림 발송 실패: {e}")
        print(f"   제목: {title}")
        print(f"   내용: {message[:100]}...")
        if url:
            print(f"   URL: {url}")


def schedule_popup_notifications(
    schedule_dates: List[str],
    styled_content: str,
    persona_style: str,
    category: str = "지식형",
    schedule_id: int = None
):
    """
    에빙하우스 망각 곡선에 따라 팝업 알림 예약
    
    Args:
        schedule_dates: ["2026-02-12", "2026-02-15", "2026-02-18", "2026-02-22"]
        styled_content: 페르소나가 적용된 최종 메시지
        persona_style: 페르소나 이름 (예: "친근한 친구")
        category: 콘텐츠 유형 ("지식형" or "일반형")
        schedule_id: 스케줄 DB ID (퀴즈 URL 생성용)
    
    동작:
        1. 4개 날짜 정보 출력
        2. 테스트용으로 즉시 1개 알림 발송 (클릭 시 웹 퀴즈 열림)
        3. 실제 서비스에서는 스케줄러(APScheduler)로 예약
    
    기획서 기반 설계:
        - 발송 시간: 오전 8시 (출근길, 인지 부하가 적은 시간)
        - 발송 주기: D+1, D+4, D+7, D+11 (에빙하우스 망각 곡선)
        - 일일 최대 4회 (알림 스트레스 방지)
    """
    print(f"\n{'='*60}")
    print(f"📅 에빙하우스 알림 스케줄 생성 완료")
    print(f"{'='*60}")
    print(f"페르소나: {persona_style}")
    print(f"콘텐츠 유형: {category}")
    print(f"\n예정된 알림:")
    
    for i, date in enumerate(schedule_dates, 1):
        print(f"  {i}차 알림: {date} 오전 8시 (출근길)")
    
    print(f"\n💡 실제 서비스에서는 위 날짜에 자동으로 알림이 발송됩니다.")
    print(f"   현재는 테스트를 위해 즉시 알림을 보냅니다.\n")
    
    # 테스트용: 즉시 알림 발송 (1차 알림 미리보기)
    emoji = "🎓" if category == "지식형" else "💭"
    title = f"{emoji} 카프카 1차 복습 알림 ({persona_style})"
    
    # 메시지 및 URL 생성
    quiz_url = None
    if category == "지식형" and schedule_id:
        # 정보형: 퀴즈 URL 포함 (클릭 시 자동으로 웹페이지 열림)
        quiz_url = f"http://localhost:8080/quiz/{schedule_id}/1"
        display_message = f"📝 오늘의 퀴즈가 준비되었습니다!\n\n1번째 문제를 풀러 가세요 (클릭하면 자동으로 열립니다)"
    else:
        # 힐링형 또는 schedule_id 없을 때: 기존 방식
        if len(styled_content) > 200:
            display_message = styled_content[:197] + "..."
        else:
            display_message = styled_content
    
    send_popup_notification(
        title=title,
        message=display_message,
        timeout=30,  # URL 확인 시간 필요
        url=quiz_url  # ✅ 클릭 시 웹페이지 열림
    )
    
    print(f"\n{'='*60}")
    print(f"✅ 테스트 알림이 화면에 표시되었습니다!")
    if quiz_url:
        print(f"🔗 클릭하면 웹 퀴즈가 열립니다: {quiz_url}")
    print(f"{'='*60}\n")


def get_platform_info():
    """
    현재 실행 중인 플랫폼 정보 반환
    
    Returns:
        플랫폼 이름 ("macOS", "Windows", "Linux")
    """
    os_name = platform.system()
    
    platform_map = {
        'Darwin': 'macOS',
        'Windows': 'Windows',
        'Linux': 'Linux'
    }
    
    return platform_map.get(os_name, os_name)


# 테스트 함수
def test_notification():
    """알림 기능 간단 테스트"""
    send_popup_notification(
        title="🎓 카프카 테스트 알림",
        message="야! 알림이 제대로 뜨는지 테스트 중이야 ㅎㅎ",
        timeout=5
    )


if __name__ == "__main__":
    # 직접 실행 시 테스트
    print(f"현재 플랫폼: {get_platform_info()}")
    test_notification()
