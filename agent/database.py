# agent/database.py
"""
SQLite 데이터베이스 관리

스케줄 정보를 영구 저장하여 프로그램 재시작 후에도 유지합니다.

기능:
- 스케줄 저장 (사용자 ID, 날짜, 콘텐츠)
- 스케줄 조회 (발송 대기 중인 것만)
- 발송 완료 처리
"""

import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import json


class ScheduleDB:
    """
    카프카 알림 스케줄 데이터베이스
    
    이유:
    - 프로그램 종료해도 스케줄 정보 유지
    - 사용자별 알림 관리
    - 발송 이력 추적
    """
    
    def __init__(self, db_path: str = 'data/kafka.db'):
        """
        DB 초기화 및 테이블 생성
        
        Args:
            db_path: DB 파일 경로 (기본: data/kafka.db)
        """
        self.db_path = db_path
        dir_path = os.path.dirname(db_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Dict처럼 접근 가능
        self._create_tables()
    
    def _create_tables(self):
        """테이블 생성 (없을 경우에만)"""
        cursor = self.conn.cursor()
        
        # 스케줄 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                url TEXT,
                summary TEXT,
                category TEXT,
                schedule_dates TEXT NOT NULL,
                styled_content TEXT NOT NULL,
                persona_style TEXT,
                persona_count INTEGER,
                questions TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # 기존 테이블에 questions 컬럼 추가 (ALTER TABLE - 안전하게)
        try:
            cursor.execute("ALTER TABLE schedules ADD COLUMN questions TEXT")
            print("✅ schedules 테이블에 questions 컬럼 추가됨")
        except sqlite3.OperationalError:
            # 이미 존재하면 무시
            pass
        
        # 알림 발송 이력 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER,
                notification_index INTEGER,
                scheduled_date TEXT,
                sent_at TIMESTAMP,
                is_success BOOLEAN,
                error_message TEXT,
                FOREIGN KEY (schedule_id) REFERENCES schedules(id)
            )
        ''')
        
        # 퀴즈 시도 기록 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                notification_index INTEGER NOT NULL,
                user_answers TEXT NOT NULL,
                correct_answers TEXT NOT NULL,
                score INTEGER NOT NULL,
                is_passed BOOLEAN NOT NULL,
                attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (schedule_id) REFERENCES schedules(id)
            )
        ''')
        
        # 오답 재발송 스케줄 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS retry_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                notification_index INTEGER NOT NULL,
                retry_date TEXT NOT NULL,
                retry_count INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (schedule_id) REFERENCES schedules(id)
            )
        ''')
        
        # URL 대기열 테이블 (무제한 저장, 매일 1개씩 처리)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS url_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user',
                url TEXT NOT NULL,
                input_type TEXT DEFAULT 'url',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                schedule_id INTEGER
            )
        ''')
        
        # 기존 url_queue 테이블에 input_type 컬럼 추가 (ALTER TABLE - 안전하게)
        try:
            cursor.execute("ALTER TABLE url_queue ADD COLUMN input_type TEXT DEFAULT 'url'")
            print("✅ url_queue 테이블에 input_type 컬럼 추가됨")
        except sqlite3.OperationalError:
            pass  # 이미 존재하면 무시
        
        self.conn.commit()
        print(f"✅ 데이터베이스 초기화 완료: {self.db_path}")
    
    def save_schedule(
        self,
        user_id: str,
        schedule_dates: List[str],
        styled_content: str,
        persona_style: str,
        persona_count: int,
        url: str = None,
        summary: str = None,
        category: str = "지식형",
        questions: List[dict] = None
    ) -> int:
        """
        새로운 스케줄 저장
        
        Args:
            user_id: 사용자 ID
            schedule_dates: 발송 예정 날짜 리스트 ["2026-02-12", ...]
            styled_content: 페르소나 적용된 메시지
            persona_style: 페르소나 이름
            persona_count: 페르소나 순환 카운터
            url: 원본 URL (선택)
            summary: 3줄 요약 (선택)
            category: 콘텐츠 유형 (지식형/일반형)
            questions: 퀴즈 문제 리스트 (선택) - JSON 형태로 저장
        
        Returns:
            생성된 스케줄 ID
        """
        cursor = self.conn.cursor()
        
        # 날짜 리스트를 JSON으로 변환
        dates_json = json.dumps(schedule_dates)
        
        # 퀴즈 문제를 JSON으로 변환
        questions_json = json.dumps(questions, ensure_ascii=False) if questions else None
        
        cursor.execute('''
            INSERT INTO schedules 
            (user_id, url, summary, category, schedule_dates, 
             styled_content, persona_style, persona_count, questions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, url, summary, category, dates_json, 
              styled_content, persona_style, persona_count, questions_json))
        
        self.conn.commit()
        schedule_id = cursor.lastrowid
        
        print(f"📦 스케줄 저장 완료 (ID: {schedule_id})")
        return schedule_id
    
    def get_pending_schedules(self) -> List[Dict]:
        """
        발송 대기 중인 스케줄 조회
        
        Returns:
            스케줄 정보 리스트
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM schedules 
            WHERE status = 'pending'
            ORDER BY created_at DESC
        ''')
        
        rows = cursor.fetchall()
        
        # Row를 Dict로 변환
        schedules = []
        for row in rows:
            schedule = dict(row)
            # JSON 문자열을 리스트로 변환
            schedule['schedule_dates'] = json.loads(schedule['schedule_dates'])
            schedules.append(schedule)
        
        return schedules
    
    def get_schedules_for_date(self, date: str, limit: int = 4) -> List[Dict]:
        """
        특정 날짜에 발송할 스케줄 조회 (에빙하우스 겹침 시 하루 최대 limit개)
        
        Args:
            date: 날짜 문자열 (YYYY-MM-DD 형식)
            limit: 최대 조회 개수 (기본 4개, 에빙하우스 정규 알림 한도)
        
        Returns:
            해당 날짜에 발송할 pending 스케줄 리스트 (최대 limit개)
        
        이유:
            - 에빙하우스 날짜가 겹쳐도 하루 최대 4개만 발송 (정보 과부하 방지)
            - 재발송은 별도로 1개 추가 허용 (총 5개)
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM schedules 
            WHERE status = 'pending'
            AND schedule_dates LIKE ?
            ORDER BY created_at ASC
            LIMIT ?
        ''', (f'%"{date}"%', limit))
        
        rows = cursor.fetchall()
        
        # Row를 Dict로 변환
        schedules = []
        for row in rows:
            schedule = dict(row)
            # JSON 문자열은 그대로 유지 (jobs.py에서 파싱)
            schedules.append(schedule)
        
        return schedules
    
    def get_schedule_by_id(self, schedule_id: int) -> Optional[Dict]:
        """
        특정 스케줄 조회
        
        Args:
            schedule_id: 스케줄 ID
        
        Returns:
            스케줄 정보 또는 None
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
        row = cursor.fetchone()
        
        if row:
            schedule = dict(row)
            schedule['schedule_dates'] = json.loads(schedule['schedule_dates'])
            return schedule
        return None
    
    def mark_as_completed(self, schedule_id: int):
        """
        스케줄 완료 처리
        
        Args:
            schedule_id: 스케줄 ID
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE schedules 
            SET status = 'completed' 
            WHERE id = ?
        ''', (schedule_id,))
        self.conn.commit()
        print(f"✅ 스케줄 완료 처리: ID {schedule_id}")
    
    def log_notification(
        self,
        schedule_id: int,
        notification_index: int,
        scheduled_date: str,
        is_success: bool,
        error_message: str = None
    ):
        """
        알림 발송 이력 기록
        
        Args:
            schedule_id: 스케줄 ID
            notification_index: 알림 차수 (1, 2, 3, 4)
            scheduled_date: 발송 예정 날짜
            is_success: 성공 여부
            error_message: 에러 메시지 (실패 시)
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO notifications 
            (schedule_id, notification_index, scheduled_date, 
             sent_at, is_success, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (schedule_id, notification_index, scheduled_date,
              datetime.now(), is_success, error_message))
        self.conn.commit()
    
    def get_statistics(self) -> Dict:
        """
        통계 조회
        
        Returns:
            전체 스케줄 수, 대기 중, 완료 등
        """
        cursor = self.conn.cursor()
        
        # 전체 스케줄 수
        cursor.execute('SELECT COUNT(*) FROM schedules')
        total = cursor.fetchone()[0]
        
        # 상태별 카운트
        cursor.execute('''
            SELECT status, COUNT(*) 
            FROM schedules 
            GROUP BY status
        ''')
        status_counts = dict(cursor.fetchall())
        
        # 발송된 알림 수
        cursor.execute('SELECT COUNT(*) FROM notifications WHERE is_success = 1')
        sent = cursor.fetchone()[0]
        
        return {
            'total_schedules': total,
            'pending': status_counts.get('pending', 0),
            'completed': status_counts.get('completed', 0),
            'total_notifications_sent': sent
        }
    
    def save_quiz_attempt(
        self,
        schedule_id: int,
        notification_index: int,
        user_answers: List[str],
        correct_answers: List[str],
        score: int,
        is_passed: bool
    ) -> int:
        """
        퀴즈 시도 기록 저장
        
        Args:
            schedule_id: 스케줄 ID
            notification_index: 알림 차수
            user_answers: 사용자 답안 리스트
            correct_answers: 정답 리스트
            score: 점수 (0-100)
            is_passed: 합격 여부 (60점 이상)
        
        Returns:
            생성된 시도 기록 ID
        """
        cursor = self.conn.cursor()
        
        cursor.execute('''
            INSERT INTO quiz_attempts
            (schedule_id, notification_index, user_answers, correct_answers, score, is_passed)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            schedule_id,
            notification_index,
            json.dumps(user_answers),
            json.dumps(correct_answers),
            score,
            is_passed
        ))
        
        self.conn.commit()
        attempt_id = cursor.lastrowid
        
        print(f"📝 퀴즈 시도 기록 저장 완료 (ID: {attempt_id}, 점수: {score}점)")
        return attempt_id
    
    def get_quiz_attempts(self, schedule_id: int) -> List[Dict]:
        """특정 스케줄의 퀴즈 시도 기록 조회"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM quiz_attempts
            WHERE schedule_id = ?
            ORDER BY attempted_at DESC
        ''', (schedule_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def add_retry_schedule(
        self,
        schedule_id: int,
        notification_index: int,
        retry_date: str,
        retry_count: int = 1
    ) -> int:
        """
        오답 재발송 스케줄 추가
        
        Args:
            schedule_id: 스케줄 ID
            notification_index: 알림 차수
            retry_date: 재발송 날짜 (YYYY-MM-DD)
            retry_count: 재시도 횟수
        
        Returns:
            생성된 재발송 스케줄 ID
        """
        cursor = self.conn.cursor()
        
        cursor.execute('''
            INSERT INTO retry_schedules
            (schedule_id, notification_index, retry_date, retry_count)
            VALUES (?, ?, ?, ?)
        ''', (schedule_id, notification_index, retry_date, retry_count))
        
        self.conn.commit()
        retry_id = cursor.lastrowid
        
        print(f"🔄 재발송 스케줄 추가 완료 (ID: {retry_id}, 날짜: {retry_date})")
        return retry_id
    
    def get_retry_count(self, schedule_id: int, notification_index: int) -> int:
        """특정 알림의 재시도 횟수 조회"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM retry_schedules
            WHERE schedule_id = ? AND notification_index = ?
        ''', (schedule_id, notification_index))
        
        return cursor.fetchone()[0]
    
    def get_retry_schedules_for_date(self, date: str, limit: int = 1) -> List[Dict]:
        """특정 날짜에 재발송할 스케줄 조회 (하루 최대 1개, 퀴즈 오답 예외)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM retry_schedules
            WHERE retry_date = ? AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
        ''', (date, limit))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def mark_retry_as_completed(self, retry_id: int):
        """재발송 스케줄 완료 처리"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE retry_schedules
            SET status = 'completed'
            WHERE id = ?
        ''', (retry_id,))
        self.conn.commit()
        
    def add_to_url_queue(self, url: str, user_id: str = "default_user", input_type: str = "url") -> int:
        """
        URL 대기열에 추가 (무제한 저장)
        
        Args:
            url: 저장할 URL
            user_id: 사용자 ID
            input_type: 'url' | 'text'
        
        Returns:
            큐 항목 ID
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO url_queue (user_id, url, input_type, status)
            VALUES (?, ?, ?, 'pending')
        ''', (user_id, url, input_type))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_next_from_url_queue(self) -> Optional[Dict]:
        """
        대기열에서 가장 오래된 URL 1개 꺼내기 (FIFO)
        
        Returns:
            큐 항목 또는 None
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM url_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def mark_queue_item_processing(self, queue_id: int):
        """큐 항목을 처리 중으로 표시"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE url_queue SET status = 'processing'
            WHERE id = ?
        ''', (queue_id,))
        self.conn.commit()
    
    def mark_queue_item_completed(self, queue_id: int, schedule_id: int):
        """큐 항목 처리 완료"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE url_queue 
            SET status = 'completed', processed_at = ?, schedule_id = ?
            WHERE id = ?
        ''', (datetime.now(), schedule_id, queue_id))
        self.conn.commit()
    
    def mark_queue_item_failed(self, queue_id: int):
        """큐 항목 처리 실패"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE url_queue SET status = 'failed'
            WHERE id = ?
        ''', (queue_id,))
        self.conn.commit()
    
    def get_pending_queue_count(self) -> int:
        """대기 중인 큐 항목 수"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM url_queue WHERE status = 'pending'")
        return cursor.fetchone()[0]
    
    def get_similar_recommendations(self, category: str, limit: int = 3) -> List[Dict]:
        """
        동일한 카테고리의 다른 추천 콘텐츠 조회
        
        Args:
            category: 콘텐츠 유형
            limit: 추천 개수
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT url, summary, persona_style 
            FROM schedules 
            WHERE category = ? AND url IS NOT NULL
            ORDER BY RANDOM() 
            LIMIT ?
        ''', (category, limit))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def close(self):
        """DB 연결 종료"""
        self.conn.close()
        print("🔒 데이터베이스 연결 종료")


# 전역 DB 인스턴스 (싱글톤)
_db_instance = None

def get_db() -> ScheduleDB:
    """
    전역 DB 인스턴스 반환
    
    이유:
    - 여러 곳에서 동일한 DB 연결 사용
    - 연결 중복 방지
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = ScheduleDB()
    return _db_instance
