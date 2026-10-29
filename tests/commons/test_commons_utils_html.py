# -*- coding: utf-8 -*-

from wirecloud.commons.utils import html
from wirecloud.commons.utils.version import Version


def test_clean_html_removes_unsafe_and_fixes_links():
    code = """
    <?x test?>
    <script>alert(1)</script>
    <audio src="a.mp3"></audio>
    <video src="v.mp4"></video>
    <img src="img.png" onload="x()"/>
    <a href="/relative/path">Rel</a>
    <a href="https://example.com/path">Abs</a>
    <source src="s.mp4"/>
    """
    cleaned = html.clean_html(code, base_url="https://cdn.example.com/base/")
    assert "script" not in cleaned
    assert "audio" not in cleaned
    assert "onload" not in cleaned
    assert 'controls="controls"' in cleaned
    assert "https://cdn.example.com/base/img.png" in cleaned
    assert "https://cdn.example.com/base/v.mp4" in cleaned
    assert "https://cdn.example.com/base/s.mp4" in cleaned
    assert "target=\"_blank\"" in cleaned
    assert "relative/path" not in cleaned


def test_clean_html_without_base_url():
    cleaned = html.clean_html('<img src="img.png"/><a href="https://example.com">x</a>')
    assert 'src="img.png"' in cleaned
    assert 'target="_blank"' in cleaned


def test_clean_html_closes_empty_elements():
    # The result is parsed as HTML, where `<i class="fas fa-crosshairs"/>`
    # would wrap the rest of the document
    cleaned = html.clean_html('<p>Use the <i class="fas fa-crosshairs"></i> button<br/><img src="a.png"/></p>')
    assert '<i class="fas fa-crosshairs"></i> button' in cleaned
    assert '<br/><img src="a.png"/>' in cleaned


def test_filter_changelog_versions():
    code = """
    <h2>v2.0.0 (latest)</h2><p>n2</p>
    <h2>1.5.0</h2><p>n15</p>
    <h2>invalid</h2><p>ignored</p>
    <h2>1.0.0</h2><p>old</p>
    """
    filtered = html.filter_changelog(code, Version("1.4.0"))
    assert "v2.0.0" in filtered
    assert "1.5.0" in filtered
    assert "1.0.0" not in filtered

    filtered_all = html.filter_changelog(code, Version("0.9.0"))
    assert "1.0.0" in filtered_all


def test_filter_changelog_with_invalid_header_and_preceding_cleanup():
    code = """
    <p>intro</p>
    <h2>invalid</h2><p>ignored</p>
    <h2>v2.0.0</h2><p>n2</p>
    <h2>1.0.0</h2><p>old</p>
    """
    filtered = html.filter_changelog(code, Version("1.5.0"))
    assert "intro" not in filtered
    assert "invalid" not in filtered
    assert "v2.0.0" in filtered
    assert "1.0.0" not in filtered


def test_filter_changelog_without_valid_versions():
    code = "<h2>invalid</h2><p>text</p>"
    filtered = html.filter_changelog(code, Version("1.0.0"))
    assert "invalid" in filtered
