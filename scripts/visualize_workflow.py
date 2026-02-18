#!/usr/bin/env python3
"""
Kafka AI 워크플로우 시각화

LangGraph의 get_graph()를 사용해 현재 그래프 구조를 Mermaid/PNG/ASCII로 출력합니다.
코드 변경 시 이 스크립트를 다시 실행하면 항상 최신 워크플로우가 반영됩니다.

사용법:
    python3 scripts/visualize_workflow.py
    python3 scripts/visualize_workflow.py --output-dir docs
    python3 scripts/visualize_workflow.py --format png
"""

import os
import sys
import argparse

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Kafka AI 워크플로우 시각화")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="출력 디렉터리 (기본: 현재 디렉터리)",
    )
    parser.add_argument(
        "--format",
        choices=["mermaid", "png", "ascii", "all"],
        default="all",
        help="출력 형식 (기본: all)",
    )
    args = parser.parse_args()

    from agent.graph import build_graph

    graph = build_graph()
    g = graph.get_graph()

    os.makedirs(args.output_dir, exist_ok=True)

    # 1. Mermaid 형식 (항상 출력)
    mermaid_code = g.draw_mermaid()
    mmd_path = os.path.join(args.output_dir, "workflow.mmd")

    if args.format in ("mermaid", "all"):
        with open(mmd_path, "w", encoding="utf-8") as f:
            f.write(mermaid_code)
        print(f"✅ Mermaid 저장: {mmd_path}")
        print("\n--- Mermaid 코드 (mermaid.live에 붙여넣기) ---\n")
        print(mermaid_code)
        print("\n--- 끝 ---\n")

    # 2. ASCII (grandalf 필요)
    if args.format in ("ascii", "all"):
        try:
            ascii_art = g.draw_ascii()
            print("\n--- ASCII 워크플로우 ---\n")
            print(ascii_art)
            print("\n--- 끝 ---\n")
        except ImportError as e:
            print(f"⚠️ ASCII 생성 실패 (pip install grandalf 필요): {e}")

    # 3. PNG (grandalf 필요)
    if args.format in ("png", "all"):
        try:
            png_bytes = g.draw_mermaid_png()
            png_path = os.path.join(args.output_dir, "workflow.png")
            with open(png_path, "wb") as f:
                f.write(png_bytes)
            print(f"✅ PNG 저장: {png_path}")
        except (ImportError, Exception) as e:
            print(f"⚠️ PNG 생성 실패 (pip install grandalf 필요): {e}")

    print("\n📖 확인 방법:")
    print("  1. Mermaid: https://mermaid.live 에서 workflow.mmd 내용 붙여넣기")
    print("  2. PNG: workflow.png 파일을 이미지 뷰어로 열기")
    print("  3. ASCII: 위 터미널 출력 참고")


if __name__ == "__main__":
    main()
