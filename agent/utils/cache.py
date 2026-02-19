import sqlite3
import json
import hashlib
import os
from datetime import datetime
from typing import Dict, Any, Optional

# 캐시 디렉토리 및 DB 파일 경로 설정
CACHE_DIR = "data/cache"
CACHE_DB_PATH = os.path.join(CACHE_DIR, "cache.db")

class CacheDB:
    def __init__(self):
        # 1. 캐시 디렉토리가 없으면 생성
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR, exist_ok=True)
            
        # 2. 테이블 생성 (파일이 이미 있으면 연결만 수행)
        self._create_table()

    def _get_connection(self):
        return sqlite3.connect(CACHE_DB_PATH, check_same_thread=False)

    def _create_table(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # IF NOT EXISTS를 사용하여 기존 데이터 보존
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    url TEXT,
                    category TEXT,
                    saved_summary TEXT,
                    summary TEXT,
                    quiz TEXT,
                    thought_questions TEXT,
                    augmentation_info TEXT,
                    context TEXT,
                    citations TEXT,
                    input_text TEXT,
                    styled_content TEXT,
                    persona_style TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def get_cache_key(self, url: str = None, text: str = None) -> str:
        """URL 또는 본문의 MD5 해시값을 캐시 키로 사용합니다."""
        key = url if url else text
        if not key:
            return ""
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def save(self, state: Dict[str, Any]) -> bool:
        """AgentState의 주요 결과를 DB에 캐싱합니다."""
        url = state.get("url")
        text = state.get("input_text")
        cache_key = self.get_cache_key(url, text)
        
        if not cache_key:
            return False
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO cache (
                        cache_key, url, category, saved_summary, summary, 
                        quiz, thought_questions, augmentation_info, context, 
                        citations, input_text, styled_content, persona_style, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    cache_key,
                    url,
                    state.get("category"),
                    state.get("saved_summary"),
                    state.get("summary"), # JSON string
                    state.get("quiz"),    # JSON string
                    json.dumps(state.get("thought_questions", []), ensure_ascii=False),
                    state.get("augmentation_info"),
                    state.get("context"),
                    json.dumps(state.get("citations", []), ensure_ascii=False),
                    text,
                    state.get("styled_content"),
                    state.get("persona_style"),
                    datetime.now().isoformat()
                ))
                conn.commit()
            return True
        except Exception as e:
            print(f"⚠️ 캐시 DB 저장 실패: {str(e)}")
            return False

    def load(self, url: str = None, text: str = None) -> Optional[Dict[str, Any]]:
        """URL 또는 본문에 해당하는 캐시가 있으면 불러옵니다."""
        cache_key = self.get_cache_key(url, text)
        if not cache_key:
            return None
        
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM cache WHERE cache_key = ?', (cache_key,))
                row = cursor.fetchone()
                
                if row:
                    data = dict(row)
                    # JSON 문자열 필드들을 다시 객체로 변환
                    try:
                        if data["thought_questions"]:
                            data["thought_questions"] = json.loads(data["thought_questions"])
                        if data["citations"]:
                            data["citations"] = json.loads(data["citations"])
                    except:
                        pass
                    return data
        except Exception as e:
            print(f"⚠️ 캐시 DB 로드 실패: {str(e)}")
            
        return None

# 싱글톤 인스턴스
_cache_db = CacheDB()

def save_cache(state: Dict[str, Any]) -> bool:
    return _cache_db.save(state)

def load_cache(url: str = None, text: str = None) -> Optional[Dict[str, Any]]:
    return _cache_db.load(url, text)