# 🎓 Kafka AI - 에빙하우스 기반 복습 알림 서비스

LangGraph 기반으로 구현된 지능형 학습 콘텐츠 처리 및 복습 알림 시스템입니다.

## 📁 프로젝트 구조

```
kafka/
├── main.py                    # 메인 워크플로우 진입점
├── requirements.txt           # Python 의존성
├── .env                       # 환경 변수 (API 키)
│
├── agent/                     # 핵심 AI 에이전트
│   ├── database.py           # SQLite 데이터베이스 관리
│   ├── rag.py                # RAG 검증 시스템
│   ├── graph/                # LangGraph 워크플로우
│   ├── nodes/                # 각 처리 단계 노드
│   ├── notification/         # 알림 시스템
│   ├── prompts/              # LLM 프롬프트
│   ├── scheduler/            # 실시간 스케줄러
│   │   └── scheduler_service.py  # 스케줄러 진입점
│   ├── schemas/              # 데이터 스키마
│   └── utils/                # 유틸리티 함수
│
├── web/                       # 웹 퀴즈 시스템
│   ├── app.py                # Flask 앱
│   ├── web_server.py         # 웹 서버 진입점
│   ├── static/               # CSS, JS
│   └── templates/            # HTML 템플릿
│
├── docs/                      # 문서
│   ├── DATABASE_GUIDE.md
│   ├── NOTIFICATION_CLICK_GUIDE.md
│   ├── QUIZ_GUIDE.md
│   └── SCHEDULER_GUIDE.md
│
├── tests/                     # 테스트 파일
│   ├── test_database.py
│   ├── test_popup.py
│   └── article.txt
│
└── data/                      # 데이터 파일
    └── *.db                   # SQLite 데이터베이스
```

## 🚀 빠른 시작

### 1. 의존성 설치
```bash
pip3 install -r requirements.txt
```

### 2. 환경 변수 설정
`.env` 파일에 API 키 추가:
```env
UPSTAGE_API_KEY=your_api_key_here
```

### 3. 실행 (웹 UI 또는 CLI)

**🖥️ 웹 UI 모드 (권장)** – URL 입력부터 퀴즈까지 브라우저에서 처리
```bash
python3 main.py
```
→ http://localhost:8080 에서 URL 입력, 즉시 처리, 퀴즈 풀기

**⌨️ CLI 모드** – 터미널에서 콘텐츠 처리
```bash
# 텍스트 직접 입력 (즉시 처리)
python3 main.py --text "AI는 인공지능입니다. 머신러닝은 AI의 하위 분야입니다."

# URL 저장 (대기열에 무제한 누적, 매일 1개씩 스케줄러가 처리)
python3 main.py --url "https://example.com/article"

# URL 즉시 처리 (큐 거치지 않고 바로 처리)
python3 main.py --url "https://example.com/article" --process-now
```

### 4. 웹 서버 직접 실행 (터미널 1)
```bash
# 기본 포트 (5000)
python3 -m web.web_server

# 8080 포트 사용 (macOS AirPlay 충돌 회피 권장)
python3 -m web.web_server --port 8080

# 디버그 모드 끄기
python3 -m web.web_server --port 8080 --no-debug
```

### 5. 스케줄러 실행 (터미널 2)
```bash
# 테스트 모드 (즉시 1회 실행)
python3 -m agent.scheduler.scheduler_service --test

# 프로덕션 모드 (매일 오전 8시 자동 실행)
python3 -m agent.scheduler.scheduler_service

# 디버깅 모드 (10초마다 실행)
python3 -m agent.scheduler.scheduler_service --interval 10
```

## 📋 주요 기능

### 1. 콘텐츠 자동 분류
- **지식형**: 퀴즈 생성, 복습 알림
- **힐링형**: 생각 유도 질문, 마음챙김 알림

### 2. 에빙하우스 망각 곡선 기반 스케줄링
- D+1, D+4, D+7, D+11 주기로 자동 알림

### 3. 10가지 페르소나 스타일
- 친근한 친구, 다정한 선배, 엄격한 교수, 유머러스한 코치, 밈 마스터 등

### 4. 클릭 가능한 알림
- **macOS**: pync 라이브러리
- **Windows**: win10toast 라이브러리
- 알림 클릭 시 자동으로 웹 퀴즈 페이지 열림

### 5. 웹 기반 퀴즈 시스템
- URL 무제한 저장, 매일 1개씩 처리
- 자동 채점 및 오답 재발송 (최대 3회)

## 🧪 테스트

### 데이터베이스 테스트
```bash
python3 tests/test_database.py
```

### 팝업 알림 테스트
```bash
python3 tests/test_popup.py
```

### classify 정확도 평가
```bash
python3 scripts/evaluate_classify_accuracy.py
# --fixture tests/fixtures/classify_samples.json (기본값)
```

### 여러 개 알림 테스트 (가상 데이터)
```bash
# 1. 오늘 날짜에 해당하는 스케줄 3개 삽입
python3 scripts/seed_multiple_notifications_test.py

# 2. 스케줄러 테스트 실행 → 알림 3개 연달아 표시
python3 -m agent.scheduler.scheduler_service --test

# 2-1. 여러 개 알림 테스트 (반복 가능)
python3 -m agent.scheduler.scheduler_service --test-multi
# → 알림 3개 연달아 표시, 여러 번 실행해도 매번 재발송

# 일반 테스트 (한 번 보낸 알림은 스킵)

python3 -m agent.scheduler.scheduler_service --test
```

## 📚 문서

- [데이터베이스 가이드](docs/DATABASE_GUIDE.md)
- [클릭 가능한 알림 가이드](docs/NOTIFICATION_CLICK_GUIDE.md)
- [퀴즈 시스템 가이드](docs/QUIZ_GUIDE.md)
- [스케줄러 가이드](docs/SCHEDULER_GUIDE.md)
- [워크플로우 시각화](docs/WORKFLOW_VISUALIZATION.md)
- [웹 UI 사용 가이드](docs/WEB_UI_GUIDE.md)

### 워크플로우 시각화
```bash
python3 scripts/visualize_workflow.py
# docs/workflow.mmd 생성 → https://mermaid.live 에 붙여넣어 확인
```

## 🛠️ 기술 스택

- **LLM**: Upstage Solar Pro3
- **프레임워크**: LangGraph, LangChain
- **웹**: Flask
- **DB**: SQLite
- **스케줄러**: APScheduler
- **알림**: pync (macOS), win10toast (Windows)

