# -*- coding: utf-8 -*-

import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from wirecloud import main as main_module
from wirecloud.commons.utils import theme as theme_utils
from wirecloud.platform.plugins import get_templates
from wirecloud.themes import industrytheme


async def _noop_close():
    return None


main_module.close = _noop_close

THEMES_PATH = Path(theme_utils.themes.__file__).parent
INDUSTRY_TEMPLATES = THEMES_PATH / "industrytheme" / "templates"
DEFAULT_TEMPLATES = THEMES_PATH / "defaulttheme" / "templates"


@pytest.fixture
def industry_available(monkeypatch):
    monkeypatch.setattr(theme_utils, "AVAILABLE_THEMES", ["defaulttheme", "industrytheme"])
    theme_utils._generate_jinja2_templates()
    theme_utils._generate_theme_translations()
    yield
    theme_utils.JINJA2_TEMPLATES.pop("industrytheme", None)
    theme_utils.THEME_TRANSLATIONS.pop("industrytheme", None)


def test_industrytheme_is_a_root_theme():
    assert industrytheme.parent is None
    assert industrytheme.config["color_schemes"] == ["light", "dark"]
    assert industrytheme.config["keyboard_shortcuts"] is True


def test_industrytheme_provides_every_template():
    # Root themes must provide all the templates used by the platform
    expected = {str(path.relative_to(DEFAULT_TEMPLATES)) for path in DEFAULT_TEMPLATES.rglob("*.html")}
    provided = {str(path.relative_to(INDUSTRY_TEMPLATES)) for path in INDUSTRY_TEMPLATES.rglob("*.html")}
    assert expected - provided == set()


@pytest.mark.parametrize("view", ["classic", "smartphone", "embedded"])
async def test_get_industrytheme_info(app_client, industry_available, view):
    response = await app_client.get(f"/api/theme/industrytheme?view={view}", headers={"accept": "application/json"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "industrytheme"
    assert payload["config"]["color_schemes"] == ["light", "dark"]
    assert set(payload["templates"].keys()) == set(get_templates(view))
    for template_id, content in payload["templates"].items():
        assert content.strip() != "", template_id
        if content.lstrip().startswith("<s:styledgui"):
            # StyledElements.GUIBuilder parses these templates as XML
            ElementTree.fromstring(content)


async def test_industrytheme_templates_render_the_shell_hooks(app_client, industry_available):
    response = await app_client.get("/api/theme/industrytheme?view=classic", headers={"accept": "application/json"})
    templates = response.json()["templates"]

    # Placeholders and classes required by the platform code
    assert "<t:closebutton" in templates["wirecloud/modals/base"]
    assert "<t:iframe/>" in templates["wirecloud/workspace/widget"]
    assert "wc-widget-heading" in templates["wirecloud/workspace/widget"]
    assert "<t:usermenu" in templates["wirecloud/user_menu"]
    assert "wc-signin-button" in templates["wirecloud/signin"]
    assert "<t:button/>" in templates["wirecloud/workspace/empty_tab_message"]


def test_industrytheme_bundles_existing_files():
    # The webpack entries silently skip missing files, so a stylesheet or a
    # script that is not committed would only be noticed in the browser
    theme_dir = THEMES_PATH / "industrytheme"
    files = set(re.findall(r"'((?:css|js)/[^']+)'", (theme_dir / "theme.ts").read_text()))

    assert files
    assert {f for f in files if not (theme_dir / "static" / f).is_file()} == set()


def test_industrytheme_icon_map_icons_exist():
    # Every icon of the maps needs its SVG (see scripts/update_icons.py),
    # otherwise its Font Awesome names are drawn as nothing
    static_dir = THEMES_PATH / "industrytheme" / "static"
    source = (static_dir / "css" / "base" / "_icon-map.scss").read_text()
    lucide_list = re.search(r"\$lucide-icons:\s*\((.*?)\);", source, re.S).group(1)
    fa_map = re.search(r"\$fa-icons:\s*\((.*?)\);", source, re.S).group(1)
    names = set(re.findall(r'"([a-z0-9-]+)"', lucide_list))
    names.update(re.findall(r'"[a-z0-9-]+":\s*"([a-z0-9-]+)"', fa_map))

    assert "bold" in names
    assert {n for n in names if not (static_dir / "icons" / f"{n}.svg").is_file()} == set()


def test_industrytheme_static_files(industry_available, monkeypatch, tmp_path):
    monkeypatch.setattr(theme_utils, "DIST_PATH", str(tmp_path))

    icon = theme_utils.get_theme_static_path("industrytheme", "icons/settings.svg")
    assert icon.endswith("industrytheme/static/icons/settings.svg")
    assert 'stroke-width="1.5"' in Path(icon).read_text()

    font = theme_utils.get_theme_static_path("industrytheme", "fonts/barlow-latin-400-normal.woff2")
    assert font.endswith("barlow-latin-400-normal.woff2")

    # Files of the default theme are not available to the Industry theme
    with pytest.raises(theme_utils.NotFound):
        theme_utils.get_theme_static_path("industrytheme", "css/fontawesome.min.css")
