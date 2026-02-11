import re
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
