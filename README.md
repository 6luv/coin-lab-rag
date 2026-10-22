# Coin Lab — 코인 프로젝트 분석 RAG

CoinGecko 코인 메타데이터(시가총액 상위 150개)와 위키백과·백서 문서를 근거로, 코인 프로젝트에 대한 질문에
**근거 번호와 원문 출처를 붙여** 답하는 RAG 서비스입니다.

> 가상자산은 판단이 위험한 도메인입니다. 이 서비스의 답변은 문서 요약이며 투자 조언이 아닙니다.

진행 상황과 다음 작업은 [`docs/progress.md`](docs/progress.md), 요구사항별 설계와 상태는 [`docs/plan.md`](docs/plan.md)를 보세요.

## 폴더 구조

```
config/settings.json        청킹·Top-k·컬렉션·경로·호출 간격 설정
src/config.py               설정·환경변수 로더
src/data_prep/              도메인 의존 코드: CoinGecko·위키 클라이언트, 항목 정규화·색인 텍스트, 문서 저장, 프롬프트
src/vectorstore/store.py    임베딩·Chroma 컬렉션·청킹
src/rag/                    LLM 호출, 질문 기반 수집(collect), 근거 검색·병합(retrieve), LangGraph(graph)
src/service/recommend.py    조건 기반 코인 탐색
src/server.py               FastAPI 서버 (API + 화면 제공)
scripts/                    수집·색인·점검 스크립트 (아래 실행 방법)
data/coins.json             정규화된 코인 150건 (로컬 전용 · git 제외)
data/source_map.json        코인 → 위키데이터·위키백과 매핑과 사람 검토 결과
data/docs/wikipedia/        수집한 위키 문서 ({coin_id}_{doc_id}.json) + manifest.json (CC BY-SA 4.0)
data/docs/whitepaper/       수집한 백서 텍스트 (PDF 는 쪽 단위, 저작권은 각 프로젝트 · git 제외)
web/                        HTML/CSS/JS 화면, web/sample/ 샘플 모드 데이터 (git 제외)
tests/                      단위·파이프라인·서버·자동 루프 테스트
docs/                       계획·데이터 출처·아키텍처·결정·진행·트러블슈팅, docs/reviews/ 검증 기록
DESIGN.md                   화면 디자인 기준 (색·글꼴·레이아웃·컴포넌트)
AGENTS.md                   Claude(구현) · Codex(검증) 공통 지침 — CLAUDE.md 가 불러옴
config/agents.json          자동 호출 루프의 CLI 명령·옵션
scripts/agent_loop.py       Claude ↔ Codex 자동 호출 루프
.claude/commands/           Claude Code 슬래시 명령 (/codex-review)
```

## 실행 방법

### 1) 환경 준비
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   /  macOS·Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env      # macOS·Linux: cp .env.example .env
```
`.env`에 채울 값: `GMS_KEY`, `CONTACT_EMAIL`(필수, 위키미디어 User-Agent용 — 없으면 위키 문서를 수집하지 않음), `COINGECKO_DEMO_API_KEY`(권장)
- GMS 주소는 GMS 안내에 따라 `https://gms.ssafy.io/gmsapi/api.openai.com/v1`을 기본으로 쓰고(채팅은 `/v1/responses`), 키는 환경 변수 `GMS_KEY`로만 읽습니다. 다른 주소를 쓰려면 `OPENAI_BASE_URL`에 적습니다.
- 모델은 `CHAT_MODEL`(기본 `gpt-4.1-mini`), `EMBEDDING_MODEL`(기본 `text-embedding-3-small`)로 바꿀 수 있습니다.

### 2) 데이터 수집 (PC의 일반 네트워크에서 실행)
```bash
python -m scripts.collect_coins             # 코인 150개 목록·상세·위키 매핑 → data/coins.json
python -m scripts.collect_coins --no-fetch  # API 호출 없이 받아 둔 원본으로 coins.json 만 다시 만들기
python -m scripts.collect_item_docs         # 코인 자체 위키 문서 (한국어 우선 → 영어, 연결 없는 코인은 검색)
python -m scripts.collect_whitepapers       # 위키 문서가 없는 코인의 백서(PDF·웹) (F2016, git 제외)
python -m scripts.build_web_sample          # 화면 샘플 데이터 갱신
```
- CoinGecko 키 없는 호출은 공용 IP에서 429가 잦습니다(실측 약 1건/분). Demo 키를 넣으면 2초 간격으로 받습니다.
- CoinGecko 약관상 캐시는 24시간 안에 갱신해야 하므로 시연 전에 `collect_coins`를 다시 실행하세요.
- 중간에 실패해도 받은 만큼 저장되고, 다시 실행하면 이어서 받습니다.

