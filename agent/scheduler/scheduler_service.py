#!/usr/bin/env python3
# scheduler_service.py
"""
카프카 스케줄러 서비스 실행 스크립트

사용법:
    # 프로덕션 모드 (매일 오전 8시 자동 실행)
    python3 scheduler_service.py
    
    # 테스트 모드 (즉시 1회 실행)
    python3 scheduler_service.py --test
    
    # 디버깅 모드 (10초마다 실행)
    python3 scheduler_service.py --interval 10
    
    # 데몬 모드 (백그라운드 영구 실행)
    python3 scheduler_service.py --daemon
"""

import argparse
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main():
    parser = argparse.ArgumentParser(
        description="카프카 실시간 스케줄러 서비스",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  프로덕션 모드 (매일 오전 8시):
    $ python3 scheduler_service.py
  
  테스트 모드 (즉시 실행):
    $ python3 scheduler_service.py --test
  
  여러 개 알림 반복 테스트 (seed 후 --test-multi):
    $ python3 scripts/seed_multiple_notifications_test.py
    $ python3 -m agent.scheduler.scheduler_service --test-multi
  
  디버깅 모드 (1분마다):
    $ python3 scheduler_service.py --interval 60
  
  백그라운드 실행:
    $ nohup python3 scheduler_service.py &
        """
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='테스트 모드 (즉시 1회 실행)'
    )

    parser.add_argument(
        '--test-multi',
        action='store_true',
        help='여러 개 알림 테스트 모드 (test_multi_user 스케줄은 발송 이력 무시, 반복 테스트 가능)'
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        metavar='SECONDS',
        help='실행 간격 (초 단위, 디버깅용)'
    )
    
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='데몬 모드 (백그라운드 영구 실행)'
    )
    
    args = parser.parse_args()
    
    # 환경 변수 체크
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv("UPSTAGE_API_KEY"):
        print("❌ 오류: UPSTAGE_API_KEY 환경 변수가 설정되지 않았습니다.")
        print("   .env 파일에 UPSTAGE_API_KEY를 추가하세요.")
        sys.exit(1)
    
    # DB 파일 존재 확인
    if not os.path.exists('data/kafka.db'):
        print("⚠️  경고: data/kafka.db 파일이 없습니다.")
        print("   먼저 main.py를 실행하여 스케줄을 생성하세요.\n")
    
    # 스케줄러 시작
    from agent.scheduler import start_scheduler
    
    print("=" * 60)
    print("🚀 카프카 스케줄러 서비스")
    print("=" * 60)
    print()
    
    try:
        if args.test or args.test_multi:
            # 테스트 모드 (--test-multi: 여러 개 알림 반복 테스트용)
            start_scheduler(test=True, test_multi=args.test_multi)
        elif args.interval:
            # 디버깅 모드
            start_scheduler(daemon=True, interval=args.interval)
        else:
            # 프로덕션 모드
            start_scheduler(daemon=True)
    except KeyboardInterrupt:
        print("\n\n👋 사용자가 중지했습니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
