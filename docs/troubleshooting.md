# 트러블슈팅 기록

## 2026-10-22 · 샌드박스 셸에서 외부 API 403
- 문제/재현: 작업용 샌드박스(클라우드·로컬 VM)에서 `curl https://api.coingecko.com/api/v3/ping`, `https://ko.wikipedia.org/w/api.php`
- 오류: `curl: (56) Received HTTP code 403 from proxy after CONNECT`
- 원인: 에이전트 실행 환경의 egress 허용 목록에 해당 호스트가 없음 (사용자 PC 자체 네트워크 문제 아님)
- 해결: 데스크톱 앱 내장 브라우저에서 API를 호출해 스냅샷 확보. 정식 수집은 사용자 PC 터미널에서 `python -m scripts.collect_coins` 실행
- 검증: 브라우저에서 `/ping` 200 `{"gecko_says":"(V3) To the Moon!"}`, markets 150건 수신
- 재발 방지: 수집 스크립트는 사용자 PC(일반 네트워크)에서 실행한다고 README에 명시

## 2026-10-22 · CoinGecko 상세 호출 429
- 문제/재현: 키 없이 `/coins/{id}` 를 6.5초 간격으로 연속 호출
- 오류: HTTP 429 Too Many Requests (약 3회 성공 후 반복)
- 원인: 키 없는 공개 API는 IP 단위 한도이고 교육장 공용 IP를 여러 사용자가 공유
- 해결: 429 시 Retry-After(없으면 65초) 대기 후 재시도, 5건마다 중간 저장, 실패 코인은 건너뛰고 다음 실행 때 재시도. 근본 해결은 Demo 키 발급 후 `.env` 설정
- 검증: 키 없이 실측 약 1건/분 성공 (150건 상세에 2시간 이상 소요 추정)
- 재발 방지: `.env.example`에 `COINGECKO_DEMO_API_KEY` 항목, 키 있으면 2초 간격 사용

## 2026-10-22 · 위키데이터 Special:EntityData 브라우저 fetch 실패
- 문제/재현: 브라우저에서 `https://www.wikidata.org/wiki/Special:EntityData/Q131723.json` fetch
- 오류: `TypeError: Failed to fetch` (CORS)
- 원인: 해당 경로는 CORS 헤더 없음
- 해결: `w/api.php?action=wbgetentities&origin=*` 사용
- 재발 방지: Python 수집(requests)은 CORS 영향 없음. 브라우저 측 호출에는 `origin=*` 필요

## 2026-10-22 · GMS 임베딩 403 "Target domain embeddings is not allowed"
- 문제/재현: 사용자 PC에서 `python -m scripts.index_docs` (GMS 임베딩 첫 호출)
- 오류: `openai.PermissionDeniedError: Error code: 403 - {'message': '[GMS 에러] Target domain embeddings is not allowed'}`
- 원인(오류 문구로 판단): GMS 는 `/gmsapi/` 뒤 첫 경로를 대상 도메인으로 읽는다. 기본 주소에 `api.openai.com` 이 빠져 `.../gmsapi/embeddings` 로 호출되면 대상 도메인이 `embeddings` 가 된다.
- 해결: 사용자가 `.env` 를 고쳐 해결. 현재 `OPENAI_BASE_URL` 은 `https://gms.ssafy.io/gmsapi/api.openai.com/v1` 형태(값은 출력하지 않고 형태만 확인)
- 검증: 사용자 PC에서 색인 진행 확인(사용자 보고)
- 재발 방지: `src/config.openai_base_url()` 이 `/gmsapi` 로 끝나는 주소에 `/api.openai.com/v1` 을 붙인다 (테스트 `test_gms_base_url_adds_openai_target`)

