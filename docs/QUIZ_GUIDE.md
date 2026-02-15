# 🎓 퀴즈 답변 입력 시스템 사용 가이드

정보형(지식형) 콘텐츠의 퀴즈를 웹에서 풀고, 오답 시 자동으로 재발송하는 시스템입니다.

---

## 🎯 주요 기능

✅ **웹 기반 퀴즈**: 팝업 알림 클릭 → 웹 페이지에서 퀴즈 풀이  
✅ **자동 채점**: 5문제 4지선다, 즉시 결과 확인  
✅ **오답 재발송**: 60점 미만 시 다음날 자동 재발송 (최대 3회)  
✅ **학습 기록**: 모든 시도 기록 DB 저장  
✅ **반응형 디자인**: PC/모바일 모두 지원  

---

## 📦 설치 및 설정

### **1. Flask 설치**

```bash
pip3 install flask
```

또는

```bash
pip3 install -r requirements.txt
```

### **2. 파일 구조 확인**

```
kafka/
├── web/                          # 웹 서버 모듈
│   ├── app.py                    # Flask 앱
│   ├── templates/
│   │   └── quiz.html             # 퀴즈 페이지
│   └── static/
│       ├── css/style.css         # 스타일
│       └── js/quiz.js            # 클라이언트 로직
├── agent/
│   ├── database.py               # quiz_attempts, retry_schedules 테이블 추가
│   └── scheduler/
│       └── jobs.py               # 팝업 알림에 URL 추가, 재발송 로직
└── web_server.py                 # 웹 서버 실행 스크립트
```

---

## 🚀 사용 방법

### **Step 1: 웹 서버 시작**

```bash
python3 web_server.py
```

**출력:**
```
====================================================
🎓 카프카 퀴즈 웹 서버
====================================================

📍 URL: http://localhost:5000
🔗 퀴즈 링크 형식: http://localhost:5000/quiz/<schedule_id>/<notification_index>

💡 팁:
   1. 웹 서버를 먼저 실행하세요
   2. 스케줄러로 알림을 발송하세요
   3. 팝업 알림의 URL을 클릭하면 이 서버로 연결됩니다
```

**다른 포트 사용:**
```bash
python3 web_server.py --port 8080
```

---

### **Step 2: 콘텐츠 추가 (지식형)**

```bash
python3 main.py --text "AI는 인공지능입니다. 머신러닝은 AI의 하위 분야입니다."
```

또는

```bash
python3 main.py --url "https://youtube.com/watch?v=..."
```

**⚠️ 중요**: 정보형(지식형) 콘텐츠만 퀴즈가 생성됩니다!

---

### **Step 3: 스케줄러로 알림 발송**

```bash
# 테스트 모드 (즉시 발송)
python3 scheduler_service.py --test
```

**팝업 알림 내용:**
```
🎓 카프카 1차 복습 알림 (친근한 친구)

📝 퀴즈가 준비되었습니다!

퀴즈 풀러 가기:
http://localhost:5000/quiz/1/1
```

---

### **Step 4: 웹에서 퀴즈 풀기**

1. 팝업 알림의 URL 클릭
2. 웹 브라우저 자동 열림
3. 5문제 풀이 (4지선다)
4. "제출하기" 버튼 클릭

**채점 결과:**
- ✅ **60점 이상**: 합격! 다음 복습 때 뵙겠습니다
- ❌ **60점 미만**: 불합격, 내일 다시 복습 알림 발송

---

## 🧪 테스트 시나리오

### **시나리오 1: 정상 흐름 (합격)**

```bash
# 1. 웹 서버 시작 (터미널 1)
python3 web_server.py

# 2. 콘텐츠 추가 (터미널 2)
python3 main.py --text "AI는 인공지능입니다..."

# 3. 알림 발송 (터미널 2)
python3 scheduler_service.py --test

# 4. 팝업 알림 클릭
# → http://localhost:5000/quiz/1/1 열림

# 5. 퀴즈 풀이 (5문제)
# → 80점 → 합격 🎉

# 6. DB 확인
sqlite3 kafka.db "SELECT * FROM quiz_attempts;"
# id=1, score=80, is_passed=1
```

---

### **시나리오 2: 오답 재발송**

```bash
# 1~4. 위와 동일

# 5. 퀴즈 풀이 (일부러 틀림)
# → 40점 → 불합격 😅
# "🔄 내일 다시 복습 알림을 보내드리겠습니다!"

# 6. 재발송 스케줄 확인
sqlite3 kafka.db "SELECT * FROM retry_schedules;"
# schedule_id=1, retry_date=2026-02-14, retry_count=1

# 7. 다음날 스케줄러 실행
python3 scheduler_service.py --test
# → 같은 퀴즈 재발송

# 8. 재시도 (2차)
# → 70점 → 합격 ✅
```

---

### **시나리오 3: 최대 재시도 초과**

```bash
# 3회 연속 불합격 시

# 1차 시도: 40점 → 재발송 예약
# 2차 시도: 50점 → 재발송 예약
# 3차 시도: 55점 → 재발송 예약
# 4차 시도: 45점 → "최대 재시도 횟수를 초과했습니다"
```

---

## 📊 DB 스키마

### **quiz_attempts 테이블**

| 필드 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | 기본 키 |
| schedule_id | INTEGER | 스케줄 ID |
| notification_index | INTEGER | 알림 차수 (1, 2, 3, 4) |
| user_answers | TEXT (JSON) | 사용자 답안 ["A", "B", ...] |
| correct_answers | TEXT (JSON) | 정답 ["A", "C", ...] |
| score | INTEGER | 점수 (0-100) |
| is_passed | BOOLEAN | 합격 여부 (60점 기준) |
| attempted_at | TIMESTAMP | 시도 시각 |

