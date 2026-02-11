import os
import argparse
import json

from agent.graph import build_graph
from agent.utils import extract_youtube_video_id, get_youtube_transcript


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
                for j, opt in enumerate(item.get("options", []), 1):
                    print(f"  {j}) {opt}")
                print("  정답:", item.get("answer"))
        except Exception:
            print(result.get("quiz", ""))
    
    print("\n========== JUDGE ==========")
    print("score:", result.get("judge_score"))
    print("needs_improve:", result.get("needs_improve"))
    print("improve_count:", result.get("improve_count", 0))

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
        print(f"Extracting transcript from: {args.url}")
        video_id = extract_youtube_video_id(args.url)
        input_text = get_youtube_transcript(video_id)
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
