import argparse
import os
import json

from agent.graph import build_graph


def _pp(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, help="Input text (or article text).")
    parser.add_argument("--eval", action="store_true", help="Print pairwise A/B eval report.")
    parser.add_argument("--max-improve", type=int, default=2, help="Max improve iterations in judge loop.")
    parser.add_argument("--debug", action="store_true", help="Print debug keys.")
    args = parser.parse_args()

    if not os.getenv("UPSTAGE_API_KEY"):
        raise ValueError("UPSTAGE_API_KEY not set")

    input_text = args.text
    if not input_text:
        print("텍스트가 없습니다.")
        return

    graph = build_graph()

    # do_ab_eval=True: 항상 A(LLM) vs B(RAG) 비교 후 더 나은 쪽을 summary로 채택
    result = graph.invoke(
        {
            "input_text": input_text,
            "max_improve": args.max_improve,
            "do_ab_eval": True,
            "print_eval": bool(args.eval),
        }
    )

    # 🔥 여기 추가하세요
    print("[DEBUG winner]", result.get("winner"),
        "| has_pairwise_eval?", "pairwise_eval" in result)


    if args.debug:
        print("\n[DEBUG result keys]", sorted(result.keys()))

    # (선택) A/B 평가 리포트 출력
    if args.eval:
        report = result.get("pairwise_eval")
        if report is not None:
            print("\n========== RAG VS LLM (PAIRWISE EVAL) ==========")
            _pp(report)

    winner = result.get("winner")
    final_summary = result.get("summary", "")

    print("\n========== FINAL SUMMARY ==========")
    if winner:
        print(f"(winner={winner})")
    print(final_summary)


if __name__ == "__main__":
    main()
