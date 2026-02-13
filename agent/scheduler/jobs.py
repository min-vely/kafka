# agent/scheduler/jobs.py
"""
스케줄링 작업 함수들

실제로 실행될 작업(Job)들을 정의합니다.
"""

from datetime import datetime, date
from typing import List, Dict
import json


def send_daily_notifications():
    """
    매일 오전 8시에 실행되는 메인 작업
    
    동작:
    1. DB에서 오늘 발송할 스케줄 조회
    2. 각 스케줄에 대해 알림 발송
    3. 발송 결과를 DB에 기록
    
    이유:
    - 에빙하우스 망각 곡선에 따라 정해진 날짜에 복습 알림 발송
    - 오전 8시 출근길 시간대는 인지 부하가 적어 학습에 효과적
    """
    from agent.database import get_db
    
    today = date.today().isoformat()
    print(f"\n{'='*60}")
    print(f"📅 일일 알림 발송 작업 시작: {today}")
    print(f"{'='*60}\n")
    
    db = get_db()
    
    try:
        # 오늘 발송할 스케줄 조회
        schedules = db.get_schedules_for_date(today)
        
        if not schedules:
            print(f"📭 오늘 발송할 알림이 없습니다.")
            return
        
        print(f"📬 발송 대상: {len(schedules)}개 스케줄\n")
        
        # 각 스케줄에 대해 알림 발송
        success_count = 0
        fail_count = 0
        
        for schedule in schedules:
            try:
                send_notification_for_schedule(schedule, today)
                success_count += 1
            except Exception as e:
                print(f"❌ 스케줄 {schedule['id']} 발송 실패: {e}")
                fail_count += 1
        
        print(f"\n{'='*60}")
        print(f"✅ 발송 완료: {success_count}개 성공, {fail_count}개 실패")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"❌ 일일 알림 발송 중 오류: {e}")
        import traceback
        traceback.print_exc()


def send_notification_for_schedule(schedule: Dict, target_date: str):
    """
    특정 스케줄에 대해 알림 발송
    
    Args:
        schedule: 스케줄 정보 딕셔너리
        target_date: 발송 대상 날짜 (YYYY-MM-DD)
    
    동작:
    1. schedule_dates에서 몇 번째 알림인지 확인
    2. 중복 발송 방지 체크
    3. 팝업 알림 발송
    4. DB에 발송 기록
    5. 마지막 알림이면 완료 처리
    """
    from agent.notification.popup import send_popup_notification
    from agent.database import get_db
    
    schedule_id = schedule['id']
    schedule_dates = json.loads(schedule['schedule_dates'])
    
    # 몇 번째 알림인지 확인
    try:
        notification_index = schedule_dates.index(target_date) + 1  # 1부터 시작
    except ValueError:
        print(f"⚠️  스케줄 {schedule_id}: 날짜 {target_date}를 찾을 수 없음")
        return
    
    db = get_db()
    
    # 중복 발송 방지
    if is_already_sent(db, schedule_id, notification_index):
        print(f"⏭️  스케줄 {schedule_id}: {notification_index}차 알림 이미 발송됨 (스킵)")
        return
    
    print(f"📤 스케줄 {schedule_id}: {notification_index}차 알림 발송 중...")
    
    try:
        # 알림 제목 및 내용 생성
        category = schedule.get('category', '지식형')
        persona_style = schedule.get('persona_style', '친근한 친구')
        styled_content = schedule.get('styled_content', '')
        
        emoji = "🎓" if category == "지식형" else "💭"
        title = f"{emoji} 카프카 {notification_index}차 복습 알림 ({persona_style})"
        
        # 메시지 길이 제한
        if len(styled_content) > 200:
            message = styled_content[:197] + "..."
        else:
            message = styled_content
        
        # 팝업 발송
        send_popup_notification(
            title=title,
            message=message,
            timeout=10
        )
        
        # 발송 성공 로그
        db.log_notification(
            schedule_id=schedule_id,
            notification_index=notification_index,
            scheduled_date=target_date,
            is_success=True
        )
        
        print(f"✅ 스케줄 {schedule_id}: {notification_index}차 알림 발송 완료")
        
        # 마지막 알림이면 완료 처리
        if notification_index == len(schedule_dates):
            db.mark_as_completed(schedule_id)
            print(f"🎉 스케줄 {schedule_id}: 모든 알림 발송 완료 (상태: completed)")
        
    except Exception as e:
        # 발송 실패 로그
        db.log_notification(
            schedule_id=schedule_id,
            notification_index=notification_index,
            scheduled_date=target_date,
            is_success=False,
            error_message=str(e)
        )
        print(f"❌ 스케줄 {schedule_id}: {notification_index}차 알림 발송 실패 - {e}")
        raise


def is_already_sent(db, schedule_id: int, notification_index: int) -> bool:
    """
    이미 발송된 알림인지 확인
    
    Args:
        db: 데이터베이스 인스턴스
        schedule_id: 스케줄 ID
        notification_index: 알림 차수 (1, 2, 3, 4)
    
    Returns:
        이미 발송되었으면 True, 아니면 False
    
    이유:
    - 중복 발송 방지
    - 스케줄러 재시작 시에도 같은 알림을 두 번 보내지 않음
    """
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE schedule_id = ? 
        AND notification_index = ?
        AND is_success = 1
    """, (schedule_id, notification_index))
    
    count = cursor.fetchone()[0]
    return count > 0


# 테스트용 함수
def test_send_notification():
    """즉시 알림 발송 테스트"""
    from agent.database import get_db
    
    db = get_db()
    schedules = db.get_pending_schedules()
    
    if not schedules:
        print("⚠️  발송할 스케줄이 없습니다. 먼저 main.py를 실행하여 스케줄을 생성하세요.")
        return
    
    # 첫 번째 스케줄 테스트
    schedule = schedules[0]
    schedule_dates = json.loads(schedule['schedule_dates'])
    
    print(f"🧪 테스트 모드: 스케줄 {schedule['id']}의 1차 알림 발송\n")
    
    try:
        send_notification_for_schedule(schedule, schedule_dates[0])
        print(f"\n✅ 테스트 성공!")
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 직접 실행 시 테스트
    print("🧪 스케줄러 작업 테스트")
    test_send_notification()
