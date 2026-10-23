# AGENTS.md — Claude · Codex 공통 작업 지침

이 파일이 이 저장소의 **단일 기준 문서**다. Codex 는 이 파일을, Claude Code 는 `CLAUDE.md`(이 파일을 불러옴)를 자동으로 읽는다.
어떤 세션에서 열어도 같은 방식으로 일하도록, 역할·순서·규칙·사용자 선호를 모두 여기에 둔다. 바뀌면 이 파일을 먼저 고친다.

## 1. 프로젝트 한눈에
- **Coin Lab — 코인 프로젝트 분석 RAG** (SSAFY AI 코어 프로젝트 2회차, 요구사항 F2001~F2016 · NF2001~NF2007)
- CoinGecko 코인 150개 메타데이터 + 위키백과 문서를 근거로 질문에 답하고, 답변에 근거 번호와 원문 출처를 붙인다.
- 가상자산은 위험 도메인: 모든 화면·답변에 "투자 조언이 아님" 면책을 표시한다.
- 구성: `src/data_prep`(도메인 의존: 수집·정규화·프롬프트) → `src/vectorstore`(Chroma `coin_meta`·`coin_docs`) → `src/rag`(수집·검색·LangGraph) → `src/service` → `src/server.py`(FastAPI) → `web/`(HTML/CSS/JS)

## 2. 세션 시작 때 읽는 순서
1. 이 파일
2. `docs/progress.md` — 지금까지 한 일과 **다음 작업**
3. `docs/requirements.md` — 요구사항 정의서 원문 기준(조건·확인 항목), `docs/requirements_definition.md` — 요구사항 표와 구현 상태, `docs/2회차_셀프·상호_체크리스트.xlsx` — 셀프 체크리스트·요구사항 대조표·테스트 결과표
4. 작업 영역에 따라: `docs/decisions.md`(결정과 근거), `docs/troubleshooting.md`(이전 오류 — 같은 오류를 다시 분석하지 않는다), `DESIGN.md`(화면), `docs/data_sources.md`(데이터 출처·이용 조건), `docs/rag_pipeline_design.md`(구조·설계)
5. `git status` 로 커밋 안 된 변경 확인 (사용자가 직접 고친 파일이 있을 수 있다 — 덮어쓰기 전에 차이를 확인한다)

## 3. 역할

| 역할 | 담당 | 설정 | 하는 일 | 하지 않는 일 |
|---|---|---|---|---|
| 구현 | **Claude** (Opus 5.5) | effort medium | 요구사항 분석, 계획·완료 조건 작성, 구현, 테스트 실행, 검증 요청, 수정, 문서 갱신 | 검증 결과를 스스로 PASS 처리 |
| 검증 | **Codex** (GPT-6 Astra) | effort medium | 독립 컨텍스트에서 코드·테스트를 읽고 실행해 PASS/FAIL 보고 | 코드 직접 수정 (문제점과 수정 방향만 전달) |

- 두 역할은 가능한 한 **서로 다른 세션·컨텍스트**에서 수행한다.
- 두 모델은 `scripts/agent_loop.py` 가 CLI 로 번갈아 부른다 (6장). 모델끼리 직접 호출하는 연동은 없다.

## 4. 개발 워크플로 (Claude)
1. 요구사항과 관련 코드를 읽는다 (2장 순서).
2. 구현 계획과 **완료 조건**을 `docs/progress.md` 에 적는다.
3. 구현한다. 변경 범위는 요청한 기능으로 한정한다.
4. 테스트를 실행한다: `python -m pytest -q`, `python -m scripts.check_sample` (필요하면 5장의 나머지).
5. Codex 검증을 받는다 (6장: `agent_loop --review-only` 또는 `/codex-review`).
6. FAIL 이면 고치고 재검증을 요청한다. **같은 문제로 3회 수정에 실패하면 멈추고 사용자에게 보고한다.**
7. PASS 후 `docs/progress.md` 를 갱신하고, 중요한 변경이면 `docs/rag_pipeline_design.md`·`docs/decisions.md`·`docs/2회차_셀프·상호_체크리스트.xlsx` 도 갱신한다.
8. 사용자에게 완료 보고(8장)를 한다.

