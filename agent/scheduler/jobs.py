# agent/scheduler/jobs.py
"""
스케줄링 작업 함수들

실제로 실행될 작업(Job)들을 정의합니다.
"""

from datetime import datetime, date
from typing import List, Dict
import json
import time

from agent.utils import clean_content_for_display


from agent.utils import clean_content_for_display


def process_one_from_queue(db):
    """
    URL 대기열에서 1개 꺼내서 전체 파이프라인 처리 (매일 1개씩)
    
    동작:
    - 큐에서 가장 오래된 URL 1개 조회
    - graph.invoke()로 전체 워크플로우 실행
    - schedules 테이블에 저장됨 (에빙하우스 날짜 적용)
    """
    item = db.get_next_from_url_queue()
    if not item:
        return
    
    queue_id = item['id']
    url = item['url']
    
    print(f"📥 대기열에서 URL 처리 중 (큐 ID: {queue_id})")
    print(f"   URL: {url[:60]}..." if len(url) > 60 else f"   URL: {url}")
    
    db.mark_queue_item_processing(queue_id)
    
    try:
        from agent.graph import build_graph
        
        graph = build_graph()
        initial_state = {
            "user_input": url,
            "input_text": "",
            "max_improve": 3
        }
        
        result = graph.invoke(initial_state)
        schedule_id = result.get("schedule_id") or 0
        
        db.mark_queue_item_completed(queue_id, schedule_id)
        print(f"✅ 큐 항목 처리 완료 (Schedule ID: {schedule_id})")
        
    except Exception as e:
        db.mark_queue_item_failed(queue_id)
        print(f"❌ 큐 항목 처리 실패: {e}")
        import traceback
        traceback.print_exc()


def send_daily_notifications(test_multi: bool = False):
    """
    매일 오전 8시에 실행되는 메인 작업
    
    Args:
        test_multi: 여러 개 알림 테스트 모드 (test_multi_user 스케줄은 발송 이력 무시)
    
    동작:
    1. URL 대기열에서 1개 꺼내 처리 (매일 1개씩)
    2. DB에서 오늘 발송할 스케줄 조회 (에빙하우스 겹침 시 하루 최대 4개)
    3. 오늘 재발송할 스케줄 조회 (퀴즈 오답 시 하루 최대 1개, 총 5개까지)
    4. 각 스케줄에 대해 알림 발송
    
    이유:
    - URL 무제한 저장, 매일 1개씩 처리 (1일 1스크랩처럼)
    - 에빙하우스 망각 곡선에 따라 정해진 날짜에 복습 알림 발송
    - 에빙하우스 날짜 겹침 시 하루 최대 4개 (정보 과부하 방지)
    - 퀴즈 오답 재발송 시 하루 최대 5개 (4+1)
    """
    from agent.database import get_db
    
    today = date.today().isoformat()
    print(f"\n{'='*60}")
    print(f"📅 일일 알림 발송 작업 시작: {today}")
    print(f"{'='*60}\n")
    
    db = get_db()
    
    try:
        # 1. URL 대기열에서 1개 꺼내 처리 (매일 1개씩)
        process_one_from_queue(db)
        
        # 2. 오늘 발송할 스케줄 조회 (에빙하우스 겹침 시 하루 최대 4개)
        schedules = db.get_schedules_for_date(today, limit=4)
        
        # 3. 오늘 재발송할 스케줄 조회 (퀴즈 오답 시 하루 최대 1개)
        retry_schedules = db.get_retry_schedules_for_date(today, limit=1)
        
        total_count = len(schedules) + len(retry_schedules)
        
        if total_count == 0:
            pending_count = db.get_pending_queue_count()
            if pending_count > 0:
                print(f"📭 오늘 발송할 알림은 없습니다. (대기 중인 URL: {pending_count}개)")
            else:
                print(f"📭 오늘 발송할 알림이 없습니다.")
            return
        
        print(f"📬 발송 대상: 정규 {len(schedules)}개 + 재발송 {len(retry_schedules)}개 (하루 최대 5개)\n")
        
        success_count = 0
        fail_count = 0
        
        # 정규 스케줄 발송 (여러 개일 때 순차 표시를 위해 test_multi에서 간격 추가)
        for i, schedule in enumerate(schedules):
            try:
                if test_multi and i > 0:
                    # 이전 알림이 화면에 잘 보이도록 2초 간격
                    time.sleep(2)
                send_notification_for_schedule(schedule, today, test_multi=test_multi)
                success_count += 1
            except Exception as e:
                print(f"❌ 스케줄 {schedule['id']} 발송 실패: {e}")
                fail_count += 1
        
        # 재발송 스케줄 처리
        for retry in retry_schedules:
            try:
                schedule = db.get_schedule_by_id(retry['schedule_id'])
                if schedule:
                    print(f"🔄 재발송: 스케줄 {retry['schedule_id']}, {retry['notification_index']}차 (시도 {retry['retry_count']}회)")
                    send_notification_for_schedule(schedule, today, notification_index=retry['notification_index'])
                    db.mark_retry_as_completed(retry['id'])
                    success_count += 1
            except Exception as e:
                print(f"❌ 재발송 실패 (retry_id: {retry['id']}): {e}")
                fail_count += 1
        
        print(f"\n{'='*60}")
        print(f"✅ 발송 완료: {success_count}개 성공, {fail_count}개 실패")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"❌ 일일 알림 발송 중 오류: {e}")
        import traceback
        traceback.print_exc()


