"""Claude(구현) ↔ Codex(검증) 자동 호출 루프.

  python -m scripts.agent_loop "F2014 MMR 비교 실험 구현"        # 구현 → 테스트 → 검증 → (FAIL 이면) 수정 반복
  python -m scripts.agent_loop --review-only "인덱싱 복구 수정"   # 지금 변경을 Codex 검증만
  python -m scripts.agent_loop --dry-run "..."                   # 실행할 명령만 출력

- 두 CLI 를 매번 새 프로세스로 부른다 → 구현과 검증의 컨텍스트가 섞이지 않는다.
- Codex 는 read-only 샌드박스로 실행하고, 검증 전후 작업 폴더 해시를 비교해 파일을 바꿨으면 경고한다.
- 같은 작업에서 수정 후에도 FAIL 이 max_fix_rounds(기본 3)번 이어지면 멈추고 보고한다.
- 검증 결과는 docs/reviews/ 에, 진행 기록은 docs/reviews/<날짜>-<주제>-loop.md 에 남긴다.
- 명령·옵션은 config/agents.json 에서 바꾼다. 커밋·푸시는 하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "agents.json"
VERDICT = re.compile(r"결과\s*[:：]\s*\**\s*(PASS|FAIL)", re.I)


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def slug(text: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", text).strip("-").lower()
    return s[:40] or "task"


def resolve(cmd: list[str], **values) -> list[str]:
    out = [c.format(python=sys.executable, **values) if "{" in c else c for c in cmd]
    exe = shutil.which(out[0])  # Windows 의 claude.cmd / codex.cmd 도 찾는다
    if exe:
        out[0] = exe
    return out


def run(cmd: list[str], stdin: str | None, timeout: int, cwd: Path = ROOT) -> tuple[int, str]:
    try:
        # 자식 파이썬이 파이프 출력도 UTF-8 로 쓰게 한다 (Windows 기본은 cp949 → 글자 깨짐)
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        p = subprocess.run(cmd, input=stdin, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except FileNotFoundError:
        return 127, f"명령을 찾을 수 없습니다: {cmd[0]} (설치·PATH 확인)"
    except subprocess.TimeoutExpired:
        return 124, f"시간 초과 ({timeout}초): {cmd[0]}"
    return p.returncode, (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr.strip() else "")


def git(*args: str) -> str:
    code, out = run(["git", *args], None, 60)
    return out.strip() if code == 0 else ""


def tree_hash() -> str:
    """git 이 추적하거나 무시하지 않는 파일들의 내용 해시 (검증 담당이 파일을 바꿨는지 확인용)."""
    files = git("ls-files", "-co", "--exclude-standard").splitlines()
    h = hashlib.sha256()
    for f in sorted(files):
        p = ROOT / f
        if p.is_file():
            h.update(f.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def run_tests(cfg: dict) -> tuple[bool, str]:
    lines, ok = [], True
    for cmd in cfg["tests"]:
        code, out = run(resolve(cmd), None, cfg["timeout_sec"])
        ok &= code == 0
        tail = "\n".join(out.strip().splitlines()[-8:])
        lines.append(f"$ {' '.join(cmd).replace('{python}', 'python')}  → exit {code}\n{tail}")
    return ok, "\n\n".join(lines)


def implement_prompt(task: str, review: str | None, round_no: int) -> str:
    head = (
        "AGENTS.md 와 CLAUDE.md 지침을 따르는 구현 담당으로 일한다. 이 실행은 자동 루프의 일부라 사용자에게 질문할 수 없다.\n"
        "애매한 부분은 가장 합리적인 해석을 택하고 마지막 보고에 적는다. 커밋·푸시하지 않는다. "
        ".env 를 읽거나 출력하지 않는다.\n\n"
        f"## 작업\n{task}\n"
    )
    if review:
        head += (
            f"\n## Codex 검증 결과 (수정 {round_no}회차)\n아래 FAIL 지적을 고친다. 지적과 무관한 코드는 바꾸지 않는다. "
            "각 지적에 회귀 테스트를 추가한다.\n\n" + review + "\n"
        )
    return head + (
        "\n## 마지막 보고 형식\n변경한 파일 / 실행한 테스트와 결과 / 남은 문제 — 한국어로 간결하게."
    )


def review_prompt(task: str, impl_report: str, tests: str, baseline: str, prev: list[Path]) -> str:
    status = git("status", "--short") or "(git 정보 없음)"
    stat = git("diff", "--stat") or "(추적 파일 변경 없음 또는 git 정보 없음)"
    prev_txt = "\n".join(f"- {rel(p)}" for p in prev) or "- 없음"
    return (
        "AGENTS.md 7장 기준의 검증 담당으로 아래 변경을 검증한다. 코드와 문서를 수정하지 않는다 (read-only).\n"
        "결과 첫 줄은 반드시 `결과: PASS` 또는 `결과: FAIL` 형식으로 쓰고, FAIL 이면 "
        "[심각도] 파일:줄 — 문제 / 재현 / 수정 방향을 적는다. 보고서는 한국어로 쓴다.\n\n"
        f"## 작업\n{task}\n\n## 구현 담당 보고\n{impl_report.strip()[-4000:] or '(없음)'}\n\n"
        f"## 오케스트레이터가 실행한 테스트\n{tests}\n\n"
        f"## 작업 시작 전부터 있던 변경 (이번 작업과 무관할 수 있음)\n{baseline}\n\n"
        f"## 현재 변경 (git status)\n{status}\n\n## diff 통계\n{stat}\n\n"
        f"## 이번 작업의 이전 검증 기록 (같은 문제 반복 여부 판단용)\n{prev_txt}\n"
    )


def rel(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def verdict(text: str) -> str:
    m = VERDICT.search(text or "")
    return m.group(1).upper() if m else "UNKNOWN"


class Log:
    def __init__(self, path: Path, task: str):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# 자동 루프 기록 — {task}\n\n시작: {datetime.now():%Y-%m-%d %H:%M}\n\n", encoding="utf-8")

    def add(self, text: str) -> None:
        print(text)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(text + "\n\n")


def main(argv: list[str] | None = None, cfg: dict | None = None) -> int:
    ap = argparse.ArgumentParser(description="Claude ↔ Codex 자동 호출 루프")
    ap.add_argument("task", help="작업 설명 (요구사항 번호 포함 권장)")
    ap.add_argument("--review-only", action="store_true", help="구현 없이 현재 변경만 검증 (FAIL 이어도 수정하지 않음)")
    ap.add_argument("--max-fix-rounds", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    cfg = cfg or load_config()
    max_fix = args.max_fix_rounds if args.max_fix_rounds is not None else cfg["max_fix_rounds"]
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    reviews = ROOT / cfg["reviews_dir"]
    name = f"{stamp}-{slug(args.task)}"

    if args.dry_run:
        print("구현:", " ".join(resolve(cfg["implementer"]["cmd"])), "< (프롬프트)")
        print("검증:", " ".join(resolve(cfg["reviewer"]["cmd"], out=str(reviews / f"{name}-r1.md"))), "< (프롬프트)")
        for t in cfg["tests"]:
            print("테스트:", " ".join(resolve(t)))
        return 0

    log = Log(reviews / f"{name}-loop.md", args.task)
    baseline = git("status", "--short") or "(없음)"
    review_text, prev, impl_report = None, [], ""
    rounds = 0 if args.review_only else max_fix + 1  # 최초 구현 1회 + 수정 max_fix 회
    attempt = 0
    while True:
        attempt += 1
        if not args.review_only:
            log.add(f"## {attempt}회차 구현 ({cfg['implementer']['name']})")
            code, impl_report = run(resolve(cfg["implementer"]["cmd"]),
                                    implement_prompt(args.task, review_text, attempt - 1), cfg["timeout_sec"])
            log.add(f"exit {code}\n\n```\n{impl_report.strip()[-3000:]}\n```")
            if code != 0:
                log.add("구현 담당 실행 실패 → 중단. (CLI 설치·로그인·권한 확인)")
                return 2
        ok, tests = run_tests(cfg)
        log.add(f"### 테스트 ({'통과' if ok else '실패'})\n```\n{tests}\n```")

        out = reviews / f"{name}-r{attempt}.md"
        before = tree_hash()
        code, raw = run(resolve(cfg["reviewer"]["cmd"], out=str(out)),
                        review_prompt(args.task, impl_report, tests, baseline, prev), cfg["timeout_sec"])
        if tree_hash() != before:
            log.add("⚠ 검증 담당 실행 중 작업 폴더 파일이 바뀌었습니다. `git status` 로 확인하세요 (자동 되돌리기 안 함).")
        if code != 0:
            log.add(f"검증 담당 실행 실패 (exit {code}) → 중단.\n```\n{raw.strip()[-2000:]}\n```")
            return 2
        if not out.exists() or not out.read_text(encoding="utf-8").strip():
            out.write_text(raw, encoding="utf-8")  # --output-last-message 를 지원하지 않는 설정일 때
        review_text = out.read_text(encoding="utf-8")
        result = verdict(review_text)
        prev.append(out)
        log.add(f"### 검증 ({cfg['reviewer']['name']}) → **{result}** · {rel(out)}")

        if result == "PASS":
            log.add("검증 통과. docs/progress.md 갱신과 커밋은 사람이 확인 후 진행한다.")
            return 0
        if result == "UNKNOWN":
            log.add("검증 결과에서 PASS/FAIL 을 찾지 못해 중단. 보고서를 직접 확인하세요.")
            return 3
        if args.review_only:
            log.add("--review-only: 수정하지 않고 종료.")
            return 1
        if attempt >= rounds:
            log.add(f"반복 실패: 수정 {max_fix}회 후에도 FAIL → 자동 반복 중단. 남은 지적은 위 보고서 참고.")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
