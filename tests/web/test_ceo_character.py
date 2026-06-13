# tests/web/test_ceo_character.py
"""Pure file-content checks for the CEO character feature — no browser required."""
from __future__ import annotations

from pathlib import Path

_STATIC = Path(__file__).parent.parent.parent / "src" / "infrastructure" / "web" / "static"
_JS  = _STATIC / "ceo_character.js"
_CSS = _STATIC / "ceo_character.css"
_HTML = _STATIC / "kingdom.html"


def test_js_file_exists() -> None:
    assert _JS.exists(), "ceo_character.js must exist in static/"


def test_css_file_exists() -> None:
    assert _CSS.exists(), "ceo_character.css must exist in static/"


def test_kingdom_html_includes_css() -> None:
    html = _HTML.read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/static/ceo_character.css">' in html, (
        "kingdom.html must include the CSS link"
    )


def test_kingdom_html_includes_js() -> None:
    html = _HTML.read_text(encoding="utf-8")
    assert '<script src="/static/ceo_character.js"></script>' in html, (
        "kingdom.html must include the JS script tag"
    )


def test_no_math_random_in_js() -> None:
    js = _JS.read_text(encoding="utf-8")
    assert "Math.random()" not in js, (
        "ceo_character.js must not use Math.random() — use mulberry32 PRNG instead"
    )


def test_no_invented_price_literal_in_js() -> None:
    js = _JS.read_text(encoding="utf-8")
    assert "1284567.89" not in js, (
        "ceo_character.js must not contain hardcoded price literals"
    )


def test_js_contains_mulberry32() -> None:
    js = _JS.read_text(encoding="utf-8")
    assert "mulberry32" in js, "ceo_character.js must define the mulberry32 PRNG"


def test_js_contains_speech_synthesis() -> None:
    js = _JS.read_text(encoding="utf-8")
    assert "speechSynthesis" in js, "ceo_character.js must reference speechSynthesis for TTS"


_ALL_20_EMOTIONS = [
    "neutral", "happy", "ecstatic", "excited", "confident", "satisfied",
    "calm", "determined", "focused", "curious", "cautious", "anxious",
    "stressed", "tired", "worried", "frustrated", "overwhelmed",
    "panicked", "angry", "sleeping",
]


def test_all_20_emotion_ids_present_in_js() -> None:
    js = _JS.read_text(encoding="utf-8")
    missing = [eid for eid in _ALL_20_EMOTIONS if eid not in js]
    assert not missing, f"Missing emotion ids in ceo_character.js: {missing}"


def test_css_has_ceo_layer_selector() -> None:
    css = _CSS.read_text(encoding="utf-8")
    assert "#ceo-layer" in css


def test_css_has_bob_animation() -> None:
    css = _CSS.read_text(encoding="utf-8")
    assert "ceo-bob" in css


def test_css_has_wave_animation() -> None:
    css = _CSS.read_text(encoding="utf-8")
    assert "ceo-wave" in css
