#!/usr/bin/env python3
"""
데이터베이스 테스트 스크립트

사용법:
    python3 test_database.py
"""

from agent.database import ScheduleDB
from datetime import datetime

def test_basic_operations():
    """기본 CRUD 테스트"""
    print("="*60)
    print("🧪 데이터베이스 기본 기능 테스트")
    print("="*60)
    
    # 테스트용 DB (별도 파일)
    db = ScheduleDB('data/test_kafka.db')
    
    # 1. 스케줄 저장
    print("\n📝 테스트 1: 스케줄 저장")
    schedule_id = db.save_schedule(
        user_id="test_user_1",
        schedule_dates=["2026-02-12", "2026-02-15", "2026-02-18", "2026-02-22"],
        styled_content="야! 어제 배운 AI 내용 기억나? 딥러닝이 핵심이었잖아 ㅎㅎ",
        persona_style="친근한 친구",
        persona_count=0,
        url="https://example.com/ai-article",
        summary="AI는 인공지능입니다. 머신러닝은 AI의 하위 분야입니다. 딥러닝은 그중 하나입니다.",
        category="지식형"
    )
    print(f"✅ 저장 성공! Schedule ID: {schedule_id}")
    
    # 2. 스케줄 조회
    print("\n📋 테스트 2: 대기 중인 스케줄 조회")
    pending = db.get_pending_schedules()
    print(f"✅ 대기 중인 스케줄: {len(pending)}개")
    if pending:
        schedule = pending[0]
        print(f"   - ID: {schedule['id']}")
        print(f"   - 사용자: {schedule['user_id']}")
        print(f"   - 페르소나: {schedule['persona_style']}")
        print(f"   - 날짜: {schedule['schedule_dates']}")
    
    # 3. 특정 스케줄 조회
    print("\n🔍 테스트 3: ID로 스케줄 조회")
    schedule = db.get_schedule_by_id(schedule_id)
    if schedule:
        print(f"✅ 조회 성공!")
        print(f"   - 콘텐츠: {schedule['styled_content'][:50]}...")
        print(f"   - 생성일: {schedule['created_at']}")
    
    # 4. 알림 발송 이력 기록
    print("\n📨 테스트 4: 알림 발송 이력 기록")
    db.log_notification(
        schedule_id=schedule_id,
        notification_index=1,
        scheduled_date="2026-02-12",
        is_success=True
    )
    print("✅ 발송 이력 기록 완료")
    
    # 5. 통계 조회
    print("\n📊 테스트 5: 통계 조회")
    stats = db.get_statistics()
    print("✅ 통계:")
    print(f"   - 전체 스케줄: {stats['total_schedules']}개")
    print(f"   - 대기 중: {stats['pending']}개")
    print(f"   - 완료: {stats['completed']}개")
    print(f"   - 발송된 알림: {stats['total_notifications_sent']}개")
    
    # 6. 스케줄 완료 처리
    print("\n✅ 테스트 6: 스케줄 완료 처리")
    db.mark_as_completed(schedule_id)
    
    # 다시 조회해서 확인
    pending_after = db.get_pending_schedules()
    print(f"✅ 완료 처리 후 대기 중인 스케줄: {len(pending_after)}개")
    
    # DB 종료
    db.close()
    
    print("\n" + "="*60)
    print("✅ 모든 테스트 통과!")
    print("="*60)
    print("\n💡 생성된 파일: data/test_kafka.db")
    print("   확인: sqlite3 data/test_kafka.db")
    print("        .tables")
    print("        SELECT * FROM schedules;")


def test_multiple_users():
    """여러 사용자 테스트"""
    print("\n" + "="*60)
    print("🧪 다중 사용자 테스트")
    print("="*60)
    
    db = ScheduleDB('data/test_kafka.db')
    
    # 여러 사용자 추가
    users = [
        ("user_a", "친근한 친구", "지식형"),
        ("user_b", "지혜로운 멘토", "일반형"),
        ("user_c", "공감하는 친구", "지식형"),
    ]
    
    for user_id, persona, category in users:
        db.save_schedule(
            user_id=user_id,
            schedule_dates=["2026-02-12", "2026-02-15", "2026-02-18", "2026-02-22"],
            styled_content=f"{user_id}의 테스트 콘텐츠입니다.",
            persona_style=persona,
            persona_count=0,
            category=category
        )
        print(f"✅ {user_id} 스케줄 생성")
    
    # 전체 조회
    all_pending = db.get_pending_schedules()
    print(f"\n📊 전체 대기 중인 스케줄: {len(all_pending)}개")
    
    for schedule in all_pending:
        print(f"   - {schedule['user_id']}: {schedule['persona_style']} ({schedule['category']})")
    
    db.close()
    print("\n✅ 다중 사용자 테스트 완료!")


def main():
    """메인 실행 함수"""
    try:
        # 기본 테스트
        test_basic_operations()
        
        # 다중 사용자 테스트
        test_multiple_users()
        
        print("\n🎉 모든 데이터베이스 테스트가 성공적으로 완료되었습니다!")
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
