# 📅 카프카 실시간 스케줄러 가이드

에빙하우스 망각 곡선에 따라 지정된 날짜/시간에 자동으로 팝업 알림을 발송하는 스케줄러 시스템입니다.

---

## 🎯 기능

✅ **자동 알림 발송**: 매일 오전 8시에 오늘 발송할 스케줄을 자동으로 조회하여 팝업 발송  
✅ **에빙하우스 주기**: D+1, D+4, D+7, D+11 날짜에 정확히 복습 알림 발송  
✅ **중복 방지**: 이미 발송된 알림은 재발송하지 않음  
✅ **발송 로그**: 모든 발송 내역을 DB에 기록  
✅ **완료 처리**: 마지막 (4차) 알림 발송 후 자동으로 completed 상태로 변경  
✅ **크로스 플랫폼**: macOS, Windows, Linux 모두 지원  

---

## 📦 설치

### 1. APScheduler 설치

```bash
pip3 install apscheduler
```

또는

```bash
pip3 install -r requirements.txt
```

### 2. 파일 구조 확인

```
kafka/
├── agent/
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── scheduler.py       # 스케줄러 메인 클래스
│   │   └── jobs.py             # 스케줄링 작업 함수들
│   ├── database.py             # get_schedules_for_date() 추가됨
│   └── notification/
│       └── popup.py            # 팝업 알림 (기존)
├── scheduler_service.py        # 실행 스크립트
├── SCHEDULER_DESIGN.md         # 설계 문서
└── SCHEDULER_GUIDE.md          # 이 파일
```

---

## 🚀 사용법

### **1. 프로덕션 모드 (매일 오전 8시 자동 실행)**

```bash
python3 scheduler_service.py
```

**동작:**
- 스케줄러가 백그라운드에서 실행됩니다.
- 매일 오전 8시에 자동으로 오늘 발송할 알림을 조회하여 팝업 발송
- Ctrl+C로 종료할 때까지 계속 실행

**출력 예시:**
```
====================================================
🚀 카프카 스케줄러 서비스
====================================================

🚀 프로덕션 모드: 매일 오전 8시에 자동 실행

✅ 스케줄러 시작됨!
📅 다음 실행 예정: 2026-02-13 08:00:00
   작업 이름: 일일 알림 발송 (오전 8시)

🔄 스케줄러 실행 중... (Ctrl+C로 종료)
====================================================
```

---

### **2. 테스트 모드 (즉시 1회 실행)**

```bash
python3 scheduler_service.py --test
```

**동작:**
- 스케줄러를 시작하지 않고 즉시 1회 실행
- 오늘 날짜에 해당하는 스케줄이 있으면 발송
- 테스트/디버깅에 유용

**출력 예시:**
```
====================================================
🚀 카프카 스케줄러 서비스
====================================================

🧪 테스트 모드: 즉시 알림 발송 실행

====================================================
📅 일일 알림 발송 작업 시작: 2026-02-13
====================================================

📬 발송 대상: 2개 스케줄

📤 스케줄 1: 1차 알림 발송 중...
✅ [macOS] 알림 발송 성공!
✅ 스케줄 1: 1차 알림 발송 완료

📤 스케줄 2: 2차 알림 발송 중...
✅ [macOS] 알림 발송 성공!
✅ 스케줄 2: 2차 알림 발송 완료

====================================================
✅ 발송 완료: 2개 성공, 0개 실패
====================================================
```

---

### **3. 디버깅 모드 (지정된 간격마다 실행)**

```bash
# 10초마다 실행
python3 scheduler_service.py --interval 10

# 1분마다 실행
python3 scheduler_service.py --interval 60
```

**동작:**
- 지정된 간격(초)마다 알림 발송 작업 실행
- 빠른 테스트에 유용
- Ctrl+C로 종료할 때까지 계속 실행

---

### **4. 백그라운드 실행 (nohup)**

```bash
# 백그라운드에서 실행
nohup python3 scheduler_service.py > scheduler.log 2>&1 &

# 프로세스 확인
ps aux | grep scheduler_service

# 종료
pkill -f scheduler_service.py
```

