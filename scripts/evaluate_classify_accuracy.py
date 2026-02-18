#!/usr/bin/env python3
"""
classify 노드 정확도 평가 스크립트

기획서 체크포인트: classify Accuracy (라벨 비교)

사용법:
    python3 scripts/evaluate_classify_accuracy.py
    python3 scripts/evaluate_classify_accuracy.py --fixture tests/fixtures/classify_samples.json

.fienv 및 UPSTAGE_API_KEY 필요
"""

import argparse
import json
import os
from pathlib import Path

# 프로젝트 루트 추가
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)


def load_fixture(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="classify 정확도 평가")
    parser.add_argument(
        "--fixture",
        default=str(ROOT / "tests" / "fixtures" / "classify_samples.json"),
        help="샘플 JSON 경로 (text, expected 필드)",
    )
    args = parser.parse_args()

    samples = load_fixture(args.fixture)
    if not samples:
        print("⚠️ 샘플이 비어 있습니다.")
        return

    from agent.nodes.nodes import classify_content

    correct = 0
    results = []

    print("=" * 60)
    print("📊 classify 정확도 평가")
    print("=" * 60)
    print(f"샘플 수: {len(samples)}개\n")

    for i, s in enumerate(samples, 1):
        text = s.get("text", "")
        expected = s.get("expected", "")
        if not text or expected not in ("지식형", "힐링형"):
            print(f"  [{i}] 건너뜀 (text/expected 누락)")
            continue

        pred = classify_content(text)
        ok = pred == expected
        if ok:
            correct += 1
        results.append({"i": i, "expected": expected, "predicted": pred, "ok": ok})
        status = "✅" if ok else "❌"
        print(f"  [{i}] {status} expected={expected}, predicted={pred}")

    total = len(results)
    accuracy = correct / total if total else 0.0

    print("\n" + "-" * 60)
    print(f"정확도: {correct}/{total} = {accuracy:.1%}")
    print("=" * 60)

    return accuracy


if __name__ == "__main__":
    main()
