# agent/database.py
"""
SQLite 데이터베이스 관리

스케줄 정보를 영구 저장하여 프로그램 재시작 후에도 유지합니다.

기능:
- 스케줄 저장 (사용자 ID, 날짜, 콘텐츠)
- 스케줄 조회 (발송 대기 중인 것만)
- 발송 완료 처리
"""

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
    
    def __init__(self, db_path: str = 'kafka.db'):
        """
        DB 초기화 및 테이블 생성
        
        Args:
            db_path: DB 파일 경로 (기본: kafka.db)
        """
        self.db_path = db_path
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
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
        category: str = "지식형"
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
        
        Returns:
            생성된 스케줄 ID
        """
        cursor = self.conn.cursor()
        
        # 날짜 리스트를 JSON으로 변환
        dates_json = json.dumps(schedule_dates)
        
        cursor.execute('''
            INSERT INTO schedules 
            (user_id, url, summary, category, schedule_dates, 
             styled_content, persona_style, persona_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, url, summary, category, dates_json, 
              styled_content, persona_style, persona_count))
        
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
    
    def get_schedules_for_date(self, date: str) -> List[Dict]:
        """
        특정 날짜에 발송할 스케줄 조회
        
        Args:
            date: 날짜 문자열 (YYYY-MM-DD 형식, 예: "2026-02-13")
        
        Returns:
            해당 날짜가 schedule_dates에 포함된 pending 스케줄 리스트
        
        사용 예:
            schedules = db.get_schedules_for_date("2026-02-13")
            # 2026-02-13에 발송해야 하는 스케줄들 반환
        
        이유:
            - 스케줄러가 매일 오전 8시에 실행될 때 오늘 발송할 스케줄만 조회
            - schedule_dates는 JSON 배열로 저장되므로 LIKE 검색 사용
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM schedules 
            WHERE status = 'pending'
            AND schedule_dates LIKE ?
            ORDER BY created_at DESC
        ''', (f'%"{date}"%',))
        
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
