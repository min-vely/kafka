// 카프카 퀴즈 클라이언트 로직

// 라디오 버튼 선택 시 시각적 피드백
document.querySelectorAll('input[type="radio"]').forEach(radio => {
    radio.addEventListener('change', function() {
        // 같은 name의 다른 라디오 버튼들의 부모 label에서 selected 클래스 제거
        const name = this.name;
        document.querySelectorAll(`input[name="${name}"]`).forEach(r => {
            r.closest('.option').classList.remove('selected');
        });
        
        // 선택된 라디오 버튼의 부모 label에 selected 클래스 추가
        this.closest('.option').classList.add('selected');
        
        console.log(`Q${name} 선택됨: ${this.value}`);
    });
});

document.getElementById('quiz-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // 제출 버튼 비활성화
    const submitBtn = e.target.querySelector('.submit-btn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="loading"></span> 채점 중...';
    
    // 답안 수집 (1개 문제)
    const form = e.target;
    const selected = form.querySelector('input[name="answer"]:checked');
    
    if (!selected) {
        alert('답을 선택해주세요!');
        submitBtn.disabled = false;
        submitBtn.innerHTML = '제출하기';
        return;
    }
    
    const answer = selected.value;
    console.log('제출된 답안:', answer);
    
    try {
        // 서버로 제출
        const response = await fetch(
            `/quiz/${scheduleId}/${notificationIndex}/submit`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ answer })
            }
        );
        
        if (!response.ok) {
            throw new Error('제출 실패');
        }
        
        const result = await response.json();
        
        // 결과 표시
        displayResult(result);
        
        // 폼 숨기기
        form.style.display = 'none';
        
    } catch (error) {
        alert('오류가 발생했습니다: ' + error.message);
        submitBtn.disabled = false;
        submitBtn.innerHTML = '제출하기';
    }
});

function displayResult(result) {
    const resultDiv = document.getElementById('result');
    
    let html = '';
    
    if (result.is_correct) {
        html = `
            <h2>🎉 정답입니다!</h2>
            <div class="answer-info">
                <p><strong>당신의 답:</strong> ${result.user_answer}</p>
                <p><strong>정답:</strong> ${result.correct_answer}</p>
            </div>
            <p class="result-message">훌륭합니다! 복습을 잘 하셨네요. 😊</p>
            <p class="next-info">다음 복습 알림 때 새로운 문제로 뵙겠습니다!</p>
        `;
        resultDiv.className = 'result-box success';
    } else {
        html = `
            <h2>😅 틀렸습니다</h2>
            <div class="answer-info">
                <p><strong>당신의 답:</strong> <span class="incorrect">${result.user_answer}</span></p>
                <p><strong>정답:</strong> <span class="correct">${result.correct_answer}</span></p>
            </div>
            ${result.retry_scheduled 
                ? '<p class="result-message"><strong>🔄 내일 오전 8시에 다시 복습 알림을 보내드리겠습니다!</strong></p>' 
                : '<p class="result-message">최대 재시도 횟수(3회)를 초과했습니다.</p>'
            }
            <p class="hint">💡 요약을 다시 읽어보시면 도움이 될 거예요!</p>
        `;
        resultDiv.className = 'result-box fail';
    }
    
    resultDiv.innerHTML = html;
    resultDiv.style.display = 'block';
    
    // 결과 영역으로 스크롤
    resultDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// CSS에 추가할 스타일
const style = document.createElement('style');
style.textContent = `
    .score-large {
        font-size: 3em;
        font-weight: bold;
        margin: 20px 0;
    }
    
    .result-box h3 {
        margin-bottom: 16px;
        color: #2c3e50;
    }
`;
document.head.appendChild(style);
