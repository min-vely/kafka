# 🔀 Kafka AI 워크플로우 시각화

LangGraph 그래프를 Mermaid/PNG/ASCII로 시각화하여 현재 워크플로우 구조를 확인할 수 있습니다.

---

## 🚀 실행 방법

```bash
# 프로젝트 루트에서
python3 scripts/visualize_workflow.py
```

**옵션:**
- `--output-dir <경로>`: 출력 디렉터리 (기본: 현재 디렉터리)
- `--format <형식>`: `mermaid` | `png` | `ascii` | `all` (기본: all)

**예시:**
```bash
# docs 폴더에 Mermaid만 저장
python3 scripts/visualize_workflow.py --format mermaid --output-dir docs

# PNG 이미지 생성 (grandalf + 네트워크 필요)
python3 scripts/visualize_workflow.py --format png
```

---

## 📖 확인 방법

### 1. Mermaid (가장 쉬움, 항상 동작)

1. 스크립트 실행 후 `workflow.mmd` 파일이 생성됨
2. [https://mermaid.live](https://mermaid.live) 접속
3. 왼쪽 편집기에 `workflow.mmd` 내용 전체 붙여넣기
4. 오른쪽에 플로우차트가 실시간 렌더링됨
5. PNG/SVG로 다운로드 가능

### 2. PNG (이미지 파일로 저장)

- **필수**: `pip install grandalf`
- **네트워크**: mermaid.ink API 호출 또는 Pyppeteer (로컬 렌더링)
- 실행 시 `workflow.png` 파일 생성 → 이미지 뷰어로 열기

### 3. ASCII (터미널에서 바로 확인)

- **필수**: `pip install grandalf`
- 터미널에 텍스트 기반 플로우차트 출력

---

## 📁 출력 파일

| 파일 | 설명 |
|------|------|
| `workflow.mmd` | Mermaid 코드. mermaid.live에 붙여넣으면 시각화됨 |
| `workflow.png` | PNG 이미지 (grandalf + 네트워크 필요 시 생성) |

---

## 🔄 업데이트

그래프 구조(`agent/graph/graph.py`)를 수정한 후 스크립트를 다시 실행하면 **항상 최신 워크플로우**가 반영됩니다.
