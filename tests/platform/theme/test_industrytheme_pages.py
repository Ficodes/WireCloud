# -*- coding: utf-8 -*-

# Pages rendered outside the platform shell by the Industry theme: the OAuth
# consent and connected applications pages (strict CSP, no inline scripts) and
# the error pages (rendered with autoescape).

import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from babel.messages.pofile import read_po
from jinja2 import Environment, nodes
from lxml import html

from commons.test_http_exception_pages import error_client
from oauth2provider.test_oauth import oauth_app, oauth_client, login_user, authorize_client, AUDIENCE
from wirecloud import settings
from wirecloud.commons.utils import theme as theme_utils
from wirecloud.mcp import docs as mcp_docs
from wirecloud.oauth2provider import service

THEME_PATH = Path(theme_utils.themes.__file__).parent / "industrytheme"
TEMPLATES = sorted((THEME_PATH / "templates").rglob("*.html"))
XSS = '<img src=x onerror="alert(1)">'


@pytest.fixture
def industry_theme(monkeypatch):
    monkeypatch.setattr(settings, "AVAILABLE_THEMES", ["defaulttheme", "industrytheme"])
    monkeypatch.setattr(theme_utils, "AVAILABLE_THEMES", settings.AVAILABLE_THEMES)
    monkeypatch.setattr(theme_utils, "JINJA2_TEMPLATES", {})
    monkeypatch.setattr(theme_utils, "THEME_TRANSLATIONS", {})
    theme_utils._generate_jinja2_templates()
    theme_utils._generate_theme_translations()


def assert_csp_compatible(document):
    # The OAuth pages forbid inline scripts and styles (see oauth2provider/pages.py)
    assert document.xpath("//style") == []
    assert document.xpath("//*[@style]") == []
    assert [s for s in document.xpath("//script") if (s.text or "").strip()] == []
    assert document.xpath("//@*[starts-with(name(), 'on')]") == []

    scripts = {urlsplit(src).path: (urlsplit(src), script) for script in document.xpath("//script")
               for src in [script.get("src")]}
    assert set(scripts) == {"/static/js/industry/ColorSchemeBoot.js", "/static/js/cache.js"}
    bundle, bundle_element = scripts["/static/js/cache.js"]
    assert parse_qs(bundle.query) == {"themeactive": ["industrytheme"], "view": ["oauth2"]}
    assert "defer" in bundle_element.attrib

    stylesheets = document.xpath("//link[@rel='stylesheet']/@href")
    assert len(stylesheets) == 1
    css = urlsplit(stylesheets[0])
    assert css.path == "/static/css/cache.css"
    assert parse_qs(css.query) == {"themeactive": ["industrytheme"], "view": ["index"]}


def test_industrytheme_oauth_templates_keep_the_page_contract():
    # Block names documented in docs/oauth2.md for theme overrides
    base = (THEME_PATH / "templates" / "wirecloud" / "oauth2provider" / "base.html").read_text()
    for block in ("title", "styles", "scripts", "branding", "content", "footer"):
        assert f"{{% block {block} %}}" in base
    assert '{% include "wirecloud/views/_head.html" %}' not in base


async def test_industrytheme_consent_page(oauth_client, db_session, industry_theme):
    await login_user(db_session, oauth_client)
    oauth_client.cookies.set("wc_oauth_browser", "preview-browser")
    await db_session.client.oauth_attempts.insert_one({
        "_id": service.digest("preview-handle"), "browser": service.digest("preview-browser"),
        "csrf": service.digest("preview-csrf"), "expires_at": service.now() + timedelta(minutes=5),
        "client_id": "client-id", "client_name": XSS, "redirect_uri": "http://127.0.0.1:9000/callback",
        "audience": AUDIENCE, "scopes": ["wirecloud:read"]})

    response = await oauth_client.get("/oauth2/consent", params={
        "request_id": "preview-handle", "csrf": "preview-csrf", "themeactive": "industrytheme"})

    assert response.status_code == 200, response.text
    assert "&lt;img src=x onerror=" in response.text
    assert "<img src=x" not in response.text
    document = html.fromstring(response.text)
    assert document.xpath("/html/@data-wc-theme") == ["industrytheme"]
    assert document.xpath("//*[contains(@class, 'wc-brand-mark')]")
    assert_csp_compatible(document)

    # Markers enhanced by oauth2provider/pages.js and the native form
    assert document.xpath("//section[@data-se-panel]//*[@data-se-panel-title][@id='consent-title']")
    form = document.xpath("//*[@data-se-panel-footer]/form[@method='post']")[0]
    assert {i.get("name") for i in form.xpath(".//input[@type='hidden']")} == {"request_id", "csrf"}
    buttons = [(b.get("name"), b.get("value"), b.get("data-se-button")) for b in form.xpath(".//button")]
    assert buttons == [("decision", "deny", "default"), ("decision", "approve", "primary")]
    assert document.xpath("//ul[@class='oauth-permissions']/li/text()") == ["Read accessible data"]


