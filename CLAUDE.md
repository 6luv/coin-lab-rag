# CLAUDE.md

공통 지침은 `AGENTS.md` 에 있다 (Codex 와 같은 파일을 기준으로 삼기 위해 내용을 여기에 따로 쓰지 않는다).

@AGENTS.md

## Claude 전용
- 이 저장소에서 Claude 는 **구현 담당**(Opus 5.5, effort medium)이다. 검증은 Codex 가 하고, Claude 는 검증 결과를 스스로 PASS 처리하지 않는다.
- 세션을 시작하면 `AGENTS.md` 2장 순서대로 읽고, `docs/progress.md` 의 "다음 작업"에서 이어간다.
- 검증은 `/codex-review <작업>` 또는 `python -m scripts.agent_loop --review-only "<작업>"` 로 Codex 에 맡긴다 (`AGENTS.md` 6장).
- 작업을 마치면 `AGENTS.md` 8장 형식으로 한국어로 보고한다.
