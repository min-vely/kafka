import os
import sys
import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.graph import build_graph
from agent.utils.pretty_result import pretty_print


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, help="Input text")
    parser.add_argument("--url", type=str, help="YouTube URL or News Article URL")
    parser.add_argument(
        "--evaluate-classify",
        action="store_true",
        help="분류 정확도 평가 실행 (fixture 기반, 터미널에 결과 출력)",
    )
    parser.add_argument(
        "--process-now",
        action="store_true",
        help="URL을 큐에 넣지 않고 즉시 처리 (기본: URL은 큐에 저장, --process-now면 즉시 처리)"
    )
    parser.add_argument("--web", action="store_true", help="웹 UI 모드 (8080 포트)")
    parser.add_argument(
        "--fixture",
        type=str,
        default="",
        help="[--evaluate-classify 시] 샘플 JSON 경로 (미지정 시 기본 fixture 사용)",
    )
    parser.add_argument(
        "--show-classify-accuracy",
        action="store_true",
        help="URL/텍스트 처리 시, 맨 처음에 분류 정확도 평가 결과를 먼저 출력 (처리 전에 함께 확인)",
    )
    args = parser.parse_args()

    # 분류 정확도 평가 모드 (추가 기능)
    if args.evaluate_classify:
        import subprocess
        project_root = Path(__file__).resolve().parent
        script_path = project_root / "scripts" / "evaluate_classify_accuracy.py"
        cmd = [sys.executable, str(script_path)]
        if args.fixture:
            cmd.extend(["--fixture", args.fixture])
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root)
        subprocess.run(cmd, check=True, cwd=project_root, env=env)
        return

    # 인자 없이 실행 시 웹 UI 모드 (main.py 또는 main.py --web)
    if not args.text and not args.url:
        from web.app import app
        print("=" * 60)
        print("🎓 카프카 AI - 웹 UI 모드")
        print("=" * 60)
        print()
        print("📍 URL: http://localhost:8080")
        print("   → URL 입력 → 즉시 처리 → 퀴즈 풀기")
        print()
        print("⚠️  Ctrl+C로 종료")
        print()
        app.run(debug=True, host='0.0.0.0', port=8080, use_reloader=False)
        return

    # input_url노드로 값 받기 위한 변수 추가(input_text, source_input)
    input_text = ""
    target_url = args.url
    raw_text = args.text
    source_input = ""

    # 1. 터미널 인자(--text, --url)가 있는 경우
    if raw_text:
        source_input = raw_text
        input_text = raw_text  # 텍스트면 바로 본문으로!
    elif target_url:
        source_input = target_url
        input_text = ""  # URL은 노드에서 추출해야 하니까 비워둠
        
        # URL 무제한 저장 모드: --process-now 없으면 큐에 저장만 하고 종료
        if not args.process_now:
            from agent.database import get_db
            db = get_db()
            qid = db.add_to_url_queue(target_url, user_id="default_user", input_type="url")
            pending = db.get_pending_queue_count()
            print(f"✅ URL이 대기열에 저장되었습니다 (큐 ID: {qid})")
            print(f"   📬 대기 중인 URL: {pending}개")
            print(f"   💡 스케줄러가 매일 1개씩 처리합니다 (python -m agent.scheduler.scheduler_service)")
            print(f"   💡 즉시 처리하려면: python main.py --url \"{target_url}\" --process-now")
            return

    # 인자가 아무것도 없을 경우 대화형 입력 모드 진입
    else:
        user_input = input("URL 또는 텍스트(파일명)를 입력하세요: ").strip()
        if not user_input:
            print("입력값이 없습니다. 프로그램을 종료합니다.")
            return

        # URL 판별(input_url로 이동)
        #if user_input.startswith(("http://", "https://")):
        #target_url = user_input

        # 파일 존재 여부 확인
        if os.path.isfile(user_input):
            print(f"파일을 읽어옵니다: {user_input}")
            with open(user_input, "r", encoding="utf-8") as f:
                input_text = f.read()
            source_input = user_input # 파일이면 경로를 넣어줌
        else:
            #[중요!] URL 오타 등을 검증하려면 input_text에 미리 담지 말고
            # source_input에만 담아서 1번 노드로 보내야 합니다.
            source_input = user_input
            input_text = "" #본문 비우기


    # URL 처리 로직(extract_content_node로 이동)
    # if target_url:
    #     if is_youtube_url(target_url):
    #         print(f"Extracting transcript from YouTube: {target_url}")
    #         video_id = extract_youtube_video_id(target_url)
    #         input_text = get_youtube_transcript(video_id)
    #     else:
    #         print(f"Extracting article content from: {target_url}")
    #         input_text = get_article_content(target_url)
    # if not source_input:
    #     print("처리할 내용이 없습니다.")
    #     return

    # if raw_text:
    #     input_text = raw_text
    #
    # if not input_text:
    #     print("처리할 텍스트가 없습니다.")
    #     return

    if not os.getenv("UPSTAGE_API_KEY"):
        raise ValueError("UPSTAGE_API_KEY not set")

    graph = build_graph()

    # 만약 위에서 source_input이 제대로 안 담겼을 경우 대비한 코드
    if not source_input and 'user_input' in locals():
        source_input = user_input

    # 그래프에 전달할 초기 상태(State) 설정
    initial_state = {
        "user_input": source_input,  # URL이나 직접 입력한 텍스트
        "input_text": input_text,  # 파일에서 읽어온 '본문' 내용 (여기에 넣어줘야 함!)
        "max_improve": 3  # 3회 초과 시 마지막 요약으로 확정
    }

    # URL/텍스트 처리 시, 맨 처음에 분류 정확도 평가 결과 출력 (선택)
    if args.show_classify_accuracy:
        import subprocess
        project_root = Path(__file__).resolve().parent
        script_path = project_root / "scripts" / "evaluate_classify_accuracy.py"
        cmd = [sys.executable, str(script_path)]
        if args.fixture:
            cmd.extend(["--fixture", args.fixture])
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root)
        subprocess.run(cmd, check=True, cwd=project_root, env=env)
        print("\n" + "=" * 60)
        print("아래: URL/텍스트 처리 결과")
        print("=" * 60 + "\n")
    
    # # URL이 있으면 추가(input_url로 기능 이동)
    # # if target_url:
    # #     initial_state["url"] = target_url
    # result = graph.invoke(initial_state)
    # pretty_print(result)

    # 그래프 실행 및 결과 획득
    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        print(f"\n❌ 처리 중 오류가 발생했습니다: {e}")
        raise

    # 🆕 에이전틱 레이어: 최종 메시지 내 일정이 있다면 구글 캘린더 등록 링크 생성
    from agent.tools.calendar_event_adder import run_calendar_agent
    if result.get("styled_content"):
        try:
            combined_input = f"원본정보: {result.get('context', '')}\n요약내용: {result['styled_content']}"
            result["styled_content"] = run_calendar_agent(combined_input)
        except Exception as e:
            print(f"⚠️ 캘린더 에이전트 실행 중 오류 (무시하고 계속): {e}")

    # 최종 결과 출력
    pretty_print(result)


if __name__ == "__main__":
    main()
