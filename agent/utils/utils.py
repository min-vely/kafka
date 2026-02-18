import re
import json
import requests
from urllib.parse import urlparse
from datetime import datetime, timedelta
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
)

def is_valid_url(url: str) -> bool:
    """
    URL이 유효한 형식(http/https 포함)인지 확인합니다.
    """
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False

def is_youtube_url(url: str) -> bool:
    """
    URL이 유튜브 링크인지 확인합니다.
    """
    patterns = [
        r"youtu\.be/",
        r"youtube\.com/watch\?v=",
        r"youtube\.com/shorts/"
    ]
    return any(re.search(pattern, url) for pattern in patterns)

def extract_youtube_video_id(url: str) -> str:
    """
    유튜브 URL에서 video_id(11자리)를 추출한다.
    지원 형식:
    - https://youtu.be/{id}
    - https://www.youtube.com/watch?v={id}
    - https://www.youtube.com/shorts/{id}
    """
    patterns = [
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})"
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError("Invalid YouTube URL. Only valid YouTube video links are allowed.")

def get_youtube_transcript(video_id: str) -> str:
    """
    유튜브 video_id로부터 자막을 가져와 하나의 텍스트로 반환
    """
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=["ko", "en"])
    except TranscriptsDisabled:
        raise ValueError("Transcripts are disabled for this video.")
    except NoTranscriptFound:
        raise ValueError("No transcript found for this video.")
    except Exception as e:
        raise ValueError(f"Transcript extraction failed: {str(e)}")

    full_text = " ".join([item.text for item in transcript])
    return full_text

def get_article_content(url: str) -> str:
    """
    Jina Reader(r.jina.ai)를 사용하여 뉴스 기사 제목과 본문을 추출합니다.
    """
    if not is_valid_url(url):
        raise ValueError(f"유효하지 않은 URL 형식입니다: {url}")

    jina_url = f"https://r.jina.ai/{url}"
    try:
        # 타임아웃 10초 설정
        response = requests.get(jina_url, timeout=10)
        response.raise_for_status()
        
        content = response.text
        stripped = content.strip()
        if len(stripped) < 80:
            raise ValueError(
                "추출된 본문이 너무 짧습니다. 요약할 수 없는 페이지(로그인 필요, 결제 등)일 수 있습니다."
            )
        return content
    except requests.exceptions.Timeout:
        raise ValueError("뉴스 기사를 가져오는 중 타임아웃이 발생했습니다. 다시 시도해주세요.")
    except Exception as e:
        raise ValueError(f"뉴스 기사를 가져오는 데 실패했습니다: {str(e)}")

# ============================================================
# 🆕 에빙하우스 망각 곡선 날짜 계산
# ============================================================

def calculate_ebbinghaus_dates(base_date: datetime = None) -> List[str]:
    """
    에빙하우스 망각 곡선에 따른 복습 날짜를 계산합니다.
    
    Args:
        base_date: 기준 날짜 (기본값: 오늘)
    
    Returns:
        D+1, D+4, D+7, D+11 날짜 리스트 (형식: YYYY-MM-DD)
    
    예시:
        기준일이 2026-02-11이면
        → ["2026-02-12", "2026-02-15", "2026-02-18", "2026-02-22"]
    
    이유:
        에빙하우스 망각 곡선 이론에 따르면, 
        학습 후 1일, 4일, 7일, 11일에 복습하면 
        정보를 장기 기억으로 전환하는 데 가장 효과적입니다.
    """
    if base_date is None:
        base_date = datetime.now()
    
    intervals = [1, 4, 7, 11]  # 에빙하우스 주기
    dates = []
    
    for interval in intervals:
        target_date = base_date + timedelta(days=interval)
        dates.append(target_date.strftime("%Y-%m-%d"))
    
    return dates


def validate_schedule_dates(dates: List[str]) -> tuple:
    """
    schedule_dates의 YYYY-MM-DD 형식 및 유효한 날짜인지 검증합니다.
    
    Args:
        dates: 검증할 날짜 문자열 리스트 (예: ["2026-02-12", "2026-02-15"])
    
    Returns:
        (is_valid: bool, validated_dates: List[str], error_message: Optional[str])
        - is_valid: 모든 날짜가 유효하면 True
        - validated_dates: 유효한 날짜만 필터링된 리스트 (또는 원본)
        - error_message: 유효하지 않을 때 오류 설명
    """
    if not dates or not isinstance(dates, list):
        return False, [], "schedule_dates가 비어있거나 리스트가 아닙니다."
    
    validated = []
    for i, d in enumerate(dates):
        if not isinstance(d, str):
            return False, [], f"날짜[{i}]가 문자열이 아닙니다: {type(d)}"
        s = d.strip()
        if len(s) != 10 or s[4] != "-" or s[7] != "-":
            return False, [], f"날짜[{i}] 형식 오류 (YYYY-MM-DD 필요): '{d}'"
        try:
            datetime.strptime(s, "%Y-%m-%d")
            validated.append(s)
        except ValueError:
            return False, [], f"날짜[{i}] 유효하지 않은 날짜: '{d}'"
    
    return True, validated, None


def extract_json(text: str) -> dict:
    """
    텍스트에서 JSON 블록을 찾아 파싱합니다.
    마크다운 태그(```json)나 서문/결문이 섞여 있어도 최대한 추출합니다.
    """
    if not text:
        return {}
        
    # 1. 마크다운 코드 블록 제거 (```json ... ```)
    clean_text = re.sub(r"```json\s*(.*?)\s*```", r"\1", text, flags=re.DOTALL)
    clean_text = re.sub(r"```\s*(.*?)\s*```", r"\1", clean_text, flags=re.DOTALL)
    
    # 2. 가장 바깥쪽 { } 찾기
    match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
            
    # 3. 정규표현식 실패 시 최후의 수단: 직접 { } 인덱스 찾기
    try:
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1:
            return json.loads(text[start_idx : end_idx + 1])
    except:
        pass
        
    return {}
