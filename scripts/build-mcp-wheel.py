"""Create the standalone MCP release variant from a built WireCloud wheel.

The local version label distinguishes the GitHub release asset and lets pip
replace the regular distribution without installing overlapping packages.
Application files and compiled assets are reused byte for byte.
"""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import io
from email import policy
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename


def build_mcp_wheel(source: Path, output_dir: Path, constraints: Path) -> Path:
    name, version, _, _ = parse_wheel_filename(source.name)
    if canonicalize_name(name) != "wirecloud" or version.local:
        raise ValueError("Expected a regular WireCloud wheel without a local version label")

    pins = []
    for line in constraints.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        specifiers = list(requirement.specifier)
        if (requirement.url or requirement.marker or requirement.extras or len(specifiers) != 1
                or specifiers[0].operator != "==" or "*" in specifiers[0].version):
            raise ValueError("MCP constraints must be unconditional exact version pins")
        pins.append(str(requirement))
    if not any(canonicalize_name(Requirement(pin).name) == "mcp" for pin in pins):
        raise ValueError("MCP constraints must pin the MCP SDK")

    mcp_version = f"{version}+mcp"
    parts = source.name.split("-")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "-".join([parts[0], mcp_version, *parts[2:]])

    with ZipFile(source) as wheel:
        metadata_paths = [path for path in wheel.namelist() if path.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise ValueError("Expected one wheel metadata directory")
        metadata_path = metadata_paths[0]
        old_info = metadata_path.split("/")[0]
        old_data = old_info.removesuffix(".dist-info") + ".data"
        new_info = f"wirecloud-{mcp_version}.dist-info"
        new_data = f"wirecloud-{mcp_version}.data"
        if any(path in wheel.namelist() for path in (f"{old_info}/RECORD.jws", f"{old_info}/RECORD.p7s")):
            raise ValueError("Signed wheels must be rebuilt and signed separately")
        metadata = BytesParser().parsebytes(wheel.read(metadata_path))
        if metadata["Version"] != str(version) or canonicalize_name(metadata["Name"]) != "wirecloud":
            raise ValueError("Wheel filename and metadata do not match")
        metadata.replace_header("Version", mcp_version)
        python_requirement = str(SpecifierSet(metadata.get("Requires-Python", "") + ",>=3.11"))
        if "Requires-Python" in metadata:
            metadata.replace_header("Requires-Python", python_requirement)
        else:
            metadata["Requires-Python"] = python_requirement
        # Retain existing requirements: pip intersects them with the exact MCP
        # pins, so future core constraints cannot silently be discarded.
        for pin in pins:
            metadata["Requires-Dist"] = pin

        records = []
        with ZipFile(target, "w") as output:
            for info in wheel.infolist():
                if info.filename == f"{old_info}/RECORD":
                    continue
                contents = wheel.read(info.filename)
                if info.filename == metadata_path:
                    contents = metadata.as_bytes(policy=policy.default.clone(max_line_length=0, utf8=True))
                destination = copy.copy(info)
                for old, new in ((old_info, new_info), (old_data, new_data)):
                    if destination.filename.startswith(old + "/"):
                        destination.filename = new + destination.filename[len(old):]
                        break
                output.writestr(destination, contents)
                digest = base64.urlsafe_b64encode(hashlib.sha256(contents).digest()).rstrip(b"=").decode("ascii")
                records.append((destination.filename, f"sha256={digest}", len(contents)))
            record = io.StringIO()
            writer = csv.writer(record, lineterminator="\n")
            writer.writerows([*records, (f"{new_info}/RECORD", "", "")])
            record_info = copy.copy(wheel.getinfo(metadata_path))
            record_info.filename = f"{new_info}/RECORD"
            output.writestr(record_info, record.getvalue().encode("utf-8"))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--constraints", type=Path,
                        default=Path(__file__).resolve().parents[1] / "constraints-mcp.txt")
    args = parser.parse_args()
    print(build_mcp_wheel(args.wheel, args.output_dir or args.wheel.parent, args.constraints))
