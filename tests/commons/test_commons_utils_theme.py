# -*- coding: utf-8 -*-

from pathlib import Path
from types import SimpleNamespace

import gettext as gt
import pytest

from wirecloud.commons.utils import theme
from wirecloud.commons.utils.http import NotFound


@pytest.fixture(autouse=True)
def isolate_theme_caches(monkeypatch):
    monkeypatch.setattr(theme, "JINJA2_TEMPLATES", {})
    monkeypatch.setattr(theme, "THEME_TRANSLATIONS", {})


def test_generate_jinja2_templates(monkeypatch, tmp_path):
    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["a", "missing", "broken"])
    mod_a = SimpleNamespace(__file__=str(tmp_path / "a" / "__init__.py"), parent=None)
    mod_broken = SimpleNamespace(__file__=str(tmp_path / "broken" / "__init__.py"))

    (tmp_path / "a" / "templates").mkdir(parents=True)

    def _import(name):
        if name == "wirecloud.themes.a":
            return mod_a
        if name == "wirecloud.themes.broken":
            return mod_broken
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(theme, "import_module", _import)
    monkeypatch.setattr(theme.os.path, "exists", lambda p: "templates" in p)
    monkeypatch.setattr(theme.os.path, "isdir", lambda p: "templates" in p)

    theme.JINJA2_TEMPLATES.clear()
    with pytest.raises(ValueError):
        theme._generate_jinja2_templates()

    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["a", "missing"])
    theme.JINJA2_TEMPLATES.clear()
    theme._generate_jinja2_templates()
    assert "a" in theme.JINJA2_TEMPLATES
    assert "missing" not in theme.JINJA2_TEMPLATES
    # Continue branch when templates path does not exist
    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["no_templates"])
    mod_no_templates = SimpleNamespace(__file__=str(tmp_path / "nt" / "__init__.py"), parent=None)
    monkeypatch.setattr(theme, "import_module", lambda name: mod_no_templates if name == "wirecloud.themes.no_templates" else (_ for _ in ()).throw(ModuleNotFoundError(name)))
    monkeypatch.setattr(theme.os.path, "exists", lambda _p: False)
    monkeypatch.setattr(theme.os.path, "isdir", lambda _p: False)
    theme.JINJA2_TEMPLATES.clear()
    theme._generate_jinja2_templates()
    assert "no_templates" in theme.JINJA2_TEMPLATES
    # Explicit continue branch: exists=True but isdir=False
    monkeypatch.setattr(theme.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(theme.os.path, "isdir", lambda _p: False)
    theme.JINJA2_TEMPLATES.clear()
    theme._generate_jinja2_templates()
    assert "no_templates" in theme.JINJA2_TEMPLATES

    # Parent import failure branch
    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["child"])
    mod_child = SimpleNamespace(__file__=str(tmp_path / "child" / "__init__.py"), parent="parent")

    def _import_parent_fail(name):
        if name == "wirecloud.themes.child":
            return mod_child
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(theme, "import_module", _import_parent_fail)
    monkeypatch.setattr(theme.os.path, "exists", lambda _p: False)
    monkeypatch.setattr(theme.os.path, "isdir", lambda _p: False)
    theme.JINJA2_TEMPLATES.clear()
    theme._generate_jinja2_templates()
    assert "child" in theme.JINJA2_TEMPLATES


def test_generate_theme_translations(monkeypatch, tmp_path):
    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["a", "broken"])
    monkeypatch.setattr(theme, "LANGUAGES", [("en", "English"), ("es", "Spanish")])
    mod_a = SimpleNamespace(__file__=str(tmp_path / "a" / "__init__.py"), parent=None)
    mod_broken = SimpleNamespace(__file__=str(tmp_path / "broken" / "__init__.py"))

    def _import(name):
        if name == "wirecloud.themes.a":
            return mod_a
        if name == "wirecloud.themes.broken":
            return mod_broken
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(theme, "import_module", _import)
    monkeypatch.setattr(theme.gt, "translation", lambda *_a, **_k: gt.NullTranslations())

    theme.THEME_TRANSLATIONS.clear()
    with pytest.raises(ValueError):
        theme._generate_theme_translations()

    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["a", "missing"])
    theme.THEME_TRANSLATIONS.clear()
    theme._generate_theme_translations()
    assert "a" in theme.THEME_TRANSLATIONS
    assert "en" in theme.THEME_TRANSLATIONS["a"]
    assert "missing" not in theme.THEME_TRANSLATIONS

    # Existing cache + parent branches
    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["child"])
    monkeypatch.setattr(theme, "LANGUAGES", [("en", "English")])
    mod_child = SimpleNamespace(__file__=str(tmp_path / "child" / "__init__.py"), parent="parent")

    def _import_parent_fail(name):
        if name == "wirecloud.themes.child":
            return mod_child
        raise ModuleNotFoundError(name)

    class _FakeTrans:
        def __init__(self):
            self.fallback_added = 0

        def add_fallback(self, _other):
            self.fallback_added += 1

    monkeypatch.setattr(theme, "import_module", _import_parent_fail)
    monkeypatch.setattr(theme.gt, "translation", lambda *_a, **_k: _FakeTrans())
    theme.THEME_TRANSLATIONS.clear()
    theme.THEME_TRANSLATIONS["child"] = {}
    theme._generate_theme_translations()
    assert "en" in theme.THEME_TRANSLATIONS["child"]
    # add_fallback branch with parent resolution
    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["chain"])
    child = SimpleNamespace(__file__=str(tmp_path / "chain" / "child.py"), parent="base")
    parent = SimpleNamespace(__file__=str(tmp_path / "chain" / "base.py"), parent=None)

    def _import_chain(name):
        if name == "wirecloud.themes.chain":
            return child
        if name == "wirecloud.themes.base":
            return parent
        raise ModuleNotFoundError(name)

    class _FakeTrans:
        def __init__(self):
            self.fallback_added = 0

        def add_fallback(self, _other):
            self.fallback_added += 1

    trans = _FakeTrans()
    monkeypatch.setattr(theme, "import_module", _import_chain)
    monkeypatch.setattr(theme.gt, "translation", lambda *_a, **_k: trans)
    theme.THEME_TRANSLATIONS.clear()
    theme._generate_theme_translations()
    assert trans.fallback_added >= 1