## 2026-10-22 · Windows 에서 tmp_path 테스트 23건 PermissionError
- 문제/재현: 사용자 PC(Windows)에서 `python -m scripts.agent_loop --review-only ...` 의 `pytest -q -p no:cacheprovider` 단계
- 오류: `ERROR tests/test_rag.py::... - PermissionError: [WinError ...]` → `20 passed, 23 errors` (tmp_path 를 쓰는 테스트 23건 전부, 준비 단계에서 실패)
- 원인(추정): pytest 공용 임시 폴더 `%TEMP%\pytest-of-<사용자>` 가 이전 Codex 샌드박스 실행 등 다른 권한으로 만들어져 현재 사용자가 쓸 수 없음. tmp_path 를 쓰지 않는 20건만 통과한 것과 일치
- 해결: `tests/conftest.py` 가 실행마다 `tempfile.mkdtemp()` 로 새 폴더를 만들어 `PYTEST_DEBUG_TEMPROOT` 로 지정 (하루 지난 이전 폴더는 정리). 프로젝트 안에 두는 `--basetemp` 방식은 삭제 실패·소유자 검사로 다른 환경에서 깨져 쓰지 않음
- 검증: 작업 환경에서 `-p no:cacheprovider` 유무 모두 45 passed, 연속 실행 시 충돌 없음. 사용자 PC 재실행 필요
- 재발 방지: 문제가 계속되면 `%TEMP%\pytest-of-<사용자>` 폴더를 지운다

## 2026-10-22 · agent_loop 출력 한글 깨짐
- 문제/재현: Windows 에서 `agent_loop` 가 실행한 `check_sample` 출력이 `�ؽ� �˰�����` 처럼 깨짐
- 원인: Windows 파이썬은 출력이 파이프일 때 cp949 로 쓰는데 루프는 UTF-8 로 읽음
- 해결: 자식 프로세스에 `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8` 전달
- 검증: 사용자 PC 재실행 필요

## 2026-10-22 · 백서 수집이 한 사이트에서 900초 대기
- 문제/재현: 사용자 PC에서 `python -m scripts.collect_whitepapers` 실행 중 특정 백서 사이트에서 멈춤
- 오류: `429 rate limited -> 900s 대기 후 재시도`
- 원인: 공통 HTTP 클라이언트가 429 응답의 `Retry-After`(900초)를 상한 없이 그대로 기다림. CoinGecko 처럼 꼭 받아야 하는 API 기준 동작이 사이트별로 건너뛰어도 되는 백서 수집에도 적용됨
- 해결: `PoliteClient(max_wait_sec=…)` 추가. 백서 클라이언트는 30초 넘게 기다리라고 하면 그 코인을 건너뛰고(기록하지 않아 다음 실행 때 재시도), 재시도 2회·타임아웃 20초 (`config/settings.json` `http.whitepaper_*`)
- 검증: `test_long_retry_after_is_skipped_not_waited` (900초 Retry-After 를 기다리지 않고 실패로 반환)
- 재발 방지: 건별로 건너뛰어도 되는 외부 호출은 대기 상한을 둔다

## 2026-10-22 · 백서 코인 질문이 500 "Error finding id"
- 문제/재현: 서버 실행 중 다른 터미널에서 `collect_whitepapers --prune` → `index_docs` 로 백서 청크를 추가한 뒤, 백서만 가진 코인(beldex·bittensor·ethena 등)에 질문
- 오류: `chromadb.errors.InternalError: Error executing plan: Internal error: Error finding id` (`During task with name 'retrieve'`), 화면에는 일반 500 문구
- 원인: Chroma 는 여러 프로세스의 동시 쓰기를 지원하지 않는다. 서버는 시작할 때 읽은 검색 인덱스를 메모리에 두는데, 그 뒤 다른 프로세스가 넣은 청크는 메타데이터(SQLite)에는 있고 서버의 메모리 인덱스에는 없어, 그 청크를 찾으려 할 때 실패한다. 위키 코인(서버 시작 전 색인)은 정상이라 증상과 일치
- 해결: 서버 재시작(메모리 인덱스 다시 읽기). 계속되면 서버를 끈 채 `python -m scripts.index_docs --rebuild`
- 재발 방지: 서버가 실행 중이면 `index_coins`·`index_docs` 가 실행을 거부(`data/chroma/.server.json` 의 주소에 접속되면 실행 중으로 판단). 이 오류가 나면 화면에 503 "서버를 다시 시작하세요" 안내. 테스트 3건
- 검증: 사용자 PC 서버 재시작 후 재질문 필요