---

## 🧪 테스트 시나리오

### **시나리오 1: 스케줄 생성 및 즉시 테스트**

```bash
# 1. 스케줄 생성
python3 main.py --text "AI는 인공지능입니다."

# 출력:
# 📅 에빙하우스 알림 예약 완료:
#   1차 알림: 2026-02-13 오전 8시
#   2차 알림: 2026-02-16 오전 8시
#   ...

# 2. DB 확인
sqlite3 kafka.db "SELECT id, schedule_dates, status FROM schedules;"

# 3. 스케줄러 테스트 (오늘 날짜 스케줄이 있으면 발송)
python3 scheduler_service.py --test
```

---

### **시나리오 2: 특정 날짜로 테스트**

```python
# Python 인터프리터에서 직접 실행
from agent.database import get_db
from agent.scheduler.jobs import send_notification_for_schedule
import json

db = get_db()

# 첫 번째 스케줄 가져오기
schedules = db.get_pending_schedules()
schedule = schedules[0]

# 1차 알림 날짜로 즉시 발송
schedule_dates = json.loads(schedule['schedule_dates'])
send_notification_for_schedule(schedule, schedule_dates[0])
```

---

### **시나리오 3: 주기적 테스트 (10초마다)**

```bash
# 10초마다 체크 (빠른 디버깅)
python3 scheduler_service.py --interval 10

# → 10초마다 오늘 날짜 스케줄을 조회하여 발송
# → 중복 발송은 자동으로 방지됨
```

---

## 📊 모니터링

### **1. 발송 내역 조회**

```bash
# 최근 10개 발송 로그
sqlite3 kafka.db "SELECT * FROM notifications ORDER BY sent_at DESC LIMIT 10;"

# 성공한 알림만
sqlite3 kafka.db "SELECT * FROM notifications WHERE is_success = 1;"

# 실패한 알림만
sqlite3 kafka.db "SELECT * FROM notifications WHERE is_success = 0;"
```

---

### **2. 스케줄 상태 확인**

```bash
# 대기 중인 스케줄
sqlite3 kafka.db "SELECT id, user_id, schedule_dates, status FROM schedules WHERE status='pending';"

# 완료된 스케줄
sqlite3 kafka.db "SELECT id, user_id, schedule_dates, status FROM schedules WHERE status='completed';"
```

---

### **3. 통계 확인**

```python
from agent.database import get_db

db = get_db()
stats = db.get_statistics()

print(f"총 스케줄: {stats['total_schedules']}")
print(f"완료: {stats['completed']}")
print(f"대기 중: {stats['pending']}")
print(f"총 발송 알림: {stats['total_notifications']}")
print(f"성공: {stats['successful_notifications']}")
print(f"실패: {stats['failed_notifications']}")
```

---

## 🔧 고급 사용

### **1. Python 코드에서 직접 사용**

```python
from agent.scheduler import KafkaScheduler

# 스케줄러 생성
scheduler = KafkaScheduler()

# 시작
scheduler.start()

# 상태 확인
status = scheduler.get_status()
print(status)

# 영구 실행
scheduler.run_forever()
```

---

### **2. 시스템 서비스로 등록 (macOS)**

```bash
# 1. plist 파일 생성
cat > ~/Library/LaunchAgents/com.kafka.scheduler.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kafka.scheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/Users/homesul/kafka/scheduler_service.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/homesul/kafka</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/homesul/kafka/scheduler.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/homesul/kafka/scheduler_error.log</string>
</dict>
</plist>
EOF

# 2. 서비스 등록
launchctl load ~/Library/LaunchAgents/com.kafka.scheduler.plist

# 3. 서비스 시작
launchctl start com.kafka.scheduler

# 4. 상태 확인
launchctl list | grep kafka

# 5. 중지
launchctl stop com.kafka.scheduler

# 6. 등록 해제
launchctl unload ~/Library/LaunchAgents/com.kafka.scheduler.plist
```

---

### **3. 시스템 서비스로 등록 (Linux)**