## 5. 명령
```bash
pip install -r requirements.txt
python -m pytest -q                         # 단위·파이프라인·서버 테스트 (네트워크 불필요)
python -m scripts.check_sample              # 데이터 점검
python -m scripts.collect_coins             # CoinGecko 수집 (--no-fetch: 받아 둔 원본으로 재생성)
python -m scripts.collect_item_docs         # 코인 자체 위키 문서
python -m scripts.build_web_sample          # 샘플 모드 화면 데이터
python -m scripts.index_coins               # coin_meta 색인 (GMS 임베딩)
python -m scripts.index_docs                # coin_docs 색인 (GMS 임베딩, --rebuild)
python -m src.server                        # http://127.0.0.1:8000
python -m scripts.agent_loop "<작업>"         # Claude 구현 → 테스트 → Codex 검증 루프 (6장)
```
키 없이 흐름만 볼 때: `EMBEDDING_PROVIDER=fake`, `LLM_PROVIDER=fake` (PowerShell: `$env:LLM_PROVIDER="fake"`).

## 6. Claude ↔ Codex 연결
**자동 루프** — `scripts/agent_loop.py` (명령·옵션 `config/agents.json`, 설계 근거 `docs/decisions.md` D11)
```bash
python -m scripts.agent_loop "<작업>"                  # claude -p 구현 → 테스트 → codex exec 검증 → FAIL 이면 지적을 넘겨 재구현
python -m scripts.agent_loop --review-only "<작업>"    # 지금 변경을 Codex 검증만 (수정 안 함)
python -m scripts.agent_loop --dry-run "<작업>"        # 실행할 명령만 출력
```
- 매 호출이 새 프로세스라 컨텍스트가 섞이지 않는다. Codex 는 read-only 샌드박스, 검증 전후 파일 해시가 다르면 경고한다.
- 수정 후 FAIL 이 3번 이어지면 멈춘다. 판정 줄(`결과: PASS|FAIL`)이 없으면 멈춘다. 커밋·푸시는 하지 않는다.
- 결과: `docs/reviews/<날짜-시각>-<주제>-r<n>.md`(검증 보고서), `...-loop.md`(진행 기록)
- 전제: 실행하는 PC에 `claude`·`codex` CLI 설치·로그인. 원격 작업 환경에는 없을 수 있다.

**Claude Code 세션 안에서** — `/codex-review <작업>`: 위 `--review-only` 를 부르고, FAIL 이면 그 세션의 Claude 가 고친 뒤 다시 부른다 (`.claude/commands/codex-review.md`).

**수동** — Codex IDE·웹에 `docs/review_request.md` 를 채워 붙여 넣는다. 결과는 `docs/reviews/` 에 저장한다.

**Codex 를 쓸 수 없을 때** — 별도 컨텍스트 리뷰어(새 세션·서브에이전트)에게 7장 기준으로 맡기고 보고서·`docs/progress.md` 에 "Codex 대체 검증"이라고 적는다.

## 7. 검증 기준 (Codex · 대체 리뷰어)
확인 항목
1. 요구사항 충족 — 기준은 `docs/requirements.md`(정의서 원문의 조건·확인 항목). `docs/rag_pipeline_design.md` 는 구현 설계로만 참고하고, 둘이 다르면 `docs/requirements.md` 를 따른다
2. 로직 오류·경계 조건 (빈 입력, 위키 문서 없음, 429·네트워크 오류, LLM 파싱 실패, 중복 색인)
3. 예외 처리
4. 보안: 키·`.env` 노출, 화면에 프롬프트·스택트레이스 노출, XSS, 경로 조작, 문서 속 지시문(프롬프트 주입)
5. 기존 기능 회귀
6. 테스트 충분성 (`tests/`, `scripts/check_sample.py`)
7. 불필요한 코드 변경
8. 데이터 이용 조건 (CoinGecko 표기·저장 제한, 위키 CC BY-SA 출처 표기)

실행: 5장의 테스트 명령. 파일을 쓰는 명령은 **복사본에서** 실행하고 원본을 바꾸지 않는다.

