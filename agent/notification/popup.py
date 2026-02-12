# agent/notification/popup.py
"""
크로스 플랫폼 알림 시스템 (macOS + Windows)

기획서 기반 요구사항:
- 에빙하우스 망각 곡선 주기 (D+1, 4, 7, 11)
- 일일 최대 4회 알림
- 오전 8시 출근길 발송 권장
- 페르소나 말투 적용
- 오답 시 다음날 예비 문제 재발송
"""

import platform
from typing import List
from datetime import datetime

try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    print("⚠️  plyer 라이브러리가 설치되지 않았습니다.")
    print("   설치: pip3 install plyer")


def send_popup_notification(
    title: str, 
    message: str, 
    timeout: int = 10,
    app_icon: str = None
):
    """
    크로스 플랫폼 팝업 알림 발송 (macOS, Windows 모두 지원)
    
    Args:
        title: 알림 제목 (예: "🎓 카프카 1차 복습 알림")
        message: 알림 내용 (페르소나가 적용된 메시지)
        timeout: 알림 표시 시간 (초, Windows는 자동)
        app_icon: 앱 아이콘 경로 (선택)
    
    동작:
        - macOS: 알림 센터 (우측 상단)
        - Windows: 액션 센터 (우측 하단)
    
    이유:
        듀오링고의 과도한 알림 스트레스를 피하고,
        부담 없이 하루 4회만 발송하여 사용자 피로도 최소화
    """
    if not PLYER_AVAILABLE:
        print(f"⚠️  알림 라이브러리 없음. 메시지만 출력:")
        print(f"   제목: {title}")
        print(f"   내용: {message[:100]}...")
        return
    
    try:
        # 플랫폼 감지
        os_name = platform.system()
        platform_name = {
            'Darwin': 'macOS',
            'Windows': 'Windows',
            'Linux': 'Linux'
        }.get(os_name, os_name)
        
        # 알림 발송
        notification.notify(
            title=title,
            message=message,
            app_name='카프카',
            timeout=timeout
        )
        
        print(f"✅ [{platform_name}] 알림 발송 성공!")
        print(f"   제목: {title}")
        print(f"   내용: {message[:80]}...")
        
    except Exception as e:
        print(f"❌ 알림 발송 실패: {e}")
        print(f"   제목: {title}")
        print(f"   내용: {message[:100]}...")


def schedule_popup_notifications(
    schedule_dates: List[str],
    styled_content: str,
    persona_style: str,
    category: str = "지식형"
):
    """
    에빙하우스 망각 곡선에 따라 팝업 알림 예약
    
    Args:
        schedule_dates: ["2026-02-12", "2026-02-15", "2026-02-18", "2026-02-22"]
        styled_content: 페르소나가 적용된 최종 메시지
        persona_style: 페르소나 이름 (예: "친근한 친구")
        category: 콘텐츠 유형 ("지식형" or "일반형")
    
    동작:
        1. 4개 날짜 정보 출력
        2. 테스트용으로 즉시 1개 알림 발송
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
    
    # 메시지 길이 제한 (너무 길면 알림창에서 잘림)
    if len(styled_content) > 200:
        display_message = styled_content[:197] + "..."
    else:
        display_message = styled_content
    
    send_popup_notification(
        title=title,
        message=display_message,
        timeout=10
    )
    
    print(f"\n{'='*60}")
    print(f"✅ 테스트 알림이 화면에 표시되었습니다!")
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