def test_get_template_and_translation_accessors():
    theme.JINJA2_TEMPLATES.clear()
    theme.THEME_TRANSLATIONS.clear()
    theme.JINJA2_TEMPLATES["a"] = "templates"
    theme.THEME_TRANSLATIONS["a"] = {"en": gt.NullTranslations()}
    assert theme.get_jinja2_templates("a") == "templates"
    assert isinstance(theme.get_theme_translation("a", "en"), gt.NullTranslations)
    with pytest.raises(NotFound):
        theme.get_jinja2_templates("x")
    with pytest.raises(NotFound):
        theme.get_theme_translation("x", "en")
    with pytest.raises(NotFound):
        theme.get_theme_translation("a", "es")


def test_get_available_themes(monkeypatch, tmp_path):
    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["a", "missing"])
    mod_a = SimpleNamespace(
        __file__=str(tmp_path / "a" / "__init__.py"),
        label=lambda lang, tr: f"Theme-{lang}",
    )
    mod_nolabel = SimpleNamespace(__file__=str(tmp_path / "n" / "__init__.py"))

    def _import(name):
        if name == "wirecloud.themes.a":
            return mod_a
        if name == "wirecloud.themes.nolabel":
            return mod_nolabel
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(theme, "import_module", _import)
    monkeypatch.setattr(theme.gt, "translation", lambda *_a, **_k: gt.NullTranslations())
    result = theme.get_available_themes("en")
    assert result == [{"value": "a", "label": "Theme-en"}]

    monkeypatch.setattr(theme.gt, "translation", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    mod_a.label = "StaticLabel"
    result2 = theme.get_available_themes("en")
    assert result2 == [{"value": "a", "label": "StaticLabel"}]

    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["nolabel"])
    with pytest.raises(ValueError):
        theme.get_available_themes("en")


