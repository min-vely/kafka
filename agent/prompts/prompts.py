QUERY_REWRITE_PROMPT = """You rewrite a retrieval query for summarizing an article.
Focus on:
- key statistics (numbers, percentages)
- comparisons (age groups, segments)
- main findings
- usage categories/actions
Return ONLY one concise Korean query sentence (no quotes, no extra text).
"""

RERANK_PROMPT = """You will be given a query and candidate passages.
Select the TOP 4 passages that are most helpful.
Return ONLY a JSON list of selected passage IDs, like: ["C1","C3","C4","C6"].
No extra text.
"""

SUMMARY_DRAFT_PROMPT = """You are Kafka AI summarizer.

Task:
- Summarize the ARTICLE in Korean, exactly 3 sentences.
Rules:
- Do NOT add citations here.
- If a detail is uncertain, write "없음" (do not guess).
Return ONLY plain Korean text (no JSON, no markdown).
"""

IMPROVE_DRAFT_PROMPT = """You are Kafka AI fixer.

Given:
- CONTEXT passages (ground truth)
- SUMMARY_DRAFT (may contain unsupported claims)

Task:
Rewrite SUMMARY_DRAFT to maximize faithfulness to CONTEXT.
Rules:
- Use ONLY CONTEXT.
- Replace unsupported claims with "없음" or remove them.
- Keep Korean exactly 3 sentences.
- Do NOT add citations here. (citations will be attached later)

Return ONLY plain Korean text (no JSON, no markdown).
"""

QUIZ_FROM_SUMMARY_PROMPT = """You are Kafka AI quiz generator.

Rules:
1) Generate questions that can be answered ONLY using the SUMMARY below.
2) Do NOT use any information not present in the summary.
3) Exactly 3 multiple-choice questions.
4) Each question has 4 options A/B/C/D and answer must be one of "A","B","C","D".

Return ONLY valid JSON with this schema:
{
  "questions": [
    {
      "text": "...",
      "options": ["A ...", "B ...", "C ...", "D ..."],
      "answer": "A"
    }
  ]
}
No markdown. No extra text.
"""

CLASSIFY_PROMPT = """너는 콘텐츠 분류 전문가야. 제공된 콘텐츠를 아래의 사고 과정(Chain of Thought)에 따라 분류해줘.

[분류 규칙]
지식형: 객관적 사실(역사, 기술, 수치)이 핵심이며, 정답을 맞히는 '회상 학습'이 중요한 경우.
일반형: 주관적 서사(미담, 관점, 교훈)가 핵심이며, 자기 생각을 정리하는 '반추'가 중요한 경우.

[사고 과정 가이드]
분석: 이 콘텐츠의 핵심 데이터가 '객관적 사실'인가, '주관적 서사'인가?
판단: 학습자가 '정답을 맞히는 것'과 '생각을 정리하는 것' 중 무엇이 더 가치 있는가?
예외 처리: 뉴스 형식을 갖춘 미담일지라도, 팩트보다 '감동과 가치'가 우선이라면 [일반형]으로 분류한다.

[출력 형식]
Reasoning: (위 가이드에 따른 논리적 추론 과정)
Category: [지식형] 또는 [일반형]"""

THOUGHT_QUESTION_PROMPT = """You are a facilitator of deep reflection.
Based on the SUMMARY below, generate 2-3 "thought-inducing questions" (생각유도질문) in Korean.

Rules:
- If category is "지식형", questions should focus on how this knowledge can be applied or why it's important.
- If category is "일반형", questions should focus on personal reflection, feelings, or life changes.
- Return ONLY a JSON list of strings.

Return format:
["질문1", "질문2"]
"""

JUDGE_PROMPT = """You are a strict evaluator of faithfulness.

Given:
- CONTEXT passages (ground truth)
- SUMMARY (model output)

Task:
Score faithfulness from 0 to 10.
- 10: every claim is directly supported by CONTEXT.
- 0: mostly unsupported or hallucinated.

If any unsupported claim exists, score must be <= 6.
If score < 7, set needs_improve=true else false.

Return ONLY valid JSON:
{
  "score": 0-10,
  "needs_improve": true/false,
  "notes": "one short Korean sentence"
}
No extra text.
"""
