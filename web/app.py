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
    
    # 퀴즈 JSON 추출 시도
    quiz_json_match = re.search(r'\{"questions":\s*\[(.*?)\]\}', styled_content, re.DOTALL)
    
    if quiz_json_match:
        try:
            # JSON 파싱
            quiz_json = '{"questions": [' + quiz_json_match.group(1) + ']}'
            quiz_data = json.loads(quiz_json)
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


@app.route('/')
def index():
    """홈 페이지"""
    return """
    <html>
    <head>
        <meta charset="UTF-8">
        <title>카프카 퀴즈</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
            }
            h1 { color: #2c3e50; }
            p { color: #7f8c8d; line-height: 1.6; }
            .info { background: #ecf0f1; padding: 20px; border-radius: 8px; margin-top: 20px; }
        </style>
    </head>
    <body>
        <h1>🎓 카프카 퀴즈 시스템</h1>
        <p>팝업 알림에서 퀴즈 링크를 클릭하면 여기로 이동합니다.</p>
        <div class="info">
            <p><strong>📌 사용 방법</strong></p>
            <p>1. main.py로 콘텐츠 추가 (지식형)</p>
            <p>2. 스케줄러로 알림 발송</p>
            <p>3. 알림 클릭 → 퀴즈 페이지</p>
            <p>4. 퀴즈 풀기 → 제출</p>
        </div>
    </body>
    </html>
    """


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
    
    return render_template('quiz.html',
        schedule_id=schedule_id,
        notification_index=notification_index,
        question=current_question,  # 1개 문제만
        total_questions=len(quiz_data['questions']),
        summary=quiz_data['summary'],
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
    user_answer = request.json.get('answer', '')
    
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
        'question_text': quiz_data['questions'][question_index]['text']
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
