# web/app.py
"""
카프카 퀴즈 웹 서버 메인 앱

정보형 콘텐츠의 퀴즈를 웹 페이지로 제공하고,
사용자 답안을 채점하여 결과를 저장합니다.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import sys
import os
import json
import re
from datetime import datetime, timedelta

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.database import get_db
from agent.utils import clean_content_for_display

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 한글 JSON 응답 지원


def extract_quiz_from_content(styled_content: str) -> dict:
    """
    styled_content에서 퀴즈 정보 추출
    
    Args:
        styled_content: 페르소나가 적용된 콘텐츠
    
    Returns:
        {
            "summary": "요약 내용",
            "questions": [
                {
                    "text": "질문 내용",
                    "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
                    "answer": "A"
                },
                ...
            ]
        }
    """
    # 요약 부분 추출
    summary_match = re.search(r'\[요약\](.*?)(?:\[퀴즈\]|$)', styled_content, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else ""
    
    # 퀴즈 JSON 추출 시도 (중첩 괄호 처리)
    start = styled_content.find('{"questions"')
    if start != -1:
        depth, i, end = 0, start, start
        for i in range(start, len(styled_content)):
            c = styled_content[i]
            if c == '[' or c == '{':
                depth += 1
            elif c == ']' or c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        quiz_json = styled_content[start:end]
        try:
            quiz_data = json.loads(quiz_json)

            # 추가: 이유는 모르겠지만, 네이버 블로그의 경우 styled content에서 [요약]말고 요약으로 불러들어와 읽히지 않은 버그가 있었음.
            # 이미 찾은 summary가 없다면, 전체 텍스트에서 "요약": "내용" 패턴을 한 번 더 찾습니다.
            if not summary:
                # JSON 키값 형태의 요약 추출 (페르소나용)
                json_summary_match = re.search(r'"요약":\s*"([^"]*)"', styled_content)
                if json_summary_match:
                    summary = json_summary_match.group(1)
            # 여기까지 추가

            return {
                "summary": summary,
                "questions": quiz_data.get("questions", [])
            }
        except json.JSONDecodeError:
            pass
    
    # JSON 파싱 실패 시 텍스트 파싱
    questions = []
    
    # Q1, Q2... 형식으로 질문 찾기
    question_pattern = r'Q(\d+)\.\s*(.*?)(?=Q\d+\.|정답:|$)'
    matches = re.findall(question_pattern, styled_content, re.DOTALL)

    for num, q_text in matches:
        # 옵션 추출 (A), B), C), D) 형식)
        options = re.findall(r'([A-D]\).*?)(?=[A-D]\)|정답:|Q\d+\.|$)', q_text, re.DOTALL)
        options = [opt.strip() for opt in options if opt.strip()]
        
        # 정답 추출
        answer_match = re.search(r'정답:\s*([A-D])', q_text)
        answer = answer_match.group(1) if answer_match else "A"
        
        # 질문 텍스트 정리
        question_text = re.split(r'[A-D]\)', q_text)[0].strip()
        
        if options:
            questions.append({
                "text": question_text,
                "options": options,
                "answer": answer
            })
    
    return {
        "summary": summary,
        "questions": questions[:5]  # 최대 5개
    }


@app.route('/', methods=['GET'])
def index():
    """홈 페이지 - URL 입력 및 대기열 현황"""
    db = get_db()
    pending_count = db.get_pending_queue_count()
    alert = request.args.get('alert')
    alert_type = request.args.get('alert_type', 'info')
    if alert:
        alert = {'message': alert, 'type': alert_type}
    return render_template('index.html', pending_count=pending_count, alert=alert)


@app.route('/process', methods=['POST'])
def process_url():
    """URL 또는 텍스트를 즉시 처리하고 퀴즈 페이지로 이동"""
    url_or_text = (request.form.get('url') or request.form.get('url_or_text') or '').strip()

    if not url_or_text:
        return redirect(url_for('index', alert='URL 또는 텍스트를 입력해주세요.', alert_type='error'))

    if not os.getenv("UPSTAGE_API_KEY"):
        return redirect(url_for('index', alert='UPSTAGE_API_KEY 환경 변수가 설정되지 않았습니다.', alert_type='error'))

    try:
        import sys
        print("\n" + "=" * 50, flush=True)
        print("⚡ [웹] 즉시 처리 시작...", flush=True)
        print("=" * 50, flush=True)
        sys.stdout.flush()

        from agent.graph import build_graph
        graph = build_graph()
        initial_state = {
            "user_input": url_or_text,
            "input_text": "",
            "max_improve": 3,
            "skip_cache": True,  # 웹 즉시처리 시 캐시 건너뛰기 (항상 새로 분석)
        }
        result = graph.invoke(initial_state)

        # 터미널에 상세 출력 (main.py와 동일)
        from agent.utils.pretty_result import pretty_print
        pretty_print(result)

        print("\n✅ [웹] 처리 완료", flush=True)
        sys.stdout.flush()
    except Exception as e:
        return redirect(url_for('index', alert=f'처리 중 오류가 발생했습니다: {str(e)}', alert_type='error'))

    if result.get("is_valid") is False:
        msg = result.get("messages", "입력값이 유효하지 않습니다.")
        return redirect(url_for('index', alert=msg, alert_type='error'))

    if result.get("is_safe") is False:
        return redirect(url_for('index', alert='콘텐츠 안전 검사에 통과하지 못했습니다.', alert_type='error'))

    schedule_id = result.get("schedule_id")
    category = result.get("category", "지식형")

    # 퀴즈 추출: 1) result.quiz → 2) result.questions → 3) DB → 4) styled_content
    questions = result.get("questions") or []
    if not questions and result.get("quiz"):
        try:
            qj = json.loads(result["quiz"])
            questions = qj.get("questions", []) if isinstance(qj, dict) else []
        except (json.JSONDecodeError, TypeError):
            pass
    if not questions and schedule_id:
        schedule = get_db().get_schedule_by_id(schedule_id)
        if schedule:
            qj = schedule.get("questions")
            if qj:
                try:
                    questions = json.loads(qj) if isinstance(qj, str) else (qj or [])
                except (json.JSONDecodeError, TypeError):
                    pass
            if not questions:
                quiz_data = extract_quiz_from_content(schedule.get("styled_content", ""))
                questions = quiz_data.get("questions", [])
    if not questions and result.get("styled_content"):
        quiz_data = extract_quiz_from_content(result["styled_content"])
        questions = quiz_data.get("questions", [])

    if category == "지식형" and schedule_id and len(questions) > 0:
        return redirect(url_for('show_quiz', schedule_id=schedule_id, notification_index=1))

    if category == "지식형" and schedule_id and len(questions) == 0:
        return redirect(url_for('index', alert='퀴즈 생성에 실패했습니다. 요약이 비어있거나 형식 변환에 실패한 것 같습니다. 다시 시도해주세요.', alert_type='error'))

    if category != "지식형":
        return redirect(url_for('index', alert='힐링형 콘텐츠입니다. 퀴즈는 생성되지 않으며, 알림을 통해 생각 유도 질문을 확인할 수 있습니다.', alert_type='info'))

    return redirect(url_for('index', alert='퀴즈 생성에 실패했습니다. 다시 시도해주세요.', alert_type='error'))


@app.route('/add-url', methods=['POST'])
def add_url():
    """URL을 대기열에 추가"""
    url_or_text = (request.form.get('url') or '').strip()
    if not url_or_text:
        return redirect(url_for('index', alert='URL 또는 텍스트를 입력해주세요.', alert_type='error'))

    db = get_db()
    input_type = 'url' if url_or_text.startswith(('http://', 'https://')) else 'text'
    db.add_to_url_queue(url_or_text, user_id="default_user", input_type=input_type)
    pending = db.get_pending_queue_count()
    return redirect(url_for('index', alert=f'대기열에 추가되었습니다. (대기 중: {pending}개)', alert_type='success'))


@app.route('/quiz/<int:schedule_id>/<int:notification_index>')
def show_quiz(schedule_id, notification_index):
    """
    퀴즈 페이지 표시
    
    Args:
        schedule_id: 스케줄 ID
        notification_index: 알림 차수 (1, 2, 3, 4)
    
    Returns:
        HTML 페이지 (quiz.html)
    """
    db = get_db()
    schedule = db.get_schedule_by_id(schedule_id)
    
    if not schedule:
        return """
        <html>
        <head><meta charset="UTF-8"><title>오류</title></head>
        <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h1>❌ 스케줄을 찾을 수 없습니다</h1>
            <p>스케줄 ID: {}</p>
        </body>
        </html>
        """.format(schedule_id), 404
    
    # 정보형이 아니면 리다이렉트
    if schedule.get('category') != '지식형':
        return """
        <html>
        <head><meta charset="UTF-8"><title>알림</title></head>
        <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h1>💭 힐링형 콘텐츠입니다</h1>
            <p>힐링형 콘텐츠는 퀴즈가 없습니다.</p>
            <p>알림을 통해 생각 유도 질문을 확인해주세요.</p>
        </body>
        </html>
        """
    
    # 퀴즈 데이터 추출 (DB에서 직접 읽기)
    questions_json = schedule.get('questions')
    
    if not questions_json:
        # questions 컬럼이 없으면 styled_content에서 추출 시도 (하위 호환)
        quiz_data = extract_quiz_from_content(schedule['styled_content'])
        if not quiz_data['questions']:
            return """
            <html>
            <head><meta charset="UTF-8"><title>오류</title></head>
            <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                <h1>⚠️ 퀴즈를 찾을 수 없습니다</h1>
                <p>콘텐츠에 퀴즈 정보가 없습니다.</p>
                <p style="color: #999; font-size: 12px;">Schedule ID: {}</p>
            </body>
            </html>
            """.format(schedule_id), 404
    else:
        # DB에서 직접 읽은 퀴즈 데이터 파싱
        try:
            questions_list = json.loads(questions_json)
            quiz_data = {
                'summary': schedule.get('summary', ''),
                'questions': questions_list
            }
        except json.JSONDecodeError:
            return """
            <html>
            <head><meta charset="UTF-8"><title>오류</title></head>
            <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                <h1>⚠️ 퀴즈 데이터 파싱 오류</h1>
                <p>퀴즈 데이터 형식이 잘못되었습니다.</p>
            </body>
            </html>
            """, 500
    
    if not quiz_data['questions']:
        return """
        <html>
        <head><meta charset="UTF-8"><title>오류</title></head>
        <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h1>⚠️ 퀴즈를 찾을 수 없습니다</h1>
            <p>콘텐츠에 퀴즈 정보가 없습니다.</p>
        </body>
        </html>
        """, 404
    
    # notification_index에 해당하는 1개 문제만 추출 (인덱스는 1부터 시작)
    question_index = notification_index - 1  # 0-based index
    
    if question_index >= len(quiz_data['questions']):
        # 문제가 부족하면 마지막 문제 사용
        question_index = len(quiz_data['questions']) - 1
    
    current_question = quiz_data['questions'][question_index]
    
    # 페르소나도 notification_index에 맞게 선택
    persona_map = {
        1: "친근한 친구",
        2: "다정한 선배", 
        3: "엄격한 교수",
        4: "유머러스한 코치",
        5: "밈 마스터"  # 예비
    }
    persona_for_today = persona_map.get(notification_index, "친근한 친구")
    
    summary_display = clean_content_for_display(quiz_data.get('summary', ''))

    return render_template('quiz.html',
        schedule_id=schedule_id,
        notification_index=notification_index,
        question=current_question,  # 1개 문제만
        total_questions=len(quiz_data['questions']),
        summary=summary_display,
        persona_style=persona_for_today
    )


@app.route('/quiz/<int:schedule_id>/<int:notification_index>/submit', methods=['POST'])
def submit_quiz(schedule_id, notification_index):
    """
    퀴즈 답안 제출 및 채점
    
    Request Body:
        {
            "answer": "A"  # 1개 문제의 답
        }
    
    Returns:
        {
            "is_correct": true,
            "user_answer": "A",
            "correct_answer": "A",
            "retry_scheduled": false
        }
    """
    data = request.get_json(silent=True) or {}
    user_answer = data.get('answer', '')
    
    db = get_db()
    schedule = db.get_schedule_by_id(schedule_id)
    
    if not schedule:
        return jsonify({"error": "스케줄을 찾을 수 없습니다"}), 404
    
    # 정답 추출 (DB에서 직접 읽기)
    questions_json = schedule.get('questions')
    
    if not questions_json:
        # questions 컬럼이 없으면 styled_content에서 추출 시도 (하위 호환)
        quiz_data = extract_quiz_from_content(schedule['styled_content'])
    else:
        try:
            questions_list = json.loads(questions_json)
            quiz_data = {'questions': questions_list}
        except json.JSONDecodeError:
            return jsonify({"error": "퀴즈 데이터 파싱 오류"}), 500

    if not quiz_data.get('questions'):
        return jsonify({"error": "퀴즈를 찾을 수 없습니다"}), 404
    
    # notification_index에 해당하는 문제의 정답 가져오기
    question_index = notification_index - 1
    if question_index >= len(quiz_data['questions']):
        question_index = len(quiz_data['questions']) - 1
    
    correct_answer = quiz_data['questions'][question_index]['answer']
    
    # 채점 (1개 문제)
    is_correct = user_answer == correct_answer
    score = 100 if is_correct else 0
    
    # DB에 기록
    db.save_quiz_attempt(
        schedule_id=schedule_id,
        notification_index=notification_index,
        user_answers=[user_answer],
        correct_answers=[correct_answer],
        score=score,
        is_passed=is_correct
    )
    
    # 오답 시 재발송 스케줄링
    retry_scheduled = False
    if not is_correct:
        retry_count = db.get_retry_count(schedule_id, notification_index)
        
        if retry_count < 3:  # 최대 3회까지
            tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
            db.add_retry_schedule(
                schedule_id=schedule_id,
                notification_index=notification_index,
                retry_date=tomorrow,
                retry_count=retry_count + 1
            )
            retry_scheduled = True
            print(f"🔄 스케줄 {schedule_id}: 재발송 예약 완료 ({tomorrow})")
        else:
            print(f"⚠️  스케줄 {schedule_id}: 최대 재시도 횟수 초과")
    
    return jsonify({
        'is_correct': is_correct,
        'user_answer': user_answer,
        'correct_answer': correct_answer,
        'retry_scheduled': retry_scheduled,
        'question_text': quiz_data['questions'][question_index].get('text', '')
    })


if __name__ == '__main__':
    print("=" * 60)
    print("🎓 카프카 퀴즈 웹 서버")
    print("=" * 60)
    print()
    print("📍 URL: http://localhost:5000")
    print("🔗 퀴즈 링크 형식: http://localhost:5000/quiz/{schedule_id}/{notification_index}")
    print()
    print("⚠️  주의: 이 서버는 팝업 알림을 클릭했을 때 열립니다")
    print("         직접 브라우저로 접속하려면 스케줄 ID가 필요합니다")
    print()
    
    app.run(debug=True, host='0.0.0.0', port=5000)