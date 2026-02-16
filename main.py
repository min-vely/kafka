import os
import argparse
import json
from agent.graph import build_graph
#유틸 모두 graph로 이동

def pretty_print(result: dict):
    #extract_content_node노드 검증
    final_msg = result.get("messages", "메시지가 없습니다.")
    is_valid = result.get("is_valid")
    is_safe = result.get("is_safe")

    print("\n" + "=" * 10 + " 🔍 INPUT VERIFICATION " + "=" * 10)
    # [1단계] 주소/입력 유효성
    valid_status = "✅ PASS" if is_valid else "❌ FAIL"
    print(f"STATUS  : {valid_status}")

    # [2단계] 콘텐츠 안전성 (is_valid가 True일 때만 출력)
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
    parser.add_argument("--url", type=str, help="YouTube URL or News Article URL")
    parser.add_argument(
        "--process-now",
        action="store_true",
        help="URL을 큐에 넣지 않고 즉시 처리 (기본: URL은 큐에 저장, --process-now면 즉시 처리)"
    )
    args = parser.parse_args()

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
        "max_improve": 2
    }
    
    # URL이 있으면 추가(input_url로 기능 이동)
    # if target_url:
    #     initial_state["url"] = target_url
    result = graph.invoke(initial_state)
    pretty_print(result)


if __name__ == "__main__":
    main()
