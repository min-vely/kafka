# agent/tools/latest_update.py

import os
from langchain_core.tools import tool
from langchain_upstage import ChatUpstage

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

from agent.prompts.prompts import (
    TAVILY_QUERY_GENERATOR_PROMPT,
    UPDATE_ANALYSIS_PROMPT,
)

# 🔹 이 모듈 전용 LLM (nodes 전역 llm에 의존하지 않게)
llm = ChatUpstage(
    model=os.environ.get("KAFKA_MODEL", "solar-pro2"),
    temperature=float(os.environ.get("KAFKA_TEMPERATURE", "0.2")),
)


@tool
def get_latest_update_analysis(summary_text: str) -> str:
    """
    요약을 기반으로 최신 정보를 웹에서 검색하고
    과거 정보와 현재 상황을 비교 분석한 한 줄 소식을 반환합니다.
    """
    try:
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if not (tavily_key and TavilyClient):
            return "Tavily API Key가 없거나 라이브러리가 설치되지 않았습니다."

        client = TavilyClient(api_key=tavily_key)

        # 1️⃣ 검색어 생성
        query_gen_prompt = TAVILY_QUERY_GENERATOR_PROMPT.format(
            summary_text=summary_text
        )
        search_query_resp = llm.invoke(query_gen_prompt)
        search_query = (search_query_resp.content or "").strip()

        # 2️⃣ Tavily 검색
        response = client.search(
            query=search_query,
            search_depth="advanced",
            max_results=3,
        )
        results = response.get("results", [])

        if not results:
            return "최신 정보를 검색했지만 업데이트된 내용이 없습니다."

        search_results_text = ""
        for res in results:
            search_results_text += (
                f"- 제목: {res['title']}\n"
                f"  내용: {res['content']}\n"
                f"  URL: {res['url']}\n\n"
            )

        # 3️⃣ 분석
        analysis_prompt = UPDATE_ANALYSIS_PROMPT.format(
            summary_text=summary_text,
            search_results=search_results_text,
        )
        analysis_resp = llm.invoke(analysis_prompt)

        return (analysis_resp.content or "").strip()

    except Exception as e:
        return f"웹 서치 및 분석 중 오류 발생: {str(e)}"
