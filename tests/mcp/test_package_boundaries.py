"""Archive integrity, recursive limits, and inline transfer boundaries."""
import base64
import io
import sys
import zipfile

import pytest

if sys.version_info < (3, 11):
    pytest.skip("MCP requires Python 3.11+", allow_module_level=True)
pytest.importorskip("mcp")

from fastapi import HTTPException
from wirecloud.mcp import packages
from test_mcp import package
from test_adapter_boundaries import mashup_package


def test_empty_and_oversized_packages_are_rejected_before_parsing(monkeypatch):
    monkeypatch.setattr(packages, "PACKAGE_LIMIT", 10)
    for data in (b"", b"x" * 11):
        with pytest.raises(HTTPException, match="413"):
            packages.validate_package(data)


def test_recursive_packages_share_a_depth_and_extraction_budget(monkeypatch):
    child = package(version="2.0.0")
    outer = mashup_package(child)
    with zipfile.ZipFile(io.BytesIO(outer)) as archive:
        outer_size = sum(info.file_size for info in archive.infolist())
    # The outer archive fits; extracting its child exceeds the combined budget.
    monkeypatch.setattr(packages, "EXTRACTED_LIMIT", outer_size + 1)
    with pytest.raises(HTTPException, match="Embedded package extraction limit"):
        packages.validate_package(outer)
    monkeypatch.setattr(packages, "EXTRACTED_LIMIT", 500 * 1024 * 1024)
    nested = child
    for _ in range(5):
        nested = mashup_package(nested)
    with pytest.raises(HTTPException, match="nesting limit"):
        packages.validate_package(nested)


def test_archive_crc_corruption_is_rejected():
    content = bytearray(package())
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entry = archive.getinfo("index.html")
        offset = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
    content[offset] ^= 0x01
    with pytest.raises(HTTPException, match="Corrupt archive entry"):
        packages.validate_package(bytes(content))


def test_inline_decoded_size_is_checked_after_base64_validation(monkeypatch):
    monkeypatch.setattr(packages, "INLINE_LIMIT", 2)
    with pytest.raises(HTTPException, match="Inline package exceeds"):
        packages.decode_package(base64.b64encode(b"abc").decode())