def test_get_theme_static_path(monkeypatch, tmp_path):
    monkeypatch.setattr(theme, "AVAILABLE_THEMES", ["a"])
    monkeypatch.setattr(theme, "DIST_PATH", str(tmp_path / "dist"))
    (tmp_path / "dist").mkdir()
    dist_file = tmp_path / "dist" / "x.js"
    dist_file.write_text("x")
    assert theme.get_theme_static_path("a", "x.js") == str(dist_file)

    with pytest.raises(NotFound):
        theme.get_theme_static_path("missing", "x.js")
    with pytest.raises(ValueError):
        theme.get_theme_static_path("a", "../x.js")

    monkeypatch.setattr(theme.os.path, "exists", lambda p: False)
    with pytest.raises(NotFound):
        theme.get_theme_static_path("a", "x.js")

    # Import failure after theme dir exists
    monkeypatch.setattr(
        theme.os.path,
        "exists",
        lambda p: not str(p).endswith("/dist/x.js"),
    )
    monkeypatch.setattr(theme, "import_module", lambda _n: (_ for _ in ()).throw(ModuleNotFoundError("x")))
    with pytest.raises(NotFound):
        theme.get_theme_static_path("a", "x.js")

    # Prepare full static resolution with theme + plugin fallback
    themes_dir = tmp_path / "themes"
    (themes_dir / "a" / "static").mkdir(parents=True)
    (themes_dir / "a" / "static" / "asset.js").write_text("x")
    monkeypatch.setattr(theme.themes, "__file__", str(themes_dir / "__init__.py"))

    mod_a = SimpleNamespace(__file__=str(themes_dir / "a" / "__init__.py"), parent=None)

    def _import(name):
        if name == "wirecloud.themes.a":
            return mod_a
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(theme, "import_module", _import)
    monkeypatch.setattr(theme.os.path, "exists", lambda p: Path(p).exists())
    monkeypatch.setattr(theme.os.path, "isdir", lambda p: Path(p).is_dir())
    assert theme.get_theme_static_path("a", "/asset.js").endswith("asset.js")

    # Missing parent attribute after import
    mod_bad = SimpleNamespace(__file__=str(themes_dir / "a" / "__init__.py"))
    monkeypatch.setattr(theme, "import_module", lambda name: mod_bad if name == "wirecloud.themes.a" else (_ for _ in ()).throw(ModuleNotFoundError(name)))
    with pytest.raises(ValueError):
        theme.get_theme_static_path("a", "asset.js")

    # Branch where static dir missing triggers parent import in loop
    mod_child = SimpleNamespace(__file__=str(themes_dir / "a" / "__init__.py"), parent="missingparent")
    monkeypatch.setattr(theme, "import_module", lambda name: mod_child if name == "wirecloud.themes.a" else (_ for _ in ()).throw(ModuleNotFoundError(name)))
    monkeypatch.setattr(theme.os.path, "exists", lambda p: str(p).endswith("/a"))
    with pytest.raises(ModuleNotFoundError):
        theme.get_theme_static_path("a", "asset.js")

    # Branch where static dir missing but parent import succeeds (line 176)
    parent_theme = SimpleNamespace(__file__=str(themes_dir / "parent" / "__init__.py"), parent=None)
    (themes_dir / "parent" / "static").mkdir(parents=True)
    (themes_dir / "parent" / "static" / "from-parent.js").write_text("x")

    def _import_parent_ok(name):
        if name == "wirecloud.themes.a":
            return SimpleNamespace(__file__=str(themes_dir / "a" / "__init__.py"), parent="parent")
        if name == "wirecloud.themes.parent":
            return parent_theme
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(theme, "import_module", _import_parent_ok)
    monkeypatch.setattr(theme.os.path, "exists", lambda p: Path(p).exists() and "a/static" not in str(p))
    assert theme.get_theme_static_path("a", "from-parent.js").endswith("from-parent.js")

    # Branch where parent is None and file is not found in static (line 183)
    monkeypatch.setattr(theme, "import_module", lambda name: parent_theme if name == "wirecloud.themes.a" else (_ for _ in ()).throw(ModuleNotFoundError(name)))
    monkeypatch.setattr(theme.os.path, "exists", lambda p: Path(p).exists() and "from-parent.js" not in str(p))
    with pytest.raises(NotFound):
        theme.get_theme_static_path("a", "from-parent.js")

    # Plugin fallback
    plugin_dir = tmp_path / "pluginpkg"
    (plugin_dir / "static").mkdir(parents=True)
    (plugin_dir / "static" / "p.js").write_text("x")
    plugin_file = plugin_dir / "plugins.py"
    plugin_file.write_text("# x")

    core_dir = tmp_path / "corepkg" / "core"
    (core_dir / "static").mkdir(parents=True)
    (core_dir / "static" / "core.js").write_text("x")
    core_file = core_dir / "plugins.py"
    core_file.write_text("# x")

    class _Plugin:
        pass

    _Plugin.__module__ = "pluginpkg.plugins"

    class _WirecloudCorePlugin:
        pass

    _WirecloudCorePlugin.__module__ = "corepkg.core.plugins"
    plugin_instance = _Plugin()
    core_instance = _WirecloudCorePlugin()
    monkeypatch.setattr(theme.inspect, "getfile", lambda cls: str(core_file if cls is _WirecloudCorePlugin else plugin_file))
    monkeypatch.setattr(theme, "get_plugins", lambda: [core_instance, plugin_instance])

    import wirecloud.platform.core.plugins as core_plugins
    monkeypatch.setattr(core_plugins, "WirecloudCorePlugin", _WirecloudCorePlugin)

    # Hide theme static so plugin fallback executes
    monkeypatch.setattr(theme.os.path, "exists", lambda p: Path(p).exists() and "asset.js" not in str(p))
    assert theme.get_theme_static_path("a", "p.js").endswith("p.js")

    # Parent import failure in fallback branch (185-188)
    mod_parent_missing = SimpleNamespace(__file__=str(themes_dir / "a" / "__init__.py"), parent="missingparent")
    monkeypatch.setattr(
        theme,
        "import_module",
        lambda name: mod_parent_missing if name == "wirecloud.themes.a" else (_ for _ in ()).throw(ModuleNotFoundError(name)),
    )
    monkeypatch.setattr(theme.os.path, "exists", lambda p: Path(p).exists() and "static/asset.js" not in str(p))
    assert theme.get_theme_static_path("a", "p.js").endswith("p.js")

    with pytest.raises(NotFound):
        theme.get_theme_static_path("a", "missing.js")
