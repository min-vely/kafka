# 🎓 Kafka AI - 에빙하우스 기반 복습 알림 서비스

LangGraph 기반으로 구현된 지능형 학습 콘텐츠 처리 및 복습 알림 시스템입니다.

## 📁 프로젝트 구조

```
kafka/
├── main.py                    # 메인 워크플로우 진입점
├── requirements.txt           # Python 의존성
├── .env                       # 환경 변수 (API 키)
├── run.sh                     # 실행 스크립트 (Unix)
├── Makefile                   # 실행 스크립트 (Make)
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

### 3. 콘텐츠 처리
```bash
# 방법 1: Makefile
make main ARGS='--text "AI는 인공지능입니다"'

# 방법 2: run.sh
./run.sh main --text "AI는 인공지능입니다"

# 방법 3: 직접 실행
python3 main.py --text "AI는 인공지능입니다"
```

### 4. 웹 서버 실행 (터미널 1)
```bash
# 방법 1: Makefile
make web ARGS='--port 8080'

# 방법 2: run.sh
./run.sh web --port 8080

# 방법 3: 직접 실행
python3 -m web.web_server --port 8080
```

### 5. 스케줄러 실행 (터미널 2)
```bash
# 방법 1: Makefile (테스트 모드)
make scheduler ARGS='--test'

# 방법 2: run.sh
./run.sh scheduler --test

# 방법 3: 직접 실행
python3 -m agent.scheduler.scheduler_service --test
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
- 1일 1문제 출제
- 자동 채점 및 오답 재발송 (최대 3회)

## 🧪 테스트

### 데이터베이스 테스트
```bash
make test-db
# 또는
./run.sh test-db
```

### 팝업 알림 테스트
```bash
make test-popup
# 또는
./run.sh test-popup
```

## 📚 문서

- [데이터베이스 가이드](docs/DATABASE_GUIDE.md)
- [클릭 가능한 알림 가이드](docs/NOTIFICATION_CLICK_GUIDE.md)
- [퀴즈 시스템 가이드](docs/QUIZ_GUIDE.md)
- [스케줄러 가이드](docs/SCHEDULER_GUIDE.md)

## 🛠️ 기술 스택

- **LLM**: Upstage Solar Pro3
- **프레임워크**: LangGraph, LangChain
- **웹**: Flask
- **DB**: SQLite
- **스케줄러**: APScheduler
- **알림**: pync (macOS), win10toast (Windows)

## 📄 라이선스

MIT License

## 🤝 기여

이슈 및 PR 환영합니다!

---

**Made with ❤️ using LangGraph**