def send_notification_for_schedule(schedule: Dict, target_date: str, notification_index: int = None, test_multi: bool = False):
    """
    특정 스케줄에 대해 알림 발송
    
    Args:
        schedule: 스케줄 정보 딕셔너리
        target_date: 발송 대상 날짜 (YYYY-MM-DD)
        notification_index: 알림 차수 (재발송 시 직접 지정, 선택)
        test_multi: test_multi_user 스케줄이면 발송 이력 무시 (여러 개 알림 반복 테스트용)
    
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
    try:
        schedule_dates = json.loads(schedule['schedule_dates'])
    except (json.JSONDecodeError, TypeError) as e:
        print(f"⚠️  스케줄 {schedule_id}: schedule_dates 파싱 오류 - {e}")
        return

    from agent.utils import validate_schedule_dates
    is_valid, validated_dates, err_msg = validate_schedule_dates(schedule_dates)
    if not is_valid:
        print(f"⚠️  스케줄 {schedule_id}: 날짜 검증 실패 - {err_msg}")
        return
    schedule_dates = validated_dates

    # 몇 번째 알림인지 확인 (재발송 시에는 직접 전달받음)
    if notification_index is None:
        try:
            notification_index = schedule_dates.index(target_date) + 1  # 1부터 시작
        except ValueError:
            print(f"⚠️  스케줄 {schedule_id}: 날짜 {target_date}를 찾을 수 없음")
            return
    
    db = get_db()
    
    # 중복 발송 방지 (test_multi_user + test_multi 모드에서는 스킵 안 함)
    skip_sent_check = test_multi and schedule.get("user_id") == "test_multi_user"
    if not skip_sent_check and is_already_sent(db, schedule_id, notification_index):
        print(f"⏭️  스케줄 {schedule_id}: {notification_index}차 알림 이미 발송됨 (스킵)")
        return
    
    print(f"📤 스케줄 {schedule_id}: {notification_index}차 알림 발송 중...")
    
    try:
        # 알림 제목 및 내용 생성
        category = schedule.get('category', '지식형')
        styled_content = schedule.get('styled_content', '')
        
        # 페르소나를 notification_index에 맞게 선택
        persona_map = {
            1: "친근한 친구",
            2: "다정한 선배",
            3: "엄격한 교수",
            4: "유머러스한 코치",
            5: "밈 마스터"  # 예비 (재발송 시)
        }
        persona_style = persona_map.get(notification_index, "친근한 친구")
        
        emoji = "🎓" if category == "지식형" else "💭"
        title = f"{emoji} 카프카 {notification_index}차 복습 알림 ({persona_style})"
        
        # 메시지 및 URL 생성
        quiz_url = None
        if category == "지식형":
            # 정보형: 퀴즈 URL 포함
            quiz_url = f"http://localhost:8080/quiz/{schedule_id}/{notification_index}"
            message = f"📝 오늘의 퀴즈가 준비되었습니다!\n\n{notification_index}번째 문제를 풀러 가세요 (클릭하면 자동으로 열립니다)"
        else:
            # 힐링형: [C#], ** 정제 후 표시
            raw_msg = styled_content[:197] + "..." if len(styled_content) > 200 else styled_content
            message = clean_content_for_display(raw_msg)
        
        # 팝업 발송 (클릭 시 자동으로 웹페이지 열림)
        # group_id: macOS에서 같은 group이면 알림이 대체됨 → 고유 ID로 각각 표시
        group_id = f"kafka-{schedule_id}-{notification_index}"
        send_popup_notification(
            title=title,
            message=message,
            timeout=30,  # 30초 표시
            url=quiz_url,  # 정보형일 때만 URL 전달
            group_id=group_id,
        )
        
        # 발송 성공 로그
        db.log_notification(
            schedule_id=schedule_id,
            notification_index=notification_index,
            scheduled_date=target_date,
            is_success=True
        )
        
        print(f"✅ 스케줄 {schedule_id}: {notification_index}차 알림 발송 완료")
        
        # 마지막 알림이면 완료 처리 (test_multi_user + test_multi 모드에서는 유지하여 반복 테스트 가능)
        if notification_index == len(schedule_dates):
            if skip_sent_check:
                print(f"🔄 스케줄 {schedule_id}: 테스트 모드라 상태 유지 (다음 --test-multi 실행 시 재발송 가능)")
            else:
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
