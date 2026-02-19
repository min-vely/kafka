# agent/scheduler/scheduler.py
"""
카프카 스케줄러 메인 클래스

APScheduler를 사용하여 지정된 시간에 자동으로 알림을 발송합니다.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import time
import atexit


class KafkaScheduler:
    """
    카프카 실시간 스케줄러
    
    기능:
    - 매일 오전 8시에 자동으로 알림 발송
    - 백그라운드에서 24/7 실행
    - 프로그램 종료 시 안전하게 정리
    
    이유:
    - 에빙하우스 망각 곡선에 따라 정해진 시간에 정확히 복습 알림 필요
    - 사용자가 수동으로 실행하지 않아도 자동으로 알림 발송
    """
    
    def __init__(self, test_mode: bool = False, interval_seconds: int = None, test_multi: bool = False):
        """
        스케줄러 초기화
        
        Args:
            test_mode: 테스트 모드 (즉시 실행)
            interval_seconds: 실행 간격 (초 단위, 디버깅용)
            test_multi: 여러 개 알림 테스트 모드 (test_multi_user 스케줄 발송 이력 무시)
        """
        self.scheduler = BackgroundScheduler()
        self.test_mode = test_mode
        self.test_multi = test_multi
        self.interval_seconds = interval_seconds
        self.is_running = False
        
        # 프로그램 종료 시 스케줄러도 함께 종료
        atexit.register(self.shutdown)
    
    def start(self):
        """
        스케줄러 시작
        
        동작:
        - test_mode: 즉시 1회 실행
        - interval_seconds: 지정된 간격마다 실행 (디버깅용)
        - 기본: 매일 오전 8시 실행 (프로덕션)
        """
        from .jobs import send_daily_notifications
        
        if self.test_mode:
            mode_msg = "여러 개 알림 반복 테스트" if self.test_multi else "즉시 알림 발송"
            print(f"🧪 테스트 모드: {mode_msg}\n")
            send_daily_notifications(test_multi=self.test_multi)
            return
        
        if self.interval_seconds:
            # 디버깅 모드: 지정된 간격마다 실행
            print(f"🔧 디버깅 모드: {self.interval_seconds}초마다 실행\n")
            self.scheduler.add_job(
                send_daily_notifications,
                IntervalTrigger(seconds=self.interval_seconds),
                id='interval_notifications',
                name='주기적 알림 발송 (디버깅)',
                replace_existing=True
            )
        else:
            # 프로덕션 모드: 매일 오전 8시
            print("🚀 프로덕션 모드: 매일 오전 8시에 자동 실행\n")
            self.scheduler.add_job(
                send_daily_notifications,
                CronTrigger(hour=8, minute=0),
                id='daily_notifications',
                name='일일 알림 발송 (오전 8시)',
                replace_existing=True
            )
        
        # 스케줄러 시작
        self.scheduler.start()
        self.is_running = True
        
        print("✅ 스케줄러 시작됨!")
        self._print_next_run_time()
    
    def _print_next_run_time(self):
        """다음 실행 시간 출력"""
        jobs = self.scheduler.get_jobs()
        if jobs:
            for job in jobs:
                next_run = job.next_run_time
                if next_run:
                    print(f"📅 다음 실행 예정: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"   작업 이름: {job.name}\n")
    
    def shutdown(self):
        """스케줄러 종료"""
        if self.is_running:
            print("\n🛑 스케줄러 종료 중...")
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            print("✅ 스케줄러 종료 완료")
    
    def run_forever(self):
        """
        스케줄러를 영원히 실행 (데몬 모드)
        
        동작:
        - 스케줄러를 백그라운드에서 실행
        - Ctrl+C로 종료할 때까지 계속 실행
        
        사용:
        ```
        scheduler = KafkaScheduler()
        scheduler.start()
        scheduler.run_forever()  # 여기서 대기
        ```
        """
        if not self.is_running:
            self.start()
        
        print("🔄 스케줄러 실행 중... (Ctrl+C로 종료)")
        print(f"{'='*60}\n")
        
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            print("\n\n⚠️  종료 신호 감지됨")
            self.shutdown()
    
    def run_once(self):
        """
        즉시 1회 실행 (테스트용)
        
        사용:
        ```
        scheduler = KafkaScheduler()
        scheduler.run_once()
        ```
        """
        from .jobs import send_daily_notifications
        
        mode_msg = "여러 개 알림 반복 테스트" if self.test_multi else "즉시 실행"
        print(f"🧪 {mode_msg} 모드\n")
        send_daily_notifications(test_multi=self.test_multi)
    
    def get_status(self):
        """
        스케줄러 상태 조회
        
        Returns:
            상태 정보 딕셔너리
        """
        jobs = self.scheduler.get_jobs()
        
        return {
            'is_running': self.is_running,
            'job_count': len(jobs),
            'jobs': [
                {
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
                }
                for job in jobs
            ]
        }


# 편의 함수
def start_scheduler(daemon: bool = True, test: bool = False, interval: int = None, test_multi: bool = False):
    """
    스케줄러를 간단하게 시작하는 헬퍼 함수
    
    Args:
        daemon: 데몬 모드 (영구 실행)
        test: 테스트 모드 (즉시 1회 실행)
        interval: 실행 간격 (초, 디버깅용)
        test_multi: 여러 개 알림 테스트 (test_multi_user 스케줄 발송 이력 무시)
    
    Example:
        # 프로덕션 모드
        start_scheduler(daemon=True)
        
        # 테스트 모드
        start_scheduler(test=True)
        
        # 여러 개 알림 반복 테스트
        start_scheduler(test=True, test_multi=True)
        
        # 디버깅 모드 (1분마다)
        start_scheduler(daemon=True, interval=60)
    """
    scheduler = KafkaScheduler(
        test_mode=test,
        interval_seconds=interval,
        test_multi=test_multi
    )
    
    if test:
        scheduler.run_once()
    elif daemon:
        scheduler.start()
        scheduler.run_forever()
    else:
        scheduler.start()
        return scheduler


if __name__ == "__main__":
    # 직접 실행 시 테스트 모드
    print("=" * 60)
    print("카프카 스케줄러 테스트")
    print("=" * 60)
    print()
    
    start_scheduler(test=True)
