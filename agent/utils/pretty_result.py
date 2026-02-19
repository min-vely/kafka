"""graph 실행 결과를 터미널에 출력하는 유틸리티"""
import json
from agent.utils import clean_content_for_display


def pretty_print(result: dict):
    """graph.invoke() 결과를 터미널에 상세 출력"""
    final_msg = result.get("messages", "메시지가 없습니다.")
    is_valid = result.get("is_valid")
    is_safe = result.get("is_safe")

    print("\n" + "=" * 10 + " 🔍 INPUT VERIFICATION " + "=" * 10)
    valid_status = "✅ PASS" if is_valid else "❌ FAIL"
    print(f"STATUS  : {valid_status}")

    if is_valid:
        safe_status = "✅ SAFE" if is_safe else "🚨 UNSAFE"
        print(f"SAFETY  : {safe_status}")
    else:
        print(f"SAFETY  : ➖ SKIP (검증 실패)")

    print(f"MESSAGE : {final_msg}")
    print("=" * 43)

    print(f"\n========== CATEGORY: {result.get('category', 'N/A')} ==========")

    print("\n========== SUMMARY ==========")
    try:
        s = json.loads(result.get("summary", "{}"))
        raw = s.get("Summary", s)
        print(clean_content_for_display(str(raw) if raw else ""))
    except Exception:
        print(clean_content_for_display(str(result.get("summary", ""))))

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

    print("\n========== PERSONA ==========")
    print("style:", result.get("persona_style", "N/A"))
    print("count:", result.get("persona_count", 0))

    styled = result.get("styled_content", "")
    if styled:
        print("\n========== STYLED CONTENT (페르소나 적용) ==========")
        print(clean_content_for_display(styled))

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
            txt = (c.get("text") or "").replace("\n", " ")
            snip = (txt[:140] + "…") if len(txt) > 140 else txt
            print(f" - {cid}: {snip}")
    else:
        print("citations: (none)")
