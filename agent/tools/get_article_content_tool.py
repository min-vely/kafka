### utils.py의 get_article_content 함수 이전

from langchain_core.tools import tool
import requests
from agent.utils.utils import is_valid_url

@tool
def get_article_content_tool(url: str) -> str:
    """
    Jina Reader(r.jina.ai)를 사용하여 지정된 URL의 뉴스 기사나 웹 페이지의 제목과 본문을 추출합니다.
    유튜브 링크가 아닌 일반 웹 페이지 URL에 사용하세요.
    """
    if not is_valid_url(url):
        return f"Error: 유효하지 않은 URL 형식입니다: {url}"

    jina_url = f"https://r.jina.ai/{url}"
    try:
        # 타임아웃 10초 설정
        response = requests.get(jina_url, timeout=10)
        response.raise_for_status()
        
        content = response.text
        stripped = content.strip()
        if len(stripped) < 80:
            return "Error: 추출된 본문이 너무 짧습니다. 요약할 수 없는 페이지(로그인 필요, 결제 등)일 수 있습니다."
            
        return content
    except requests.exceptions.Timeout:
        return "Error: 뉴스 기사를 가져오는 중 타임아웃이 발생했습니다. 다시 시도해주세요."
    except Exception as e:
        return f"Error: 뉴스 기사를 가져오는 데 실패했습니다: {str(e)}"
