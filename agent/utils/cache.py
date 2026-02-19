import os
import json
import hashlib
from typing import Dict, Any, Optional

CACHE_DIR = "data/cache"

def get_cache_filename(url: str = None, text: str = None) -> str:
    """URL 또는 본문의 MD5 해시값을 파일명으로 사용합니다."""
    key = url if url else text
    if not key:
        return ""
    
    url_hash = hashlib.md5(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{url_hash}.json")

def save_cache(state: Dict[str, Any]) -> bool:
    """AgentState의 주요 결과를 파일로 캐싱합니다."""
    url = state.get("url")
    text = state.get("input_text")
    
    cache_path = get_cache_filename(url, text)
    if not cache_path:
        return False
    
    # 캐시할 핵심 데이터 추출
    cache_data = {
        "url": url,
        "category": state.get("category"),
        "saved_summary": state.get("saved_summary"),
        "summary": state.get("summary"), # RAG 정보 포함된 JSON
        "quiz": state.get("quiz"),
        "thought_questions": state.get("thought_questions"),
        "augmentation_info": state.get("augmentation_info"),
        "context": state.get("context"),
        "citations": state.get("citations"),
        "input_text": text,
        "styled_content": state.get("styled_content"),
        "persona_style": state.get("persona_style"),
    }
    
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"⚠️ 캐시 저장 실패: {str(e)}")
        return False

def load_cache(url: str = None, text: str = None) -> Optional[Dict[str, Any]]:
    """URL 또는 본문에 해당하는 캐시가 있으면 불러옵니다."""
    cache_path = get_cache_filename(url, text)
    if not cache_path or not os.path.exists(cache_path):
        return None
    
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 캐시 로드 실패: {str(e)}")
        return None