### **retry_schedules 테이블**

| 필드 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | 기본 키 |
| schedule_id | INTEGER | 스케줄 ID |
| notification_index | INTEGER | 알림 차수 |
| retry_date | TEXT | 재발송 날짜 (YYYY-MM-DD) |
| retry_count | INTEGER | 재시도 횟수 |
| status | TEXT | 상태 (pending/completed) |
| created_at | TIMESTAMP | 생성 시각 |

---

## 🔍 모니터링

### **퀴즈 시도 기록 조회**

```bash
# 모든 시도 기록
sqlite3 kafka.db "SELECT * FROM quiz_attempts ORDER BY attempted_at DESC;"

# 특정 스케줄의 시도 기록
sqlite3 kafka.db "SELECT * FROM quiz_attempts WHERE schedule_id = 1;"

# 합격/불합격 통계
sqlite3 kafka.db "SELECT is_passed, COUNT(*) FROM quiz_attempts GROUP BY is_passed;"
```

---

### **재발송 스케줄 조회**

```bash
# 대기 중인 재발송
sqlite3 kafka.db "SELECT * FROM retry_schedules WHERE status = 'pending';"

# 특정 날짜 재발송
sqlite3 kafka.db "SELECT * FROM retry_schedules WHERE retry_date = '2026-02-14';"
```

---

## 🎨 웹 페이지 구성

### **퀴즈 페이지** (`/quiz/<schedule_id>/<notification_index>`)

```
┌─────────────────────────────────────┐
│  🎓 카프카 복습 퀴즈                │
│  1차 복습 · 친근한 친구             │
├─────────────────────────────────────┤
│  📝 요약                            │
│  [요약 내용 표시]                   │
├─────────────────────────────────────┤
│  Q1. 질문 내용...                  │
│  ○ A) 선택지 1                      │
│  ○ B) 선택지 2                      │
│  ○ C) 선택지 3                      │
│  ○ D) 선택지 4                      │
├─────────────────────────────────────┤
│  Q2. ...                            │
│  ...                                │
├─────────────────────────────────────┤
│  [제출하기]                         │
└─────────────────────────────────────┘
```

### **결과 페이지** (제출 후)

**합격 시:**
```
┌─────────────────────────────────────┐
│  🎉 합격!                           │
│  80점                               │
│  훌륭합니다! 복습을 잘 하셨네요.    │
├─────────────────────────────────────┤
│  📊 문제별 결과                     │
│  Q1: ✅ 정답                        │
│  Q2: ✅ 정답                        │
│  Q3: ✅ 정답                        │
│  Q4: ✅ 정답                        │
│  Q5: ❌ 오답 (정답: B)              │
└─────────────────────────────────────┘
```

**불합격 시:**
```
┌─────────────────────────────────────┐
│  😅 아쉽네요                        │
│  40점                               │
│  60점 미만이라 불합격입니다.        │
│  🔄 내일 다시 복습 알림을 보내드립니다!│
└─────────────────────────────────────┘
```

---

## ⚙️ 고급 설정

### **재시도 횟수 변경**

`web/app.py`:
```python
if not is_passed:
    retry_count = db.get_retry_count(schedule_id, notification_index)
    
    if retry_count < 3:  # ← 여기서 3을 5로 변경 (최대 5회)
        ...
```

---

### **합격 기준 변경**

`web/app.py`:
```python
is_passed = score >= 60  # ← 60을 80으로 변경 (80점 이상 합격)
```

---

### **웹 포트 변경**

```bash
python3 web_server.py --port 8080
```

그리고 `agent/scheduler/jobs.py`:
```python
quiz_url = f"http://localhost:8080/quiz/{schedule_id}/{notification_index}"
```

---

## 🐛 문제 해결

### **Q: 웹 페이지가 안 열려요**

```bash
# 1. 웹 서버 실행 여부 확인
ps aux | grep web_server

# 2. 웹 서버 재시작
pkill -f web_server
python3 web_server.py

# 3. 포트 충돌 확인
lsof -i :5000
```

---

### **Q: 퀴즈가 표시되지 않아요**

```bash
# 1. 정보형 콘텐츠인지 확인
sqlite3 kafka.db "SELECT id, category FROM schedules WHERE id = 1;"
# → category가 '지식형'이어야 함

# 2. styled_content에 퀴즈 있는지 확인
sqlite3 kafka.db "SELECT styled_content FROM schedules WHERE id = 1;"
```

---

### **Q: 재발송이 안 돼요**

```bash
# 1. retry_schedules 테이블 확인
sqlite3 kafka.db "SELECT * FROM retry_schedules WHERE schedule_id = 1;"

# 2. 재발송 날짜가 오늘인지 확인
# → retry_date = 오늘 날짜

# 3. 스케줄러 로그 확인
python3 scheduler_service.py --test
# → "🔄 재발송: ..." 메시지 확인
```

---

## 📈 향후 확장

- [ ] 문제별 해설 추가
- [ ] 점수 그래프 시각화
- [ ] 학습 통계 대시보드
- [ ] 사용자별 맞춤 난이도 조정
- [ ] 오답 노트 기능
- [ ] 소셜 공유 기능

---

## 📚 관련 문서

- **[QUIZ_SYSTEM_DESIGN.md](./QUIZ_SYSTEM_DESIGN.md)** - 상세 설계 문서
- **[SCHEDULER_GUIDE.md](./SCHEDULER_GUIDE.md)** - 스케줄러 사용 가이드
- **[DATABASE_GUIDE.md](./DATABASE_GUIDE.md)** - DB 구조 및 API

---

**구현 완료!** 정보형 퀴즈 답변 입력 시스템이 완벽하게 작동합니다! 🎉
