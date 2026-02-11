import re
from datetime import datetime, timedelta
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
)

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
