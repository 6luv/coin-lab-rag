# 데이터 출처 · 라이선스 · 수집 방법 (NF2006 · NF2007)

검증 일시: 2026-10-22 00:32 UTC (09:32 KST) · 검증 방법: 실제 API 호출 결과로 확인 (아래 수치는 모두 실측)

## 1. 출처 요약

| 출처 | 용도 | 엔드포인트 | 이용 조건(요약) | 저장 위치 | git |
|---|---|---|---|---|---|
| **CoinGecko API v3** (공개/Demo) | 항목 메타데이터 150건 (F2001) | `/ping`, `/coins/markets`, `/coins/{id}` | 화면에 **"Powered by CoinGecko"**(또는 "Data provided by CoinGecko") 표기, 데이터 **저장 비권장·캐시 시 24시간 내 갱신**, API 접근 재배포 금지, 한도 준수 | `data/raw/coingecko_raw.json`(원본), `data/coins.json`(정규화) | raw 제외 |
| **CoinGecko 로고 이미지** | 코인 아이콘 표시 (화면) | markets `image`, 상세 `image.small` (`coin-images.coingecko.com`) | URL 만 저장하고 이미지는 화면에서 바로 불러옴(파일 저장·재배포 안 함). 로고는 각 프로젝트의 상표이므로 식별 용도로만 사용, CoinGecko 표기로 출처 갈음 | `data/coins.json`의 `image` | 제외(coins.json) |
| **Wikidata** | 코인 ↔ 위키 문서 연결 | `w/api.php` (`haswbstatement:P5777`, `wbgetentities`) | CC0 (출처 표기 의무 없음, 표기 권장) | `data/source_map.json` | 포함 |
| **한국어 위키백과** | 외부 설명 문서 (F2004) | `ko.wikipedia.org/w/api.php` (search, extracts) | **CC BY-SA 4.0** — 제목·원문 URL 표시, 변경 시 동일 조건 | `data/docs/wikipedia/*.json` | 포함 가능(라이선스 표기) |
| **English Wikipedia** | 한국어 문서가 없을 때 폴백 | `en.wikipedia.org/w/api.php` | CC BY-SA 4.0 | 같은 위치 | 포함 가능 |
| **프로젝트 백서(PDF/웹)** | 위키 자체 문서가 없는 코인의 자체 문서 (F2004 · F2016) | CoinGecko `links.whitepaper` URL (`scripts/collect_whitepapers.py`, 질문 시 대체 수집) | 저작권은 각 프로젝트 — 교육용 검색 근거로만 인용, 근거에 원문 URL·파일명·쪽 표시, 원문 재배포 안 함. 1초 간격·재시도·20MB 상한·User-Agent 식별 | `data/docs/whitepaper/*.json` | **제외** |

- CoinGecko 약관: <https://www.coingecko.com/en/api_terms> · 표기 가이드: <https://brand.coingecko.com/resources/attribution-guide> · 한도: <https://docs.coingecko.com/docs/common-errors-rate-limit>
- 위키미디어: 라이선스 <https://ko.wikipedia.org/wiki/위키백과:저작권>, API 이용 정책상 연락처가 포함된 User-Agent 필요 (`.env`의 `CONTACT_EMAIL`)
- 본 문서는 법률 자문이 아니며, 과제 범위(학습용·비상업) 기준의 요약이다. 공개 배포 전에는 원문 약관을 다시 확인한다.

## 2. 실재 여부 검증 결과 (2026-10-22)

### 2-1. CoinGecko — ✅ 100건 이상 확보
| 항목 | 결과 |
|---|---|
| `/ping` | 200 `{"gecko_says":"(V3) To the Moon!"}` |
| `/coins/markets` (시총 순, per_page=150) | **150건** 수신 (1위 Bitcoin ~ 150위 Conflux) |
| `/coins/markets` `sparkline=true` | 코인별 7일 시간별 가격(약 168점) — 화면 24H·7D 차트용, 같은 호출 1번으로 150개 모두 |
| `/coins/{id}` 상세 (카테고리·출시일·해시 알고리즘·설명·백서 링크) | **33건** 수신 — 키 없는 호출이 공용 IP에서 429 반복(실측 약 1건/분). Demo 키로 `collect_coins` 실행 시 나머지 확보 |
| 설명 보유 | 56건 (CoinGecko 설명 31 + 위키데이터 한 줄 설명 25) — 상세를 받았어도 설명이 없는 코인 있음(예: LEO) |

