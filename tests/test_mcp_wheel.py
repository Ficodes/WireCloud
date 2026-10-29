"""Validate the installable release variant, metadata, and wheel integrity."""
import base64
import csv
import hashlib
import importlib.util
import io
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_mcp_wheel", ROOT / "scripts/build-mcp-wheel.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def regular_wheel(tmp_path):
    path = tmp_path / "wirecloud-2.0.0-py3-none-any.whl"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("wirecloud/__init__.py", "# application code\n")
        archive.writestr("wirecloud/dist/js/main.js", "// compiled frontend\n")
        archive.writestr("wirecloud-2.0.0.data/data/example.txt", "data file")
        archive.writestr("wirecloud-2.0.0.dist-info/METADATA",
            'Metadata-Version: 2.4\nName: wirecloud\nVersion: 2.0.0\nRequires-Python: >=3.9,<4\n'
            'Requires-Dist: fastapi>=0.100\nRequires-Dist: jinja2\n'
            'Requires-Dist: mcp==2.3.0; python_version >= "3.11" and extra == "mcp"\n'
            'Provides-Extra: mcp\nDescription-Content-Type: text/markdown\n\nWireCloud café\n'.encode("utf-8"))
        archive.writestr("wirecloud-2.0.0.dist-info/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr("wirecloud-2.0.0.dist-info/RECORD", "old record")
    return path


def test_mcp_wheel_keeps_application_and_assets_and_enforces_dependencies(regular_wheel):
    original = regular_wheel.read_bytes()
    path = builder.build_mcp_wheel(regular_wheel, regular_wheel.parent, ROOT / "constraints-mcp.txt")
    assert path.name == "wirecloud-2.0.0+mcp-py3-none-any.whl"
    assert regular_wheel.read_bytes() == original
    with ZipFile(path) as mcp, ZipFile(regular_wheel) as regular:
        for name in ("wirecloud/__init__.py", "wirecloud/dist/js/main.js"):
            assert mcp.read(name) == regular.read(name)
        assert mcp.read("wirecloud-2.0.0+mcp.data/data/example.txt") == b"data file"
        assert not any(name.startswith("wirecloud-2.0.0.dist-info/") for name in mcp.namelist())
        metadata = BytesParser().parsebytes(mcp.read("wirecloud-2.0.0+mcp.dist-info/METADATA"))
        assert metadata["Name"] == "wirecloud" and metadata["Version"] == "2.0.0+mcp"
        python = SpecifierSet(metadata["Requires-Python"])
        assert Version("3.11") in python and Version("3.9") not in python and Version("4.0") not in python
        requirements = [Requirement(value) for value in metadata.get_all("Requires-Dist")]
        unconditional = {str(value) for value in requirements if not value.marker}
        assert {"mcp==2.3.0", "fastapi==0.115.8", "starlette==0.45.3", "sse-starlette==3.0.3"} <= unconditional
        assert "fastapi>=0.100" in unconditional and "jinja2" in unconditional
        assert "café" in metadata.get_payload(decode=True).decode("utf-8")


def test_mcp_wheel_record_hashes_and_sizes_are_valid(regular_wheel):
    path = builder.build_mcp_wheel(regular_wheel, regular_wheel.parent, ROOT / "constraints-mcp.txt")
    with ZipFile(path) as archive:
        record_path = "wirecloud-2.0.0+mcp.dist-info/RECORD"
        records = list(csv.reader(io.StringIO(archive.read(record_path).decode("utf-8"))))
        assert {row[0] for row in records} == set(archive.namelist())
        for name, digest, size in records:
            if name == record_path:
                assert digest == size == ""
                continue
            contents = archive.read(name)
            assert int(size) == len(contents)
            assert digest == "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(contents).digest()).rstrip(b"=").decode()


@pytest.mark.parametrize("text", ["fastapi==0.115.8", "mcp>=2.3.0", "mcp==2.3.0; python_version >= '3.11'"])
def test_mcp_wheel_requires_unconditional_pinned_sdk(regular_wheel, text, tmp_path):
    constraints = tmp_path / "constraints.txt"
    constraints.write_text(text)
    with pytest.raises(ValueError, match="MCP constraints"):
        builder.build_mcp_wheel(regular_wheel, tmp_path, constraints)


def test_mcp_wheel_cannot_be_used_as_its_own_input(regular_wheel):
    path = builder.build_mcp_wheel(regular_wheel, regular_wheel.parent, ROOT / "constraints-mcp.txt")
    with pytest.raises(ValueError, match="regular WireCloud wheel"):
        builder.build_mcp_wheel(path, path.parent, ROOT / "constraints-mcp.txt")
