### utils.py의 get_article_content 함수 이전
#텍스트 정제 로직 위한 (re 모듈 사용)
import re
from langchain_core.tools import tool
import requests
from agent.utils.utils import is_valid_url, transform_naver_blog_url


@tool
def get_article_content_tool(url: str) -> str:
    """
    Jina Reader(r.jina.ai)를 사용하여 지정된 URL의 뉴스 기사나 웹 페이지의 제목과 본문을 추출합니다.
    유튜브 링크가 아닌 일반 웹 페이지 URL에 사용하세요.
    """
    # 1. 네이버 블로그라면 주소 변환부터 실행
    url = transform_naver_blog_url(url)

    if not is_valid_url(url):
        return f"Error: 유효하지 않은 URL 형식입니다: {url}"

    jina_url = f"https://r.jina.ai/{url}"

    try:
        # 타임아웃 10초 설정
        response = requests.get(jina_url, timeout=10)
        response.raise_for_status()

        raw_content = response.text

        # 2. 텍스트 정제 로직 (re 모듈 사용)
        if raw_content:
            # 이미지 태그 제거
            content = re.sub(r'!\[.*?\]\(.*?\)', '', raw_content)
            # 링크 형식 정리 ([텍스트](URL) -> 텍스트)
            content = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', content)
            # 마크다운 특수기호 및 시스템 경고 문구 제거
            content = re.sub(r'(?i)Warning:.*?(\n|$)', '', content)
            content = re.sub(r'[#*`\-]', '', content)
            # 연속된 공백 및 줄바꿈 정리
            content = re.sub(r'\n\s*\n', '\n', content).strip()
        else:
            content = ""

        if len(content) < 80:
            return "Error: 추출된 본문이 너무 짧습니다. 요약할 수 없는 페이지(로그인 필요, 결제 등)일 수 있습니다."

        return content

    except requests.exceptions.Timeout:
        return "Error: 뉴스 기사를 가져오는 중 타임아웃이 발생했습니다. 다시 시도해주세요."
    except Exception as e:
        return f"Error: 뉴스 기사를 가져오는 데 실패했습니다: {str(e)}"