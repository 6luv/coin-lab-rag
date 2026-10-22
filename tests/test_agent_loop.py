"""scripts.agent_loop: 가짜 구현/검증 CLI 로 루프 흐름만 확인한다 (실제 Claude·Codex 는 부르지 않음)."""
import sys

from scripts import agent_loop

IMPL = """
import sys, pathlib
log = pathlib.Path(sys.argv[1]); prompt = sys.stdin.read()
log.write_text(log.read_text(encoding='utf-8') + ('FIX\\n' if 'Codex 검증 결과' in prompt else 'NEW\\n') if log.exists() else 'NEW\\n', encoding='utf-8')
print('변경 파일: 없음 / 테스트: 통과')
"""

REVIEW = """
import sys, pathlib
counter = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2]); fails = int(sys.argv[3])
n = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(n))
sys.stdin.read()
out.write_text('결과: FAIL\\n- [Medium] a.py:1 — 문제' if n <= fails else '결과: **PASS**', encoding='utf-8')
"""


def make_cfg(tmp_path, fails):
    (tmp_path / "impl.py").write_text(IMPL, encoding="utf-8")
    (tmp_path / "review.py").write_text(REVIEW, encoding="utf-8")
    return {
        "implementer": {"name": "FakeClaude", "cmd": [sys.executable, str(tmp_path / "impl.py"), str(tmp_path / "impl.log")]},
        "reviewer": {"name": "FakeCodex", "cmd": [sys.executable, str(tmp_path / "review.py"),
                                                   str(tmp_path / "count"), "{out}", str(fails)]},
        "max_fix_rounds": 3,
        "timeout_sec": 60,
        "tests": [[sys.executable, "-c", "print('1 passed')"]],
        "reviews_dir": str(tmp_path / "reviews"),
    }


def test_pass_after_one_fix(tmp_path):
    cfg = make_cfg(tmp_path, fails=1)
    assert agent_loop.main(["작업 A"], cfg) == 0
    assert (tmp_path / "impl.log").read_text(encoding="utf-8").split() == ["NEW", "FIX"]
    assert len(list((tmp_path / "reviews").glob("*-r*.md"))) == 2
    loop = next((tmp_path / "reviews").glob("*-loop.md")).read_text(encoding="utf-8")
    assert "**FAIL**" in loop and "**PASS**" in loop


def test_stops_after_max_fix_rounds(tmp_path):
    cfg = make_cfg(tmp_path, fails=99)
    assert agent_loop.main(["작업 B"], cfg) == 1
    assert (tmp_path / "impl.log").read_text(encoding="utf-8").split() == ["NEW", "FIX", "FIX", "FIX"]
    assert "반복 실패" in next((tmp_path / "reviews").glob("*-loop.md")).read_text(encoding="utf-8")


def test_review_only_does_not_call_implementer(tmp_path):
    cfg = make_cfg(tmp_path, fails=99)
    assert agent_loop.main(["작업 C", "--review-only"], cfg) == 1
    assert not (tmp_path / "impl.log").exists()


def test_missing_cli_stops(tmp_path):
    cfg = make_cfg(tmp_path, fails=0)
    cfg["implementer"]["cmd"] = ["no-such-claude-cli"]
    assert agent_loop.main(["작업 D"], cfg) == 2


def test_verdict_parsing():
    assert agent_loop.verdict("결과: PASS") == "PASS"
    assert agent_loop.verdict("## 결과：**fail**") == "FAIL"
    assert agent_loop.verdict("검증했습니다") == "UNKNOWN"
