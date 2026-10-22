# Codex 검증 요청 양식 (수동용)

보통은 `python -m scripts.agent_loop --review-only "<작업>"` 이 이 내용을 자동으로 채워 Codex 를 부른다.
Codex IDE·웹에 직접 붙여 넣을 때만 이 양식을 쓴다.

AGENTS.md 지침에 따라 아래 변경을 검증하고 PASS/FAIL로 보고해 주세요. 코드는 수정하지 마세요.

- 작업: <기능 이름 / 요구사항 번호>
- 변경 파일: <목록>
- 완료 조건: <docs/progress.md 에 적은 조건>
- 구현자가 실행한 테스트와 결과: <명령과 결과 요약>
- 특히 봐 줄 부분: <경계 조건, 보안 등>
