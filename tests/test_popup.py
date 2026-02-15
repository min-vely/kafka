#!/usr/bin/env python3
"""
팝업 알림 기능 테스트 스크립트

사용법:
    python3 test_popup.py
"""

import platform
from agent.notification.popup import send_popup_notification, get_platform_info

def main():
    print("="*60)
    print("🧪 카프카 팝업 알림 테스트")
    print("="*60)
    print(f"\n현재 플랫폼: {get_platform_info()}")
    print(f"Python 감지 OS: {platform.system()}\n")
    
    # 테스트 1: 지식형 페르소나 (친근한 친구)
    print("📝 테스트 1: 지식형 - 친근한 친구 페르소나")
    send_popup_notification(
        title="🎓 카프카 1차 복습 알림 (친근한 친구)",
        message="야! 어제 배운 AI 내용 기억나?\n딥러닝이 핵심이었잖아 ㅎㅎ\nGPT는 언어 모델인데 완전 신기했지?",
        timeout=8
    )
    
    input("\n⏸️  알림을 확인하셨나요? Enter를 눌러 다음 테스트로...")
    
    # 테스트 2: 일반형 페르소나 (공감하는 친구)
    print("\n📝 테스트 2: 일반형 - 공감하는 친구 페르소나")
    send_popup_notification(
        title="💭 카프카 복습 알림 (공감하는 친구)",
        message="어제 그 글 보고 나도 되게 울컥했어.\n너는 어땠어?\n작은 행복을 느끼며 살아가는 게 중요하다고 생각해.",
        timeout=8
    )
    
    print("\n" + "="*60)
    print("✅ 테스트 완료!")
    print("="*60)
    print("\n💡 알림이 화면에 표시되었다면 성공입니다!")
    print("   - macOS: 우측 상단 알림 센터")
    print("   - Windows: 우측 하단 액션 센터\n")

if __name__ == "__main__":
    main()
