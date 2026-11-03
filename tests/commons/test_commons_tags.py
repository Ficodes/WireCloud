# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest

from wirecloud.commons.templates import tags


class _FakeTemplateResponse:
    def __init__(self, template_name, context):
        self.template_name = template_name
        self.context = context
        payload = {
            "template": template_name,
            "has_catalogue": "js_catalogue" in context,
            "plain": context.get("plain"),
            "script": context.get("wirecloud_bootstrap_script", ""),
        }
        self.body = str(payload).encode("utf-8")


class _FakeTemplates:
    def TemplateResponse(self, template_name, context):
        return _FakeTemplateResponse(template_name, context)

    def get_template(self, template_name):
        class _Template:
            def __init__(self, name):
                self._name = name

            def render(self, context):
                return _FakeTemplateResponse(self._name, context).body.decode("utf-8")

        return _Template(template_name)


class _FakeTranslations:
    def __init__(self, catalog):
        self._catalog = catalog


def test_get_translation_and_paths(monkeypatch):
    monkeypatch.setattr(tags, "get_theme_translation", lambda _theme, _lang: "theme-trans")
    monkeypatch.setattr(tags, "_trans", lambda text, **_kwargs: f"{text} %(name)s")
    assert tags.get_translation("theme", "es", "Hello", name="Alice") == "Hello Alice"

    request = SimpleNamespace(scope={})
    path = tags.get_static_path("default", "classic", request, "js/app.js?v=1")
    assert path.startswith("/static/js/app.js?")
    assert "themeactive=default" in path
    assert "view=classic" in path
    assert "v=1" in path

    path_with_view = tags.get_static_path("default", "classic", request, "js/app.js?view=embed")
    assert "view=embed" in path_with_view

    monkeypatch.setattr(tags, "get_absolute_reverse_url", lambda view, _request, **kwargs: f"/{view}/{kwargs['x']}")
    assert tags.get_url_from_view(request, "wirecloud.view", x="1") == "/wirecloud.view/1"


@pytest.mark.parametrize("prefix", ["/wirecloud", "/wirecloud/"])
def test_static_paths_preserve_deployment_prefix_and_explicit_view(prefix):
    request = SimpleNamespace(scope={"root_path": prefix})
    path = tags.get_static_path("defaulttheme", "classic", request, "js/cache.js?view=oauth2")
    assert path == "/wirecloud/static/js/cache.js?view=oauth2&themeactive=defaulttheme"


def test_get_wirecloud_bootstrap(monkeypatch):
    monkeypatch.setattr(tags, "templates", _FakeTemplates())
    monkeypatch.setattr(tags, "get_constants", lambda: [{"key": "A", "value": "1"}])
    monkeypatch.setattr(
        tags,
        "get_wirecloud_ajax_endpoints",
        lambda _view, _request: (
            SimpleNamespace(id="plain", url="/api/x"),
            SimpleNamespace(id="templated", url="/api/%(id)s"),
        ),
    )

    context = {
        "request": SimpleNamespace(state=SimpleNamespace(lang="es")),
        "static": lambda *_a, **_k: None,
        "url": lambda *_a, **_k: None,
        "VIEW_MODE": "workspace",
        "LANGUAGE_CODE": "es",
        "WIRECLOUD_VERSION_HASH": "hash",
        "THEME": "defaulttheme",
    }

    rendered = tags.get_wirecloud_bootstrap(context, [{"name": "defaulttheme"}], view=None, plain=True)
    assert "bootstrap.html" in rendered
    assert "Wirecloud.URLs" in rendered
    assert "new Wirecloud.Utils.Template" in rendered

    rendered_explicit_view = tags.get_wirecloud_bootstrap(context, [{"name": "defaulttheme"}], view="embedded", plain=False)
    assert "bootstrap.html" in rendered_explicit_view


