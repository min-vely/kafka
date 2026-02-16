# 📥 URL 대기열(Queue) 가이드

## 개요

1일 1스크랩 제한을 없애고, **URL 무제한 저장** 후 **매일 1개씩 순차 처리**하는 방식으로 변경되었습니다.

---

## 동작 방식

### 1. URL 저장 (무제한)
```
python main.py --url "https://example.com/article1"
python main.py --url "https://example.com/article2"
python main.py --url "https://example.com/article3"
```
→ 대기열에 3개 URL 누적 저장

### 2. 매일 1개씩 처리
스케줄러가 매일 오전 8시에 실행될 때:
1. 대기열에서 **가장 오래된 URL 1개** 꺼냄 (FIFO)
2. 전체 파이프라인 실행 (분류 → 요약 → 퀴즈 → 스케줄 저장)
3. 에빙하우스 날짜(D+1, D+4, D+7, D+11)에 맞춰 알림 예약

### 3. 알림 발송 제한
- **에빙하우스 겹침 시**: 하루 최대 **4개** (정규 알림)
- **퀴즈 오답 재발송**: +**1개** 추가 (하루 최대 **5개**)
- 이유: 정보 과부하 방지, 사용자 피로도 최소화

---

## 사용법

### URL 큐에 저장 (기본)
```bash
python main.py --url "https://youtube.com/watch?v=xxx"
```
→ 즉시 처리하지 않고 대기열에만 저장

### URL 즉시 처리
```bash
python main.py --url "https://youtube.com/watch?v=xxx" --process-now
```
→ 큐를 거치지 않고 바로 전체 파이프라인 실행

### 텍스트 입력 (즉시 처리)
```bash
python main.py --text "AI는 인공지능입니다"
```
→ 텍스트는 항상 즉시 처리 (큐 없음)

---

## 스케줄러 동작

```bash
python -m agent.scheduler.scheduler_service
# 또는 테스트 모드
python -m agent.scheduler.scheduler_service --test
```

**매일 실행 시 순서:**
1. 대기열에서 URL 1개 꺼내 처리
2. 오늘 날짜에 해당하는 스케줄 최대 4개 발송
3. 오늘 재발송할 퀴즈 오답 최대 1개 발송
4. 총 하루 최대 5개 알림

---

## DB 스키마

### url_queue 테이블
| 컬럼 | 설명 |
|------|------|
| id | 큐 항목 ID |
| user_id | 사용자 ID |
| url | 저장된 URL |
| input_type | 'url' \| 'text' |
| status | 'pending' \| 'processing' \| 'completed' \| 'failed' |
| created_at | 저장 시각 |
| processed_at | 처리 완료 시각 |
| schedule_id | 생성된 스케줄 ID |

---

## 관련 파일

- `agent/database.py`: add_to_url_queue, get_next_from_url_queue
- `agent/scheduler/jobs.py`: process_one_from_queue
- `main.py`: --url 시 큐 저장, --process-now 시 즉시 처리
