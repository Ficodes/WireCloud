"""Core test collection must work when the optional MCP SDK is absent."""
from pathlib import Path
import subprocess
import sys


def test_mcp_collection_skips_sdk_tests_when_local_namespace_exists():
    project_root = Path(__file__).resolve().parents[1]
    # Reproduce tests/mcp being importable as a namespace package on CI,
    # while keeping the installed SDK hidden without changing the environment.
    script = """
import sys
from pathlib import Path
from types import ModuleType

namespace = ModuleType("mcp")
namespace.__path__ = [str(Path("tests/mcp").resolve())]
sys.modules["mcp"] = namespace

import pytest
raise SystemExit(pytest.main(["tests/mcp", "-q"]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=project_root,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped" in result.stdout
