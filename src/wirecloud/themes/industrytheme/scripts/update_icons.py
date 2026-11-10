#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

# This file is part of Wirecloud.

# Wirecloud is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Wirecloud is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

"""
Copies the Lucide icons referenced by static/css/base/_icon-map.scss into
static/icons, setting their stroke width to 1.5.

Usage:

    npm pack lucide-static@0.460.0 && tar xzf lucide-static-0.460.0.tgz
    python src/wirecloud/themes/industrytheme/scripts/update_icons.py package/icons
"""

import argparse
import re
import sys
from pathlib import Path

THEME_PATH = Path(__file__).resolve().parent.parent
ICON_MAP = THEME_PATH / "static" / "css" / "base" / "_icon-map.scss"
ICONS_PATH = THEME_PATH / "static" / "icons"


def get_icon_names(source: str) -> set:
    names = set()

    lucide_list = re.search(r"\$lucide-icons:\s*\((.*?)\);", source, re.S)
    if lucide_list is not None:
        names.update(re.findall(r'"([a-z0-9-]+)"', lucide_list.group(1)))

    fa_map = re.search(r"\$fa-icons:\s*\((.*?)\);", source, re.S)
    if fa_map is not None:
        names.update(re.findall(r'"[a-z0-9-]+":\s*"([a-z0-9-]+)"', fa_map.group(1)))

    return names


def convert_icon(svg: str) -> str:
    # Drop the licence comment (see static/icons/LICENSE) and the class names
    svg = re.sub(r"<!--.*?-->\s*", "", svg, flags=re.S)
    svg = re.sub(r'\s*class="[^"]*"', "", svg)
    svg = re.sub(r'stroke-width="[^"]*"', 'stroke-width="1.5"', svg)
    # Compact the markup
    svg = re.sub(r"\s*\n\s*", " ", svg).replace("> <", "><").replace(" />", "/>").replace(" >", ">").strip()
    return svg + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="icons directory of the lucide-static package")
    parser.add_argument("--prune", action="store_true", help="remove icons that are no longer referenced")
    args = parser.parse_args(argv)

    source_path = Path(args.source)
    names = get_icon_names(ICON_MAP.read_text(encoding="utf-8"))
    missing = sorted(name for name in names if not (source_path / f"{name}.svg").exists())
    if missing:
        print("Icons not found in the source directory: " + ", ".join(missing), file=sys.stderr)
        return 1

    ICONS_PATH.mkdir(parents=True, exist_ok=True)
    for name in sorted(names):
        svg = (source_path / f"{name}.svg").read_text(encoding="utf-8")
        (ICONS_PATH / f"{name}.svg").write_text(convert_icon(svg), encoding="utf-8")

    if args.prune:
        for icon in ICONS_PATH.glob("*.svg"):
            if icon.stem not in names:
                icon.unlink()

    print(f"{len(names)} icons written to {ICONS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
