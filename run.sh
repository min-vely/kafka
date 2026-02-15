#!/bin/bash
# Kafka 프로젝트 실행 스크립트

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 도움말 출력
function show_help() {
    echo "🎓 Kafka AI 프로젝트 실행 스크립트"
    echo ""
    echo "사용법:"
    echo "  ./run.sh main [options]        # 메인 워크플로우 실행"
    echo "  ./run.sh scheduler [options]   # 스케줄러 서비스 실행"
    echo "  ./run.sh web [options]         # 웹 서버 실행"
    echo "  ./run.sh test-db               # 데이터베이스 테스트"
    echo "  ./run.sh test-popup            # 팝업 알림 테스트"
    echo ""
    echo "예시:"
    echo "  ./run.sh main --text \"AI는 인공지능입니다\""
    echo "  ./run.sh scheduler --test"
    echo "  ./run.sh web --port 8080"
    echo ""
}

# 명령어 실행
case "$1" in
    main)
        shift
        python3 main.py "$@"
        ;;
    scheduler)
        shift
        python3 -m agent.scheduler.scheduler_service "$@"
        ;;
    web)
        shift
        python3 -m web.web_server "$@"
        ;;
    test-db)
        python3 tests/test_database.py
        ;;
    test-popup)
        python3 tests/test_popup.py
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}❌ 오류: 알 수 없는 명령어 '$1'${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