async def test_industrytheme_connections_page(oauth_client, db_session, industry_theme):
    await login_user(db_session, oauth_client)
    empty = await oauth_client.get("/oauth2/connections?themeactive=industrytheme")
    assert empty.status_code == 200
    assert "No connected applications" in empty.text

    await authorize_client(oauth_client)
    await db_session.client.oauth_grants.update_many({}, {"$set": {"client_name": XSS}})
    response = await oauth_client.get("/oauth2/connections?themeactive=industrytheme")

    assert response.status_code == 200
    assert "&lt;img src=x onerror=" in response.text
    assert "<img src=x" not in response.text
    document = html.fromstring(response.text)
    assert_csp_compatible(document)

    form = document.xpath("//ul[@class='oauth-connections']/li/form[@method='post']")[0]
    assert {i.get("name") for i in form.xpath(".//input[@type='hidden']")} == {"csrf", "grant_id"}
    checkboxes = form.xpath(".//fieldset//input[@type='checkbox'][@name='scope']")
    assert {c.get("value") for c in checkboxes} == {"wirecloud:read", "wirecloud:workspace:write"}
    # Industry square checkboxes (components/forms.scss)
    assert all("checkbox" in c.get("class").split() for c in checkboxes)
    buttons = [(b.get("name"), b.get("value"), b.get("data-se-button")) for b in form.xpath(".//button")]
    assert buttons == [("action", "update_permissions", "primary"), ("action", "revoke", "danger")]


def test_industrytheme_translates_its_templates():
    # Industry is a root theme: its catalog has no fallback to the default
    # theme, and editing a string in a template invalidates its translation
    with (THEME_PATH / "locale" / "es" / "LC_MESSAGES" / "industrytheme.po").open("rb") as f:
        catalog = read_po(f, locale="es")

    strings = set()
    env = Environment()
    for template in TEMPLATES:
        for call in env.parse(template.read_text()).find_all(nodes.Call):
            if isinstance(call.node, nodes.Name) and call.node.name == "trans" and isinstance(call.args[0], nodes.Const):
                strings.add(call.args[0].value)
    # Scope descriptions of the MCP resource are translated with trans() too
    strings.update(value for name, value in vars(mcp_docs).items() if re.fullmatch(r"scope_\w+_description", name))

    assert len(strings) > 100
    assert {s for s in strings if catalog.get(s) is None or not catalog.get(s).string} == set()


@pytest.mark.parametrize("path", ["/http-error/400", "/http-error/403", '/missing/<img src=x onerror="alert(1)">'])
async def test_industrytheme_error_pages_escape_once(error_client, industry_theme, monkeypatch, path):
    # base_plain.html bootstraps the platform with every plugin's endpoints;
    # the keycloak and fiware tests leave their IdM flags enabled without the
    # matching settings, so keep them off here
    from wirecloud.fiware import plugins as fiware_plugins
    from wirecloud.keycloak import plugins as keycloak_plugins
    monkeypatch.setattr(fiware_plugins, "IDM_SUPPORT_ENABLED", False)
    monkeypatch.setattr(keycloak_plugins, "IDM_SUPPORT_ENABLED", False)

    # Error pages are rendered with autoescape: escaping again in the templates
    # would show "&lt;" to the user
    response = await error_client.get(path, params={"themeactive": "industrytheme"}, headers={"Accept": "text/html"})

    assert response.headers["content-type"].startswith("text/html")
    assert 'data-wc-theme="industrytheme"' in response.text
    assert "<img src=x" not in response.text
    if path != "/http-error/403":
        assert "&lt;img src=x" in response.text
    assert "&amp;lt;" not in response.text
    assert "&amp;#34;" not in response.text