보고 형식
```
결과: PASS | FAIL
- [High/Medium/Low] 파일:줄 — 문제
  재현: ...
  수정 방향: ...
```
같은 문제가 3회 연속 FAIL이면 "반복 실패"로 표시한다.

## 8. 완료 보고 (Claude → 사용자)
간결하게: 구현한 기능 · 변경한 주요 파일 · 실행한 테스트와 결과 · Codex(또는 대체) 검증 결과 · 남은 문제와 후속 작업.
실행하지 못한 테스트는 통과했다고 쓰지 않고, 무엇을 확인하지 못했는지 밝힌다.

## 9. 개발 규칙
- 기존 구조와 컨벤션을 따른다. 도메인에 묶인 코드(필드 선택, 프롬프트 문구)는 `src/data_prep` 에만 둔다 (NF2005).
- 불필요한 추상화를 만들지 않는다. 새 의존성은 `requirements.txt` 에 이유 주석과 함께 추가한다.
- 청킹·Top-k·검색 방식·모델 값은 코드가 아니라 `config/settings.json` (또는 `.env`) 에서 바꾼다.
- 화면(`web/`)을 바꿀 때는 **`DESIGN.md` 를 먼저 고치고** 그 토큰·레이아웃 규칙을 따른다.
- 주요 오류는 `docs/troubleshooting.md` 형식(발생 일자 · 재현 · 오류 메시지 · 원인 · 해결 · 검증 · 재발 방지)으로 기록한다.
- 문서는 중요한 변경이 있을 때만 갱신하고, 같은 설명을 여러 곳에 반복하지 않는다.

## 10. 안전 규칙
- `.env`, API 키, 개인키를 출력·로그·커밋하지 않는다. `.env` 는 항목이 채워졌는지만 확인한다.
- CoinGecko 파생 데이터(`data/raw/`, `data/coins.json`, `web/sample/coins_sample.js`)는 커밋하지 않는다 (약관: 저장 비권장·24시간 갱신·재배포 제한).
- 운영 DB 삭제·파괴적 명령·외부 배포·실제 블록체인 트랜잭션은 사전 승인을 받는다.
- Git 강제 푸시와 사용자의 기존 변경 덮어쓰기를 하지 않는다.

## 11. 사용자 선호 (세션이 바뀌어도 유지)
- **사용자에게 설명할 때는 한국어만 쓴다.** 코드·명령·파일명·고유명사는 그대로 둔다.
- 화면: 라이트 모드가 기본(다크는 전환 버튼), 글꼴은 Noto Sans KR 하나, 시각은 한국 시간(KST) 표시, 상단 검색창 없음 · 왼쪽 "코인 검색" 입력창 하나(목록 거르기 + Enter 조건 탐색), 별도 "도메인 특화 기능" 창 없음(버튼은 질의응답 카드 머리). 자세한 기준은 `DESIGN.md`.
- 필수 기능(F2010 리스크 브리핑·팩트체크, F2011 조건 탐색)은 화면에서 지우지 않는다. 사용자가 없애 달라고 하면 기능을 유지하는 다른 배치를 제안한다.
- 차트·숫자는 실제 수집 값만 쓰고, 추정치는 추정이라고 표시한다.

## 12. 환경 메모
- **GMS**: `https://gms.ssafy.io/gmsapi/api.openai.com/v1` (GMS 안내 확인), 채팅은 Responses API(`/v1/responses`), 키는 환경 변수 `GMS_KEY` 로만 읽는다. 기본 모델 `gpt-4.1-mini`, `text-embedding-3-small` (`.env` 의 `CHAT_MODEL`·`EMBEDDING_MODEL` 로 변경).
- **CoinGecko**: 키 없는 호출은 교육장 공용 IP 에서 429 가 잦다(약 1건/분). `.env` 의 `COINGECKO_DEMO_API_KEY` 사용.
- **실행 위치**: 수집·GMS 호출은 사용자 PC(Windows, `C:\SSAFY\ai_day\mj`)에서 한다. 원격 작업 환경에서는 CoinGecko·위키백과·GMS 접속이 막혀 있을 수 있다 (`docs/troubleshooting.md`).