```bash
# 1. systemd 서비스 파일 생성
sudo cat > /etc/systemd/system/kafka-scheduler.service << 'EOF'
[Unit]
Description=Kafka Notification Scheduler
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/kafka
ExecStart=/usr/bin/python3 /path/to/kafka/scheduler_service.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 2. 서비스 활성화
sudo systemctl daemon-reload
sudo systemctl enable kafka-scheduler

# 3. 서비스 시작
sudo systemctl start kafka-scheduler

# 4. 상태 확인
sudo systemctl status kafka-scheduler

# 5. 로그 확인
sudo journalctl -u kafka-scheduler -f
```

---

## ⚠️ 주의사항

### **1. 시간대 설정**
- 서버의 시간대가 한국(KST)으로 설정되어 있는지 확인하세요.
- macOS: `sudo systemsetup -settimezone Asia/Seoul`
- Linux: `sudo timedatectl set-timezone Asia/Seoul`

### **2. 알림 권한**
- macOS: 시스템 환경설정 → 알림 → Python (또는 터미널) 허용
- Windows: 설정 → 시스템 → 알림 및 작업 → Python 허용

### **3. DB 접근**
- SQLite는 동시 쓰기를 지원하지 않으므로, 여러 인스턴스를 동시에 실행하지 마세요.
- `check_same_thread=False` 옵션으로 멀티스레드 안전성 확보

### **4. 장기 실행**
- 메모리 누수 방지를 위해 주기적으로 재시작하거나 모니터링 설정
- 로그 파일이 너무 커지지 않도록 logrotate 설정

---

## 🐛 문제 해결

### **Q: 알림이 발송되지 않아요**

```bash
# 1. 스케줄러 실행 여부 확인
ps aux | grep scheduler_service

# 2. 오늘 발송할 스케줄이 있는지 확인
sqlite3 kafka.db "SELECT * FROM schedules WHERE status='pending' AND schedule_dates LIKE '%$(date +%Y-%m-%d)%';"

# 3. 테스트 모드로 즉시 실행
python3 scheduler_service.py --test

# 4. 알림 권한 확인 (macOS)
# 시스템 환경설정 → 알림 → Python 또는 터미널 허용

# 5. plyer 라이브러리 재설치
pip3 uninstall plyer pyobjc
pip3 install plyer pyobjc
```

---

### **Q: 같은 알림이 두 번 발송됐어요**

```bash
# 발송 로그 확인
sqlite3 kafka.db "SELECT schedule_id, notification_index, COUNT(*) as count 
FROM notifications 
WHERE is_success = 1 
GROUP BY schedule_id, notification_index 
HAVING count > 1;"

# 중복 방지 로직이 있으므로, 스케줄러를 여러 개 실행한 경우일 가능성
# 실행 중인 스케줄러 확인
ps aux | grep scheduler_service
```

---

### **Q: 특정 날짜의 알림을 수동으로 발송하고 싶어요**

```python
from agent.database import get_db
from agent.scheduler.jobs import send_notification_for_schedule
import json

# 원하는 스케줄 ID와 날짜
schedule_id = 1
target_date = "2026-02-16"

db = get_db()
schedule = db.get_schedule_by_id(schedule_id)

if schedule:
    send_notification_for_schedule(schedule, target_date)
else:
    print(f"스케줄 {schedule_id}를 찾을 수 없습니다.")
```

---

## 📈 향후 확장

- [ ] 웹 대시보드 (스케줄 관리 UI)
- [ ] 사용자별 시간 설정 (출근 시간 커스터마이징)
- [ ] 이메일/슬랙/디스코드 알림 채널 추가
- [ ] AI 기반 최적 복습 시간 추천
- [ ] 학습 패턴 분석 및 시각화

---

## 📚 관련 문서

- [SCHEDULER_DESIGN.md](./SCHEDULER_DESIGN.md) - 설계 문서
- [DATABASE_GUIDE.md](./DATABASE_GUIDE.md) - DB 사용 가이드
- [NOTIFICATION_GUIDE.md](./NOTIFICATION_GUIDE.md) - 알림 시스템 가이드

---

**설정 완료!** 이제 스케줄러가 자동으로 알림을 발송합니다! 🎉
