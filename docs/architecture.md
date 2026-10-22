# 아키텍처

```
CoinGecko API ──► scripts/collect_coins ──► data/coins.json ──► scripts/index_coins ──► Chroma: coin_meta (코인당 1청크, id=coin_id)
Wikidata P5777 ─┘                              │
                                               ▼
Wikipedia(ko→en) ─► scripts/collect_item_docs ─► data/docs/wikipedia/{coin_id}_{doc_id}.json + manifest.json
백서 PDF·웹 ──────► scripts/collect_whitepapers ─► data/docs/whitepaper/… (PDF 는 쪽 단위, git 제외)
                    (질문 시: 프롬프트1 검색어 → 후보 검색 → 프롬프트2 선별 → 즉시 색인, src/rag/collect.py)
                                               ▼
                                     scripts/index_docs ──► Chroma: coin_docs (id=coin:doc:seq)

질문 ─► LangGraph[retrieve: coin_meta(항상) + coin_docs(coin_id 필터, Top-k) 병합·중복제거]
     ─► [generate: 프롬프트3, [근거 n]] ─► 인용된 근거만 반환 ─► FastAPI ─► web/ (HTML/CSS/JS)
```

| 영역 | 위치 | 책임 |
|---|---|---|
| 데이터 준비 (도메인 의존) | `src/data_prep/` | CoinGecko·위키 클라이언트, 정규화, 색인 텍스트, 문서 저장/manifest, 프롬프트, 코인 목록(catalog) |
| Vector Store | `src/vectorstore/` | 임베딩, 컬렉션, 청킹 |
| RAG 파이프라인 | `src/rag/` | LLM 호출(llm), 질문 기반 수집(collect), 검색·병합(retrieve), LangGraph retrieve→generate(graph) |
| 서비스 | `src/service/`, `src/rag/graph.py` mode | 조건 탐색(recommend), 리스크 브리핑·팩트체크(graph mode=brief/factcheck) |
| UI · API | `web/`, `src/server.py` | 코인 선택, 채팅, 근거·진행 상태·면책 표시, 샘플 모드 / FastAPI `/api/*` |
| 설정 | `config/settings.json`, `.env` | 청킹·Top-k·경로 / 키·연락처 |

## 개발 하네스

```
scripts/agent_loop.py ─► claude -p (구현, 새 컨텍스트) ─► 테스트(pytest, check_sample)
        ▲                                                        │
        └──── FAIL 이면 지적을 넘겨 다시 구현 (수정 최대 3회) ◄── codex exec --sandbox read-only (검증) ─► docs/reviews/*.md
```
명령·옵션: `config/agents.json`. 공통 지침: `AGENTS.md`. 근거: `docs/decisions.md` D11.