### 2-2. 프로젝트별 설명 문서 — 🟡 일부 코인만 존재 (보완 계획 필요)
| 구분 | 건수 (150 중) | 비고 |
|---|---|---|
| 위키데이터 항목 연결 | 44 | P5777=CoinGecko id 26 · P5777=이름 slug 6 · 라벨 검색+설명 필터 12 |
| **한국어 위키백과 문서** | **18** | 위키데이터 연결 17 + 검색 후보 검토 1(XRP 레저). 본문 합계 약 7만 자 |
| **영어 위키백과 문서** | **40** | 위키데이터 연결 34 + 검색 후보 검토 8 − 발행사 문서로 판정 2(KuCoin, USD1). 본문 합계 약 30만 자 |
| 위키 문서 없음 | 110 | 스테이블코인·토큰화 펀드·신규 토큰이 대부분 |
| CoinGecko 백서 링크 | 상세 수신 33건 중 32건 보유 | `collect_whitepapers` 로 실제 수집해 확인 (PDF 23 · 웹 39건, 뷰어 화면 등 잘못 받은 것은 `--prune` 으로 제외, D16) |

검색 후보와 라벨 검색으로 붙은 위키데이터 연결은 문자열 일치만으로는 오매칭이 있어 **사람이 검토**한 결과를 `source_map.json`의 `candidate_review`(검색 후보)·`link_review`(위키데이터 연결)에 남겼다.
검토 규칙: 문서가 토큰의 프로토콜·플랫폼 자체를 다루면 accept, 별개의 발행사·거래소·회사 문서면 related(항목 자체 문서로 쓰지 않고 질문 기반 수집 후보로만 사용).
- accept 8: BNB→BNB Smart Chain, XRP→XRP Ledger/XRP 레저, Chainlink, Stellar, Dai, Sui, Hedera, Cosmos Hub→Cosmos (network)
- related(발행사·원작 문서, 항목 자체 문서로 쓰지 않음) 검색 후보 7: Tether Gold→Tether, PayPal USD→PayPal, Pepe→Pepe the Frog, Bitget Token→Bitget, Aptos→Aptos Labs, NEXO→Nexo (company), KuCoin(한국어 후보) / 위키데이터 연결 2: KuCoin→KuCoin 거래소, USD1→World Liberty Financial
- 위키데이터 연결 accept 7: Uniswap, Worldcoin, Polkadot, Pyth, World Liberty Financial(WLFI), Pump.fun, Pudgy Penguins
- reject 2: Rain(제목은 일치하지만 다른 회사), Canton→Canton of Zug
- 시사점: 프롬프트2(후보 선별)는 제목 일치가 아니라 **요약문과 코인 설명을 함께 보고** 같은 대상인지 판단해야 한다.

### 2-3. 수집 결과 (최소 가동 샘플)
- `data/docs/wikipedia/` 40건 = 한국어 18 + 영어 22 (코인당 1건, 한국어 우선), 본문 합계 약 18.5만 자, `manifest.json` 키워드 40개
- `check_sample` 근사 청크 수 240개 (1,000자/200자, langchain 미설치 시 근사치)

### 2-4. 결론과 대응
- 항목 메타데이터 조건(약 100건 이상): **충족**
- 항목별 설명 문서 조건: 위키백과만으로는 40/150. 다음 순서로 보완한다.
  1. 대표 시연 코인은 한국어 문서가 있는 코인으로 선정 (비트코인·이더리움·테더·USDC·트론·도지코인·모네로·카르다노·비트코인캐시·라이트코인·유니스왑·이더리움 클래식·알고랜드 등)
  2. 영어 위키백과 폴백 (출처 유형 `wikipedia_en`으로 구분 표시)
  3. CoinGecko 설명문을 항목 메타데이터 근거로 항상 포함 (F2006)
  4. 백서 PDF를 별도 출처 유형으로 수집 (F2016)
  5. 그래도 문서가 없는 코인은 "문서로 확인되지 않습니다"로 답하는 것이 정상 동작임을 검증 항목(4.3)으로 보여준다

## 3. 수집 방법

| 단계 | 스크립트 | 호출 규칙 (NF2006) | 재수집 방지 (NF2002) |
|---|---|---|---|
| 코인 목록·상세·매핑 | `python -m scripts.collect_coins` | CoinGecko 키 없음 6.5초/키 있음 2초 간격, 429 → 65초 대기(또는 Retry-After) 후 최대 4회 재시도, 5건마다 중간 저장, 실패한 코인은 건너뛰고 다음 실행 때 재시도 | 상세는 24시간 이내 받은 것은 건너뜀 (`--refresh`로 강제) |
| 항목 자체 문서 | `python -m scripts.collect_item_docs` | 위키 0.5초 간격, User-Agent에 프로젝트명·연락처(없으면 실행 거부), 5xx/네트워크 오류 재시도 | `data/docs/manifest.json`에 `item:{lang}:{title}` 키워드 기록. 위키데이터 연결이 없는 코인은 위키백과 검색(ko "{한글명} 암호화폐" → en "{name} cryptocurrency")으로 자체 문서를 찾고 `item:search` 로 기록 (제목 = 코인 이름·한글명·심볼, 괄호 설명이나 요약에 암호화폐 단서가 있을 때만 채택, 문서의 `search_query` 가 `item:search:…`) |
| 질문 기반 문서 | `src/rag/collect.py` (화면에서 질문할 때) | 위와 동일 | manifest 키워드 |

