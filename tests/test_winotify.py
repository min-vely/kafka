#!/usr/bin/env python3
"""
Windows winotify 알림 테스트 스크립트

사용법:
    python tests/test_winotify.py
    
Windows에서만 작동합니다.
"""

import platform
import sys

def test_winotify_basic():
    """기본 winotify 알림 테스트"""
    print("="*60)
    print("🧪 winotify 기본 알림 테스트")
    print("="*60)
    print()
    
    # Windows 확인
    if platform.system() != 'Windows':
        print("⚠️  이 테스트는 Windows에서만 작동합니다.")
        print(f"   현재 플랫폼: {platform.system()}")
        return
    
    # winotify 가져오기
    try:
        from winotify import Notification, audio
        print("✅ winotify 라이브러리 로드 성공")
    except ImportError as e:
        print(f"❌ winotify를 찾을 수 없습니다: {e}")
        print("   설치: pip install winotify")
        sys.exit(1)
    
    # 테스트 1: 기본 알림
    print("\n[테스트 1] 기본 알림 (URL 없음)")
    try:
        toast = Notification(
            app_id="카프카 AI",
            title="🎓 테스트 알림",
            msg="winotify가 제대로 작동하는지 테스트 중입니다!",
            duration="short"
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        print("✅ 기본 알림 발송 성공!")
        print("   → 우측 하단 액션 센터를 확인하세요")
    except Exception as e:
        print(f"❌ 기본 알림 실패: {e}")
        return
    
    # 대기
    input("\n기본 알림을 확인하셨으면 Enter를 눌러 다음 테스트로 진행하세요...")
    
    # 테스트 2: URL 포함 알림 (액션 버튼)
    print("\n[테스트 2] URL 포함 알림 (퀴즈 풀기 버튼)")
    try:
        toast = Notification(
            app_id="카프카 AI",
            title="🎓 카프카 1차 복습 알림",
            msg="📝 오늘의 퀴즈가 준비되었습니다! 클릭하면 자동으로 열립니다",
            duration="long"
        )
        toast.set_audio(audio.Default, loop=False)
        toast.add_actions(
            label="퀴즈 풀기",
            launch="http://localhost:8080/quiz/1/1"
        )
        toast.show()
        print("✅ URL 포함 알림 발송 성공!")
        print("   → '퀴즈 풀기' 버튼을 클릭하세요")
        print("   → 브라우저에서 http://localhost:8080/quiz/1/1 열림")
    except Exception as e:
        print(f"❌ URL 포함 알림 실패: {e}")
        return
    
    print("\n" + "="*60)
    print("✅ 모든 테스트 완료!")
    print("="*60)
    print()
    print("💡 주의:")
    print("   - Windows 알림 설정에서 'Python' 알림이 허용되어야 합니다")
    print("   - 집중 모드가 꺼져 있어야 합니다")
    print("   - 첫 실행 시 Windows가 알림 권한을 요청할 수 있습니다")


if __name__ == "__main__":
    test_winotify_basic()
