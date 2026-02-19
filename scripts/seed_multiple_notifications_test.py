#!/usr/bin/env python3
"""
여러 개 알림 테스트용 가상 스케줄 데이터 삽입

오늘 날짜에 해당하는 스케줄을 3개 추가하여,
스케줄러 --test 실행 시 알림이 여러 개 연달아 뜨는 상황을 시뮬레이션합니다.

사용법:
    python3 scripts/seed_multiple_notifications_test.py

실행 후:
    python3 -m agent.scheduler.scheduler_service --test
"""

import os
import sys
from datetime import datetime, timedelta

# 프로젝트 루트
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

os.makedirs("data", exist_ok=True)

# .env 로드
from dotenv import load_dotenv
load_dotenv()


def main():
    from agent.database import get_db

    today = datetime.now().strftime("%Y-%m-%d")
    base = datetime.now()
    # 오늘이 첫 알림 날짜가 되도록 (D+0, D+3, D+6, D+10)
    schedule_dates = [
        (base + timedelta(days=d)).strftime("%Y-%m-%d")
        for d in [0, 3, 6, 10]
    ]

    db = get_db()

    samples = [
        {
            "styled_content": "야! 어제 배운 AI 내용 기억나? 딥러닝이 핵심이었잖아 ㅎㅎ",
            "persona_style": "친근한 친구",
            "summary": "AI는 인공지능입니다. 머신러닝은 AI의 하위 분야입니다.",
            "url": "https://example.com/ai-article",
        },
        {
            "styled_content": "오늘 복습할 거 리마인드해줄게! 에빙하우스 망각 곡선 중요하다고 했잖아.",
            "persona_style": "다정한 선배",
            "summary": "에빙하우스 망각 곡선. D+1, D+4, D+7, D+11 주기 복습.",
            "url": "https://example.com/ebbinghaus",
        },
        {
            "styled_content": "복습 시간이다! 퀴즈 풀어보자 ㅋㅋ",
            "persona_style": "유머러스한 코치",
            "summary": "파이썬 기초. 변수, 함수, 클래스 개념.",
            "url": "https://example.com/python",
        },
    ]

    print("=" * 60)
    print("📦 여러 개 알림 테스트용 가상 스케줄 삽입")
    print("=" * 60)
    print(f"오늘 날짜: {today}")
    print(f"schedule_dates: {schedule_dates}")
    print(f"삽입할 스케줄: {len(samples)}개\n")

    for i, s in enumerate(samples, 1):
        schedule_id = db.save_schedule(
            user_id="test_multi_user",
            schedule_dates=schedule_dates,
            styled_content=s["styled_content"],
            persona_style=s["persona_style"],
            persona_count=0,
            url=s["url"],
            summary=s["summary"],
            category="지식형",
            questions=[
                {"question": "테스트 문제 1", "options": ["A", "B", "C", "D"], "answer": "A"},
            ],
        )
        print(f"  ✅ 스케줄 {i} 추가 (ID: {schedule_id})")

    print("\n" + "-" * 60)
    print("✅ 가상 데이터 삽입 완료!")
    print("-" * 60)
    print("\n📌 다음 명령으로 여러 개 알림 테스트:")
    print("   python3 -m agent.scheduler.scheduler_service --test")
    print("\n   → 알림이 3개 연달아 나타납니다.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
