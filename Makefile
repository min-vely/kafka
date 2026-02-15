# Kafka 프로젝트 실행 스크립트
.PHONY: help main scheduler web test-db test-popup clean

help:
	@echo "Kafka AI 프로젝트 실행 명령어"
	@echo ""
	@echo "사용법:"
	@echo "  make main ARGS='--text \"AI는...\"'  # 메인 워크플로우 실행"
	@echo "  make scheduler ARGS='--test'         # 스케줄러 서비스 실행"
	@echo "  make web ARGS='--port 8080'          # 웹 서버 실행"
	@echo "  make test-db                         # 데이터베이스 테스트"
	@echo "  make test-popup                      # 팝업 알림 테스트"
	@echo "  make clean                           # 임시 파일 정리"
	@echo ""
	@echo "예시:"
	@echo "  make scheduler ARGS='--test'"
	@echo "  make web ARGS='--port 8080'"
	@echo "  make main ARGS='--url https://example.com'"

main:
	python3 main.py $(ARGS)

scheduler:
	python3 -m agent.scheduler.scheduler_service $(ARGS)

web:
	python3 -m web.web_server $(ARGS)

test-db:
	python3 tests/test_database.py

test-popup:
	python3 tests/test_popup.py

clean:
	@echo "🧹 임시 파일 정리 중..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	@echo "✅ 정리 완료!"
