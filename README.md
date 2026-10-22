# Coin Lab — 코인 프로젝트 분석 RAG

CoinGecko 코인 메타데이터(시가총액 상위 150개)와 위키백과·백서 문서를 근거로, 코인 프로젝트에 대한 질문에
**근거 번호와 원문 출처를 붙여** 답하는 RAG 서비스입니다. SSAFY AI 코어 프로젝트 2회차 (RAG 기반 도메인 지식 서비스).

> 가상자산은 판단이 위험한 도메인입니다. 이 서비스의 답변은 문서 요약이며 투자 조언이 아닙니다.

## 제출 문서

| 산출물 (명세 6장) | 문서 |
|---|---|
| 요구사항 정의서 | [`docs/requirements_definition.md`](docs/requirements_definition.md) — 도메인 조건 충족 근거, 기능·비기능 요구사항 표 |
| RAG 파이프라인 설계문서 | [`docs/rag_pipeline_design.md`](docs/rag_pipeline_design.md) — 컬렉션·메타데이터, 수집·청킹·색인 흐름, 병합, 프롬프트, 설정값 이유, 근거 표시, 특화 기능, 문제와 해결 |
| 검증 결과 | [`docs/verification.md`](docs/verification.md) — 요구사항 대조표, 테스트 결과표, 셀프·상호 체크리스트, 제출 전 점검, 캡처 목록 |
| 구현 소스코드 | `src/`, `scripts/`, `web/`, `tests/` (아래 폴더 구조) |
| README | 해당 문서 |

## 기능

### 필수 (F2001 ~ F2012)
| 기능 | 내용 |
|---|---|
| 메타데이터 적재·색인 (F2001·F2002) | 코인 150개를 이름·한글명·순위·카테고리·해시 알고리즘·출시일·설명 텍스트로 만들어 `coin_meta` 에 코인당 1청크로 색인 (다시 색인해도 건수 불변) |
| 질문 기반 문서 수집 (F2003·F2004) | 프롬프트 1 이 질문에서 위키 검색어를 뽑고, 프롬프트 2 가 후보(제목·요약) 중 근거가 될 문서만 골라 본문 수집. 코인 자체 문서는 항상 색인, 이미 수집한 검색어·같은 질문은 다시 수집하지 않음 |
| 문서 색인 (F2005) | 1,000자 / 중복 200자(설정)로 나눠 `coin_docs` 에 색인, 청크 ID `코인:문서:순번` |
| 근거 검색·답변·표시 (F2006~F2008) | 메타데이터 근거 1 + 그 코인 문서 Top-k 6 → LangGraph retrieve·generate → 주장마다 `[근거 n]`, 실제 인용한 근거만 제목·출처 배지·원문 링크로 표시. 근거가 없으면 "확인되지 않습니다" |
| 코인 선택·질의응답 (F2009) | 메인 검색창·코인 리스트·왼쪽 목록에서 선택, 코인별 대화 기록 |
| 특화 기능 (F2010) | **리스크 브리핑**(합의·발행량·주요 사건·중앙화 요소) · **주장 팩트체크**(사실 / 사실 아님 / 문서로 확인 불가) — 모두 근거 표시 |
| 조건 탐색 (F2011) | "이더리움 위의 레이어2" 같은 자연어 조건 → 메타데이터 후보 → LLM 이 조건에 맞는 코인만 이유와 함께 |
| 진행 상태·안내 (F2012) | 수집 → 답변 단계 표시, 키·색인·연락처 누락과 서버 미연결 안내, 답변마다 면책 |

### 심화 (선택)
- **F2013 프론트엔드 직접 구현**: HTML·CSS·JavaScript 화면(`web/`)과 FastAPI 서버(`/api/*`) 분리
- **F2016 여러 문서 출처 결합**: 위키백과 + 백서(PDF·웹). PDF 는 쪽 단위로 나눠 근거에 "백서 PDF p.N" 표시, 출처 종류 배지로 구분
- F2014 MMR 은 설정 전환(`SEARCH_TYPE=mmr`)만 있고 비교 실험은 하지 않음, F2015 는 미선택

