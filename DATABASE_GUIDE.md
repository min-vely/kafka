# 🗄️ 카프카 데이터베이스 가이드

## 개요

SQLite를 사용하여 알림 스케줄을 영구 저장하는 시스템입니다.

---

## 🎯 **핵심 기능**

### 1. 스케줄 영구 저장
- 프로그램 종료 후에도 데이터 유지
- 사용자별 알림 관리
- 발송 이력 추적

### 2. 통계 및 모니터링
- 전체 스케줄 수 조회
- 대기/완료 상태 확인
- 발송 성공률 추적

---

## 📂 **테이블 구조**

### `schedules` 테이블 (스케줄 정보)

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `id` | INTEGER | 자동 증가 PK |
| `user_id` | TEXT | 사용자 ID |
| `url` | TEXT | 원본 URL |
| `summary` | TEXT | 3줄 요약 |
| `category` | TEXT | 지식형/일반형 |
| `schedule_dates` | TEXT | JSON 배열 ["2026-02-12", ...] |
| `styled_content` | TEXT | 페르소나 적용된 메시지 |
| `persona_style` | TEXT | 페르소나 이름 |
| `persona_count` | INTEGER | 페르소나 순환 카운터 |
| `created_at` | TIMESTAMP | 생성 일시 |
| `status` | TEXT | pending/completed |

### `notifications` 테이블 (발송 이력)

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `id` | INTEGER | 자동 증가 PK |
| `schedule_id` | INTEGER | 스케줄 FK |
| `notification_index` | INTEGER | 알림 차수 (1-4) |
| `scheduled_date` | TEXT | 발송 예정 날짜 |
| `sent_at` | TIMESTAMP | 실제 발송 시간 |
| `is_success` | BOOLEAN | 성공 여부 |
| `error_message` | TEXT | 에러 메시지 |

---

## 🚀 **사용 방법**

### 1. 기본 사용

```python
from agent.database import get_db

# DB 인스턴스 가져오기
db = get_db()

# 스케줄 저장
schedule_id = db.save_schedule(
    user_id="jc",
    schedule_dates=["2026-02-12", "2026-02-15", "2026-02-18", "2026-02-22"],
    styled_content="야! 어제 배운 내용 기억나?",
    persona_style="친근한 친구",
    persona_count=0,
    category="지식형"
)

# 대기 중인 스케줄 조회
pending = db.get_pending_schedules()
print(f"대기 중: {len(pending)}개")

# 특정 스케줄 조회
schedule = db.get_schedule_by_id(schedule_id)
print(schedule['styled_content'])

# 완료 처리
db.mark_as_completed(schedule_id)

# 통계 조회
stats = db.get_statistics()
print(f"전체: {stats['total_schedules']}개")
```

---

## 🧪 **테스트**

### 데이터베이스 기능 테스트

```bash
python3 test_database.py
```

**예상 결과:**
```
🧪 데이터베이스 기본 기능 테스트
✅ 저장 성공! Schedule ID: 1
✅ 대기 중인 스케줄: 1개
✅ 조회 성공!
✅ 발송 이력 기록 완료
✅ 통계:
   - 전체 스케줄: 1개
   - 대기 중: 0개
   - 완료: 1개
✅ 모든 테스트 통과!
```

---

## 📊 **DB 직접 조회**

### SQLite 명령어로 확인

```bash
# DB 열기
sqlite3 kafka.db

# 테이블 목록
.tables

# 스케줄 조회
SELECT id, user_id, persona_style, status, created_at 
FROM schedules;

# 발송 이력 조회
SELECT * FROM notifications;

# 통계
SELECT status, COUNT(*) FROM schedules GROUP BY status;

# 종료
.exit
```

---

## 🔧 **schedule_node() 연동**

### 자동 DB 저장

`agent/nodes/nodes.py`의 `schedule_node()`가 자동으로 DB에 저장합니다.

