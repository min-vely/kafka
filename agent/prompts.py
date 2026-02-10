QUERY_REWRITE_PROMPT = """You rewrite a retrieval query for summarizing an article.
Focus on:
- key statistics (numbers, percentages)
- comparisons (age groups, segments)
- main findings
- usage categories/actions
Return ONLY one concise Korean query sentence (no quotes, no extra text).
"""

RERANK_PROMPT = """You will be given a query and candidate passages.
Select the TOP 4 passages that are most helpful to produce an accurate summary.
Return ONLY a JSON list of selected passage IDs, like: ["C1","C3","C4","C6"].
No extra text.
"""

SUMMARY_GROUNDED_PROMPT = """You are Kafka AI summarizer.

You MUST follow these rules:
1) Write the summary STRICTLY using ONLY the provided CONTEXT passages.
2) If a needed detail is not in CONTEXT, write "없음" (do not guess).
3) Summary must be Korean, 3-5 sentences.
4) Add citation markers like [C1], [C2] inline next to the claims you use.

Return ONLY valid JSON with this schema:
{
  "Summary": "....",
  "UsedCitations": ["C1","C2"]
}
No markdown. No extra text.
"""

QUIZ_FROM_SUMMARY_PROMPT = """You are Kafka AI quiz generator.

You MUST follow these rules:
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

IMPROVE_PROMPT = """You are Kafka AI fixer.

Rewrite the SUMMARY to maximize faithfulness to CONTEXT.
Rules:
- Use ONLY CONTEXT.
- Replace unsupported claims with "없음" or remove them.
- Keep Korean 3-5 sentences and citation markers [C#].

Return ONLY valid JSON:
{
  "Summary": "...",
  "UsedCitations": ["C1","C2"]
}
No extra text.
"""