## 실행 방법

### 1) 환경 준비
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   /  macOS·Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env      # macOS·Linux: cp .env.example .env
```
`.env` 에 채울 값: `GMS_KEY`(필수), `CONTACT_EMAIL`(필수 — 위키미디어 User-Agent 연락처, 없으면 위키 문서를 수집하지 않음), `COINGECKO_DEMO_API_KEY`(권장)
- GMS 주소 기본값 `https://gms.ssafy.io/gmsapi/api.openai.com/v1` (채팅은 Responses API). 다른 주소는 `OPENAI_BASE_URL`.
- 모델: `CHAT_MODEL`(기본 `gpt-4.1-mini`), `EMBEDDING_MODEL`(기본 `text-embedding-3-small`).

### 2) 데이터 준비 (PC 의 일반 네트워크)
```bash
python -m scripts.collect_coins             # CoinGecko 150개 목록·상세·7일 가격 + 위키데이터 매핑 → data/coins.json
python -m scripts.collect_item_docs         # 코인 자체 위키 문서 (한국어 → 영어, 연결 없으면 검색)
python -m scripts.collect_whitepapers       # 위키 문서가 없는 코인의 백서 PDF·웹 (--prune: 잘못 받은 문서 정리)
python -m scripts.build_web_sample          # 서버 없이 볼 샘플 화면 데이터
python -m scripts.check_sample              # 항목 수·필드·출처 종류·자체 문서 보유 코인 점검
```
- 키 없는 CoinGecko 호출은 공용 IP 에서 429 가 잦습니다(약 1건/분). Demo 키를 넣으면 2초 간격.
- CoinGecko 이용 조건상 캐시는 24시간 안에 갱신해야 하므로 시연 전에 `collect_coins` 를 다시 실행하세요.
- 중간에 실패해도 받은 만큼 저장되고 다시 실행하면 이어서 받습니다.

### 3) 색인 (서버를 끈 상태에서)
```bash
python -m scripts.index_coins               # F2002 coin_meta (150청크)
python -m scripts.index_docs                # F2005 coin_docs
# 청크 설정 비교: CHUNK_SIZE=500 CHUNK_OVERLAP=100 python -m scripts.index_docs --rebuild
```
Chroma 는 여러 프로세스의 동시 쓰기를 지원하지 않아, 서버가 켜져 있으면 색인 스크립트가 실행을 거부합니다.

### 4) 서버와 화면
```bash
python -m src.server            # http://127.0.0.1:8000
```
- 질문하면 관련 문서를 수집·색인한 뒤 근거 번호를 붙여 답합니다. 설정값(`TOP_K`, `SEARCH_TYPE`, `CHUNK_SIZE` 등)은 `.env` 또는 `config/settings.json`.
- `web/index.html` 을 파일로 열면 서버 없이 **샘플 모드**(조회·키워드 탐색만).
- API 키 없이 흐름만 보려면 `LLM_PROVIDER=fake`, `EMBEDDING_PROVIDER=fake`.

| API | 설명 |
|---|---|
| `GET /api/status` | 색인 건수·모델·키·연락처 설정 여부·면책 문구 |
| `GET /api/coins`, `GET /api/coins/{id}` | 코인 목록·상세(수집된 문서 제목 포함) |
| `POST /api/coins/{id}/collect` `{question}` | 질문 기반 문서 수집·색인 → `{keywords, candidates, selected, skipped_keywords, added_titles, errors}` |
| `POST /api/ask` `{coin_id, question}` | 근거 기반 답변 → `{answer, sources[{index, title, url, source_type, source_label, page}], cited}` |
| `POST /api/coins/{id}/brief` · `/factcheck` `{claim}` | 리스크 브리핑 · 주장 팩트체크 (응답 형식은 `/api/ask` 와 같음) |
| `POST /api/recommend` `{query}` | 조건 탐색 → `{results[{coin_id, label, reason, …}]}` |

### 5) 테스트
```bash
python -m pytest -q       # 65건, 네트워크·API 키 불필요 (가짜 LLM·임베딩·위키)
```

## 데이터 준비와 색인 절차 요약

