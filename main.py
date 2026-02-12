import os
import argparse
import json

from agent.graph import build_graph
from agent.utils import is_youtube_url, extract_youtube_video_id, get_youtube_transcript, get_article_content


def pretty_print(result: dict):
    print(f"\n========== CATEGORY: {result.get('category', 'N/A')} ==========")
    
    print("\n========== SUMMARY ==========")
    try:
        s = json.loads(result.get("summary", "{}"))
        print(s.get("Summary", s))
    except Exception:
        print(result.get("summary", ""))

    print("\n========== THOUGHT QUESTIONS ==========")
    tq = result.get("thought_questions", [])
    if tq:
        for i, q in enumerate(tq, 1):
            print(f"{i}. {q}")
    else:
        print("(no thought questions)")

    if result.get("category") == "지식형":
        print("\n========== QUIZ ==========")
        try:
            q = json.loads(result.get("quiz", "{}"))
            questions = q.get("questions", [])
            if not questions:
                print("(no quiz items)")
            for i, item in enumerate(questions, 1):
                print(f"\nQ{i}. {item.get('text') or item.get('question')}")
                for opt in item.get("options", []):
                    print(f"  {opt}")
                print("  정답:", item.get("answer"))
        except Exception:
            print(result.get("quiz", ""))
    
    print("\n========== JUDGE ==========")
    print("score:", result.get("judge_score"))
    print("needs_improve:", result.get("needs_improve"))
    print("improve_count:", result.get("improve_count", 0))

    # 🆕 페르소나 정보 출력
    print("\n========== PERSONA ==========")
    print("style:", result.get("persona_style", "N/A"))
    print("count:", result.get("persona_count", 0))
    
    # 🆕 페르소나가 적용된 최종 메시지 출력
    styled = result.get("styled_content", "")
    if styled:
        print("\n========== STYLED CONTENT (페르소나 적용) ==========")
        print(styled)
    
    # 🆕 에빙하우스 스케줄 출력
    print("\n========== EBBINGHAUS SCHEDULE ==========")
    schedule_dates = result.get("schedule_dates", [])
    if schedule_dates:
        for i, date in enumerate(schedule_dates, 1):
            print(f"{i}차 알림: {date} 오전 8시 (출근길)")
    else:
        print("(no schedule)")

    print("\n========== RAG ==========")
    print("query:", result.get("query", ""))
    cits = result.get("citations", [])
    if cits:
        print("citations:")
        for c in cits:
            cid = c.get("id")
            txt = (c.get("text") or "").replace("\n"," ")
            snip = (txt[:140] + "…") if len(txt) > 140 else txt
            print(f" - {cid}: {snip}")
    else:
        print("citations: (none)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, help="Input text")
    parser.add_argument("--url", type=str, help="YouTube URL")
    args = parser.parse_args()

    input_text = ""
    if args.url:
        if is_youtube_url(args.url):
            print(f"Extracting transcript from YouTube: {args.url}")
            video_id = extract_youtube_video_id(args.url)
            input_text = get_youtube_transcript(video_id)
        else:
            print(f"Extracting article content from: {args.url}")
            input_text = get_article_content(args.url)
    elif args.text:
        input_text = args.text
    else:
        raise ValueError('No input. Try: python main.py --url "https://youtu.be/..." or --text "$(cat article.txt)"')

    if not os.getenv("UPSTAGE_API_KEY"):
        raise ValueError("UPSTAGE_API_KEY not set")

    graph = build_graph()
    result = graph.invoke({"input_text": input_text, "max_improve": 2})
    pretty_print(result)


if __name__ == "__main__":
    main()