```python
def schedule_node(state):
    # ... 날짜 계산 ...
    
    # 🆕 자동으로 DB에 저장됨!
    from agent.database import get_db
    db = get_db()
    schedule_id = db.save_schedule(...)
    
    return state
```

**실행:**
```bash
python3 main.py --text "AI는 인공지능입니다..."
```

**결과:**
- 터미널: `💾 데이터베이스 저장 완료 (Schedule ID: 1)`
- 파일: `kafka.db` 생성됨
- 내용: 스케줄 정보 영구 저장

---

## 📈 **향후 확장**

### Phase 1: 사용자 관리 (현재)
```sql
-- 간단한 user_id 문자열
user_id = "jc"
```

### Phase 2: 사용자 테이블 추가
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    email TEXT,
    created_at TIMESTAMP
);
```

### Phase 3: 퀴즈 정답률 추적
```sql
CREATE TABLE quiz_answers (
    id INTEGER PRIMARY KEY,
    notification_id INTEGER,
    user_answer TEXT,
    is_correct BOOLEAN,
    answered_at TIMESTAMP
);
```

---

## 🔍 **트러블슈팅**

### 문제 1: "database is locked"

**원인:** 동시에 여러 프로세스가 DB 접근

**해결:**
```python
# database.py에서 이미 처리됨
sqlite3.connect(db_path, check_same_thread=False)
```

### 문제 2: DB 파일이 너무 커짐

**해결:**
```bash
# 완료된 스케줄 정리
sqlite3 kafka.db "DELETE FROM schedules WHERE status='completed' AND created_at < date('now', '-30 days');"

# DB 최적화
sqlite3 kafka.db "VACUUM;"
```

### 문제 3: JSON 파싱 에러

**원인:** `schedule_dates` 필드 형식 오류

**확인:**
```python
import json
dates = json.loads(schedule['schedule_dates'])
print(dates)  # ['2026-02-12', ...]
```

---

## 📝 **코드 변경 사항**

### 추가된 파일
1. `agent/database.py` - DB 클래스 (약 250줄)
2. `test_database.py` - 테스트 스크립트 (약 150줄)
3. `DATABASE_GUIDE.md` - 이 문서

### 수정된 파일
1. `agent/nodes/nodes.py` - `schedule_node()`에 DB 저장 추가 (약 15줄)

---

## 💡 **실전 예시**

### 시나리오 1: 스케줄 확인

```python
from agent.database import get_db

db = get_db()
pending = db.get_pending_schedules()

for schedule in pending:
    print(f"사용자: {schedule['user_id']}")
    print(f"날짜: {schedule['schedule_dates']}")
    print(f"페르소나: {schedule['persona_style']}")
    print("---")
```

### 시나리오 2: 발송 시뮬레이션

```python
# 대기 중인 스케줄 가져오기
pending = db.get_pending_schedules()

for schedule in pending:
    schedule_id = schedule['id']
    dates = schedule['schedule_dates']
    
    # 각 날짜별로 알림 발송 (시뮬레이션)
    for i, date in enumerate(dates, 1):
        print(f"{date} 알림 발송: {schedule['styled_content'][:50]}...")
        
        # 발송 이력 기록
        db.log_notification(
            schedule_id=schedule_id,
            notification_index=i,
            scheduled_date=date,
            is_success=True
        )
    
    # 모두 발송 완료
    db.mark_as_completed(schedule_id)
```

---

## 🎯 **장점**

1. **영구 저장** - 프로그램 종료해도 데이터 유지
2. **간단함** - Python 내장, 별도 서버 불필요
3. **빠름** - 로컬 파일 기반
4. **확장 가능** - 필요 시 PostgreSQL로 전환 쉬움

---

## 📚 **참고 자료**

- SQLite 공식 문서: https://sqlite.org/
- Python sqlite3: https://docs.python.org/3/library/sqlite3.html

---

**작성일:** 2026-02-12  
**작성자:** JC (feature/jc)