### 3) 점검 (네트워크·키 불필요)
```bash
python -m pytest -q
python -m scripts.check_sample
```

### 4) 색인
```bash
python -m scripts.index_coins               # F2002 coin_meta
python -m scripts.index_docs                # F2005 coin_docs
# 키 없이 흐름만 확인: EMBEDDING_PROVIDER=fake  (PowerShell: $env:EMBEDDING_PROVIDER="fake")
# 청크 설정 비교: CHUNK_SIZE=500 CHUNK_OVERLAP=100 python -m scripts.index_docs --rebuild
```

### 5) 서버 + 화면
```bash
python -m src.server            # http://127.0.0.1:8000 접속
```
- 서버가 `web/` 화면과 `/api/*`를 함께 제공합니다. 질문하면 관련 위키 문서를 수집·색인한 뒤 근거 번호를 붙여 답합니다.
- 키 없이 흐름만 보려면 `LLM_PROVIDER=fake`, `EMBEDDING_PROVIDER=fake` (답변 내용은 의미 없음).
- `web/index.html`을 파일로 직접 열면 서버 없이 **샘플 모드**(조회·키워드 탐색만)로 동작합니다.
- 동작: 코인 목록·검색·카테고리 필터, 코인 위젯(로고·가격·차트·통계), 프로젝트 정보, 키워드 조건 탐색, 라이트/다크 전환
- 차트: 24H·7D 는 CoinGecko 시간별 가격, 30D 는 변동률로 역산한 추정치(점선). 시각은 모두 한국 시간(KST)
- 서버 연결 시 추가: 근거 기반 질의응답, 리스크 브리핑, 주장 팩트체크, LLM 조건 탐색

| API | 설명 |
|---|---|
| `GET /api/status` | 색인 건수·모델·키 설정 여부·면책 문구 |
| `GET /api/coins`, `GET /api/coins/{id}` | 코인 목록·상세(수집된 문서 제목 포함) |
| `POST /api/coins/{id}/collect` `{question}` | 질문 기반 문서 수집·색인 (F2003·F2004) |
| `POST /api/ask` `{coin_id, question}` | 근거 기반 답변 `{answer, sources, cited}` (F2006~F2008) |
| `POST /api/coins/{id}/brief`, `/factcheck` `{claim}` | 리스크 브리핑·주장 팩트체크 (F2010) |
| `POST /api/recommend` `{query}` | 조건 기반 탐색 (F2011) |

## 데이터 출처

| 출처 | 용도 | 이용 조건 |
|---|---|---|
| [CoinGecko API](https://www.coingecko.com/en/api) | 코인 메타데이터·시세·7일 가격·로고 URL | "Data provided by CoinGecko" 표기, 저장 비권장·24시간 내 갱신 → 원본·정규화본 git 제외, 로고는 URL로만 사용 |
| [Wikidata](https://www.wikidata.org) | 코인 ↔ 위키 문서 연결 | CC0 |
| [한국어 위키백과](https://ko.wikipedia.org) · [English Wikipedia](https://en.wikipedia.org) | 외부 설명 문서 | CC BY-SA 4.0, 제목·원문 URL 표시 |

수집 방법·검증 수치·오매칭 검토 결과는 [`docs/data_sources.md`](docs/data_sources.md)에 있습니다.
빗썸 공식 Open API는 시세·주문 기능만 있고 프로젝트 설명·백서 엔드포인트가 없어 보조 출처(원화 상장 여부·유의 종목) 후보로만 검토 중입니다.

## 개발 방식

구현은 Claude, 검증은 Codex가 맡습니다. 역할·순서·규칙은 [`AGENTS.md`](AGENTS.md) 하나에 모아 두었습니다.

```bash
python -m scripts.agent_loop "F2014 MMR 비교 실험"            # Claude 구현 → 테스트 → Codex 검증 → FAIL 이면 수정 (최대 3회)
python -m scripts.agent_loop --review-only "인덱싱 복구 수정"   # 지금 변경을 Codex 검증만
python -m scripts.agent_loop --dry-run "..."                  # 실행할 명령만 확인
```
- 필요: `claude`(Claude Code CLI), `codex`(Codex CLI)가 설치·로그인돼 있어야 합니다. 명령·모델·옵션은 `config/agents.json`에서 바꿉니다.
- Claude Code 세션 안에서는 `/codex-review <작업 설명>` 으로 같은 검증을 부를 수 있습니다.
- 결과는 `docs/reviews/`에 남고, 커밋은 사람이 확인한 뒤 합니다.
