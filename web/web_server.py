#!/usr/bin/env python3
# web_server.py
"""
카프카 퀴즈 웹 서버 실행 스크립트

사용법:
    python3 web_server.py
    
    또는
    
    python3 web_server.py --port 8080  # 다른 포트 사용
"""

import argparse
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import app


def main():
    parser = argparse.ArgumentParser(
        description="카프카 퀴즈 웹 서버",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  기본 실행 (포트 5000):
    $ python3 web_server.py
  
  다른 포트 사용:
    $ python3 web_server.py --port 8080
  
  디버그 모드 끄기:
    $ python3 web_server.py --no-debug
        """
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='웹 서버 포트 (기본: 5000)'
    )
    
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='웹 서버 호스트 (기본: 0.0.0.0)'
    )
    
    parser.add_argument(
        '--no-debug',
        action='store_true',
        help='디버그 모드 비활성화'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎓 카프카 퀴즈 웹 서버")
    print("=" * 60)
    print()
    print(f"📍 URL: http://localhost:{args.port}")
    print(f"🔗 퀴즈 링크 형식: http://localhost:{args.port}/quiz/<schedule_id>/<notification_index>")
    print()
    print("💡 팁:")
    print("   1. 웹 서버를 먼저 실행하세요")
    print("   2. 스케줄러로 알림을 발송하세요 (python3 -m agent.scheduler.scheduler_service --test)")
    print("   3. 팝업 알림의 URL을 클릭하면 이 서버로 연결됩니다")
    print()
    print("⚠️  주의: Ctrl+C로 종료하세요")
    print()
    
    try:
        app.run(
            debug=not args.no_debug,
            host=args.host,
            port=args.port
        )
    except KeyboardInterrupt:
        print("\n\n👋 웹 서버를 종료합니다")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
