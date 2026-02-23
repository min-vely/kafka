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
│   ├── database.py           # SQLite 데이터베이스 관리 (schedules, url_queue, notifications, retry_schedules, quiz_attempts)
│   ├── rag.py                # RAG 검증 시스템 (FAISS, 근거 부착)
│   ├── graph/                # LangGraph 워크플로우 (StateGraph)
│   ├── nodes/                # 각 처리 단계 노드 (input_url, extract_content, classify, synthesize, verify, judge, improve, quiz, persona, schedule 등)
│   ├── notification/         # 알림 시스템 (winotify/pync/plyer)
│   ├── prompts/              # LLM 프롬프트
│   ├── scheduler/            # APScheduler (매일 오전 8시, 에빙하우스 D+1·4·7·11)
│   │   ├── scheduler_service.py
│   │   └── jobs.py           # process_one_from_queue, send_daily_notifications
│   ├── schemas/              # AgentState 등 데이터 스키마
│   ├── tools/                # Jina Reader, Tavily, 구글 캘린더 Tool
│   └── utils/                # 에빙하우스 날짜 계산, 캐시 등
│
├── web/                       # 웹 퀴즈 시스템
│   ├── app.py                # Flask 앱 (URL 입력·즉시 처리·퀴즈)
│   ├── web_server.py         # 웹 서버 진입점
│   ├── static/               # CSS, JS
│   └── templates/            # HTML 템플릿
│
├── scripts/                   # 유틸 스크립트
│   ├── evaluate_classify_accuracy.py
│   ├── visualize_workflow.py
│   └── seed_multiple_notifications_test.py
│
├── docs/                      # 문서
│   ├── DATABASE_GUIDE.md
│   ├── NOTIFICATION_CLICK_GUIDE.md
│   ├── QUIZ_GUIDE.md
│   ├── SCHEDULER_GUIDE.md
│   ├── URL_QUEUE_GUIDE.md
│   ├── WEB_UI_GUIDE.md
│   ├── WORKFLOW_VISUALIZATION.md
│   └── WINDOWS_NOTIFICATION_FIX.md
│
├── tests/                     # 테스트 파일
│   ├── test_database.py
│   ├── test_popup.py
│   └── fixtures/classify_samples.json
│
└── data/                      # 데이터 파일
    └── *.db                   # SQLite (kafka.db, cache.db)
```

## 🚀 빠른 시작

### 1. 의존성 설치
```bash
pip3 install -r requirements.txt
```

### 2. 환경 변수 설정
`.env` 파일에 API 키 추가:
```env
# 필수
UPSTAGE_API_KEY=your_api_key_here

# 선택 (지식형 보강용)
TAVILY_API_KEY=your_tavily_key

# 선택 (LangSmith 관측용)
LANGSMITH_API_KEY=your_langsmith_key
LANGCHAIN_TRACING_V2=true
LANGSMITH_PROJECT=kafka
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

# 분류 정확도 평가 (fixture 기반)
python3 main.py --evaluate-classify
python3 main.py --evaluate-classify --fixture tests/fixtures/classify_samples.json

# 처리 전 분류 정확도 평가 결과 함께 출력
python3 main.py --url "https://example.com/article" --process-now --show-classify-accuracy
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
- **macOS**: pync (클릭 시 웹 퀴즈 URL 열림)
- **Windows**: winotify
- **기타**: plyer (클릭 불가 fallback)

### 5. 웹 기반 퀴즈 시스템
- URL 무제한 저장 (url_queue), 매일 1개씩 처리
- 5문제 4지선다, 60점 이상 합격
- 오답 시 다음날 재발송 (retry_schedules, 최대 3회)

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

# 2. 여러 개 알림 테스트 (반복 가능)
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
- [URL 대기열 가이드](docs/URL_QUEUE_GUIDE.md)
- [워크플로우 시각화](docs/WORKFLOW_VISUALIZATION.md)
- [웹 UI 사용 가이드](docs/WEB_UI_GUIDE.md)
- [Windows 알림 설정](docs/WINDOWS_NOTIFICATION_FIX.md)

### 워크플로우 시각화
```bash
python3 scripts/visualize_workflow.py
# docs/workflow.mmd 생성 → https://mermaid.live 에 붙여넣어 확인
```

## 🛠️ 기술 스택

- **LLM**: Upstage Solar Pro2 — 콘텐츠 분류, 3줄 요약, 퀴즈·생각유도 질문 생성, Judge, 페르소나 적용
- **임베딩**: Upstage Solar Embedding — RAG용 원문 청크 임베딩
- **오케스트레이션**: LangGraph, LangChain — StateGraph 기반 워크플로우, 노드·분기·루프 설계
- **본문 추출**: Jina Reader (r.jina.ai) — URL → 광고·메뉴 제거된 Markdown 본문 추출
- **웹 검색**: Tavily Search API — 지식형·동적 정보 시 최신 업데이트 검색
- **RAG**: FAISS, rank_bm25 — 벡터 검색, 요약 검증·근거 부착
- **DB**: SQLite — schedules, url_queue, notifications, retry_schedules, quiz_attempts, cache
- **웹**: Flask — 퀴즈 UI, URL 입력·즉시 처리
- **스케줄링**: APScheduler — 에빙하우스 D+1·4·7·11일 알림 예약
- **알림**: winotify (Windows), pync (macOS), plyer — OS별 데스크톱 알림
- **평가·관측**: LangSmith