def test_get_javascript_catalogue_with_translations(monkeypatch):
    monkeypatch.setattr(tags, "templates", _FakeTemplates())
    monkeypatch.setattr(tags.settings, "INSTALLED_APPS", ["wirecloud.fake", "wirecloud.missing"])

    child = SimpleNamespace(__file__="/tmp/theme/child.py", parent="base")
    base = SimpleNamespace(__file__="/tmp/theme/base.py", parent=None)

    def _import_module(name):
        if name == "wirecloud.themes.defaulttheme":
            return child
        if name == "wirecloud.themes.base":
            return base
        raise ModuleNotFoundError(name)

    def _exists(path):
        return path.endswith("defaulttheme.js.mo") or path.endswith("/wirecloud/fake/locale")

    monkeypatch.setattr(tags, "import_module", _import_module)
    monkeypatch.setattr(tags.os.path, "exists", _exists)
    monkeypatch.setattr(tags.os.path, "isdir", lambda path: path.endswith("/wirecloud/fake/locale"))

    def _translation(domain, locale_path, languages):
        if domain == "wirecloud.missing.js":
            raise FileNotFoundError("missing")
        if domain == "defaulttheme.js":
            return _FakeTranslations({"hello": "hola", ("item", 0): "item", ("item", 1): "items", "": ""})
        return _FakeTranslations({"bye": "adios"})

    monkeypatch.setattr(tags.gt, "translation", _translation)
    rendered = tags.get_javascript_catalogue("es", "defaulttheme")
    assert "js_catalogue.js" in rendered
    assert "True" in rendered


def test_get_javascript_catalogue_without_translations(monkeypatch):
    monkeypatch.setattr(tags, "templates", _FakeTemplates())
    monkeypatch.setattr(tags.settings, "INSTALLED_APPS", [])
    monkeypatch.setattr(tags, "import_module", lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("x")))
    monkeypatch.setattr(tags.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(tags.os.path, "isdir", lambda _path: False)
    rendered = tags.get_javascript_catalogue("en", "missingtheme")
    assert "js_catalogue.js" in rendered
    assert "False" in rendered


def test_get_javascript_catalogue_theme_parent_and_plugin_errors(monkeypatch):
    monkeypatch.setattr(tags, "templates", _FakeTemplates())
    monkeypatch.setattr(tags.settings, "INSTALLED_APPS", ["wirecloud.fake", "wirecloud.skip"])
    child = SimpleNamespace(__file__="/tmp/theme/child.py", parent="brokenparent")

    def _import_module(name):
        if name == "wirecloud.themes.defaulttheme":
            return child
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(tags, "import_module", _import_module)

    def _exists(path):
        if path.endswith("/wirecloud/fake/locale"):
            return True
        if path.endswith("/wirecloud/skip/locale"):
            return True
        return False

    monkeypatch.setattr(tags.os.path, "exists", _exists)
    monkeypatch.setattr(tags.os.path, "isdir", lambda path: path.endswith("/wirecloud/fake/locale"))
    monkeypatch.setattr(tags.gt, "translation", lambda *_a, **_k: (_ for _ in ()).throw(FileNotFoundError("x")))

    rendered = tags.get_javascript_catalogue("es", "defaulttheme")
    assert "js_catalogue.js" in rendered


def test_get_javascript_catalogue_theme_without_parent(monkeypatch):
    monkeypatch.setattr(tags, "templates", _FakeTemplates())
    monkeypatch.setattr(tags.settings, "INSTALLED_APPS", [])
    module = SimpleNamespace(__file__="/tmp/theme/default.py", parent=None)
    monkeypatch.setattr(tags, "import_module", lambda _name: module)
    monkeypatch.setattr(tags.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(tags.os.path, "isdir", lambda _path: False)
    rendered = tags.get_javascript_catalogue("es", "defaulttheme")
    assert "js_catalogue.js" in rendered


def test_get_javascript_catalogue_theme_parent_continue_branch(monkeypatch):
    monkeypatch.setattr(tags, "templates", _FakeTemplates())
    monkeypatch.setattr(tags.settings, "INSTALLED_APPS", [])
    child = SimpleNamespace(__file__="/tmp/themechild/child.py", parent="base")
    base = SimpleNamespace(__file__="/tmp/themebase/base.py", parent=None)

    def _import_module(name):
        if name == "wirecloud.themes.defaulttheme":
            return child
        if name == "wirecloud.themes.base":
            return base
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(tags, "import_module", _import_module)
    monkeypatch.setattr(tags.os.path, "exists", lambda path: "/tmp/themebase/" in path)
    monkeypatch.setattr(tags.os.path, "isdir", lambda _path: False)
    monkeypatch.setattr(tags.gt, "translation", lambda *_a, **_k: _FakeTranslations({"x": "y"}))
    rendered = tags.get_javascript_catalogue("es", "defaulttheme")
    assert "js_catalogue.js" in rendered
