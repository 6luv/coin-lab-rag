"""pytest 공통 설정.

실행마다 새 임시 폴더를 만들어 tmp_path 의 기준으로 쓴다 (PYTEST_DEBUG_TEMPROOT).
Windows 에서 %TEMP%\\pytest-of-<사용자> 가 다른 권한(예: Codex 샌드박스)으로 먼저 만들어지면
tmp_path 를 쓰는 테스트가 PermissionError 로 실패하기 때문이다 (docs/troubleshooting.md).
이미 PYTEST_DEBUG_TEMPROOT 가 지정돼 있으면 그대로 둔다.
"""
import os
import shutil
import tempfile
import time
from pathlib import Path

PREFIX = "coinlab-pytest-"

if "PYTEST_DEBUG_TEMPROOT" not in os.environ:
    for old in Path(tempfile.gettempdir()).glob(PREFIX + "*"):  # 하루 지난 이전 실행 폴더 정리 (실패는 무시)
        try:
            if time.time() - old.stat().st_mtime > 86400:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            pass
    os.environ["PYTEST_DEBUG_TEMPROOT"] = tempfile.mkdtemp(prefix=PREFIX)