이번 초기 수집은 작업 환경의 셸이 외부 API에 막혀(403, `docs/troubleshooting.md`) **데스크톱 앱 내장 브라우저에서 같은 API를 호출**해 받았다.
- 코인 메타데이터·매핑: 결과를 SHA-256으로 대조해 저장 (markets+상세+매핑 `3ae855b6…`, 매핑 `88e3bceb…` 일치)
- 위키 문서 40건: 브라우저가 `collect_item_docs`와 같은 규칙(한국어 우선 → 영어)으로 받은 묶음 파일을 프로젝트의 `docs_store.save_doc`으로 저장 (manifest·라이선스 필드 동일). 이후 갱신은 `collect_item_docs`로 한다.
- 스냅샷 전용 필드: `source_map.json`의 `page_id/chars/lastrevid`, `search_candidate_*`는 이번 검증 때만 기록했다. `collect_coins`가 새로 매핑하는 코인은 `{title, url}`만 남긴다.

### 백서 수집 규칙 (F2016)
- 대상: 위키 자체 문서(위키데이터 연결·검색)가 없는 코인 중 CoinGecko 에 백서 링크가 있는 코인 (사용자 PC 실측: 미연결 110개 중 84개, PDF 형태 30 · 웹 54). `--all` 이면 모든 코인.
- PDF: `pypdf` 로 쪽 단위 텍스트 추출(최대 60쪽·8만 자). 청크는 쪽을 넘지 않게 나누고 메타데이터에 `page`·`file_name` 을 저장해 근거에 "백서 PDF p.N" 으로 표시한다.
- 웹: HTML 에서 스크립트·메뉴·머리말·꼬리말을 빼고 본문 글자만 추출(최대 8만 자). 위키와 같은 방식으로 청킹.
- GitHub 미리보기 링크(`/blob/`)는 원본 파일(`raw.githubusercontent.com`)로 바꿔 받고, 폴더 링크(`/tree/`)와 미리보기·로그인 화면 글자가 보이는 페이지는 받지 않는다 (D16). 이미 잘못 받은 문서는 `--prune` 으로 정리.
- 위키·백서가 모두 없는 코인은 CoinGecko 설명만 쓴다 (D15).
- 글자가 500자 미만(스크립트로 그리는 페이지, 스캔 PDF)이거나 PDF·HTML 이 아니면 수집하지 않고 `wp:{URL}` 로 기록해 다시 시도하지 않는다. 네트워크 오류는 기록하지 않아 다음 실행 때 재시도한다.

## 4. 실행 방법 (데이터)

```bash
# .env: CONTACT_EMAIL(필수 — 없으면 위키 수집을 하지 않음), COINGECKO_DEMO_API_KEY(권장)
python -m scripts.collect_coins                 # 약 150건 · 키 있으면 수 분, 키 없으면 공용망에서 수십 분~2시간
python -m scripts.collect_item_docs --limit 20  # 상위 20개 코인의 자체 위키 문서 (1분 이내)
python -m scripts.collect_item_docs             # 전체 (문서가 있는 40개 코인)
python -m scripts.check_sample                  # 건수·필드·출처 표기 점검
python -m scripts.build_web_sample              # 화면 샘플 갱신
```

## 5. 파일 필드

`data/coins.json` (항목 1건): `coin_id, symbol, name, name_ko, market_cap_rank, categories[], genesis_date, hashing_algorithm, asset_platform_id, description_ko, description_en(각 최대 600자), description_source(coingecko|wikidata), detail_collected, homepage, whitepaper, github, explorer, market{가격·시총·거래량·공급량·ATH·등락률}, wikidata_qid, kowiki_title, enwiki_title, snapshot_at, source`

`data/source_map.json` (코인별): `wikidata{qid, method, label_ko, desc_en}, kowiki{title, url[, page_id, chars, lastrevid]}, enwiki{…}, search_candidate_ko/en{title, page_id, string_match, url}(스냅샷 전용), candidate_review{decision, note}, link_review{decision, needs_review, note}`

`data/docs/wikipedia/{coin_id}_{doc_id}.json` (예: `ethereum_wikipedia_ko-12345.json`): `page_id, doc_id, title, url, text, source, source_type, license, coin_id, related_coin, search_query, is_item_doc, lastrevid, collected_at`