1. CoinGecko 목록·상세 → 정규화(`data/coins.json`) → 색인 텍스트 → `coin_meta`
2. 코인 자체 문서: 위키데이터 연결 문서 → 위키 검색 → 백서. 자체 문서가 있는 코인 102 / 150, 나머지는 CoinGecko 설명만
3. 질문할 때: 프롬프트 1 검색어 → 위키 후보 → 프롬프트 2 선별 → 본문 수집 → 즉시 `coin_docs` 색인
4. 같은 검색어·같은 질문은 `data/docs/manifest.json` 기록으로 다시 수집하지 않음

## 데이터 출처와 이용 조건

| 출처 | 용도 | 이용 조건 | git |
|---|---|---|---|
| [CoinGecko API](https://www.coingecko.com/en/api) | 코인 메타데이터·시세·7일 가격·로고 URL·백서 링크 | "Data provided by CoinGecko" 표기, 저장 비권장·24시간 내 갱신, 로고는 URL 로만 | 제외 |
| [Wikidata](https://www.wikidata.org) | 코인 ↔ 위키 문서 연결 | CC0 | 포함 |
| [한국어 위키백과](https://ko.wikipedia.org) · [English Wikipedia](https://en.wikipedia.org) | 외부 설명 문서 | CC BY-SA 4.0, 제목·원문 URL 표시 | 포함 |
| 프로젝트 백서 (PDF·웹) | 위키 문서가 없는 코인의 설명 문서 | 저작권은 각 프로젝트 — 교육용 근거 인용, 원문 URL·파일명·쪽 표시 | 제외 |

자세한 수집 방법·검증 수치·검토 결과: [`docs/data_sources.md`](docs/data_sources.md)

## 폴더 구조

```
config/settings.json        청킹·Top-k·컬렉션·경로·호출 간격·수집 한도
src/config.py               설정·환경변수 로더
src/data_prep/              도메인 의존: CoinGecko·위키·백서 클라이언트, 정규화·색인 텍스트, 문서 저장, 프롬프트
src/vectorstore/store.py    임베딩·Chroma 컬렉션·청킹·색인
src/rag/                    LLM 호출, 질문 기반 수집(collect), 근거 검색·병합(retrieve), LangGraph(graph)
src/service/recommend.py    조건 기반 코인 탐색
src/server.py               FastAPI 서버 (API + 화면)
scripts/                    수집·색인·점검 스크립트, 개발용 자동 검증 루프(agent_loop)
web/                        HTML·CSS·JS 화면 (DESIGN.md 기준), web/sample/ 샘플 데이터(git 제외)
tests/                      자동 테스트 65건
data/                       coins.json·raw(git 제외), source_map.json, docs/wikipedia(포함)·whitepaper(제외), chroma(제외)
docs/                       제출 문서와 개발 기록 (아래)
```

### 문서 지도

| 문서 | 내용 |
|---|---|
| `docs/requirements_definition.md` · `rag_pipeline_design.md` · `verification.md` | 제출 문서 3종 |
| `docs/requirements.md` | 명세 원문의 조건·확인 항목 정리 (검증 기준) |
| `docs/data_sources.md` | 데이터 출처·이용 조건·수집 규칙·검증 수치 |
| `docs/decisions.md` | 기술 결정과 근거 (D1~D16) |
| `docs/troubleshooting.md` | 오류·원인·해결 이력 |
| `docs/progress.md` | 작업 진행 기록 |
| `DESIGN.md` | 화면 디자인 기준 |
| `AGENTS.md` · `CLAUDE.md` · `docs/review_request.md` | 개발 방식: Claude 구현 · Codex 검증 지침 |

## 개발 방식

구현은 Claude, 검증은 Codex 가 맡았습니다 (`AGENTS.md`). `python -m scripts.agent_loop "<작업>"` 이 Claude 구현 → 테스트 → Codex 검증 → FAIL 이면 수정(최대 3회)을 자동으로 이어서 실행하고, `--review-only` 는 검증만 합니다. 검증 기록은 `docs/reviews/`(git 제외)에 남습니다.
