from __future__ import annotations

import json

import pytest

import i18n
from markup import placeholders

BUNDLED_LOCALES_DIR = i18n.LOCALES_DIR
TRANSLATIONS = [language for language in i18n.available_languages() if language != i18n.REFERENCE_LANGUAGE]


@pytest.mark.parametrize("language", TRANSLATIONS)
def test_bundled_translation_matches_english(language):
    reference = i18n._read_locale(i18n.REFERENCE_LANGUAGE)
    translated = i18n._read_locale(language)
    assert translated.keys() == reference.keys()
    for key, template in reference.items():
        assert placeholders(translated[key]) == placeholders(template), key


def _write_locales(directory, translated):
    english = (BUNDLED_LOCALES_DIR / "en.json").read_text(encoding="utf-8")
    (directory / "en.json").write_text(english, encoding="utf-8")
    (directory / "xx.json").write_text(json.dumps(translated, ensure_ascii=False), encoding="utf-8")


def test_broken_translation_falls_back_to_english(tmp_path, monkeypatch, caplog, english_catalog):
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    _write_locales(
        tmp_path,
        {"war": {"someone": "Хтось", "manual_reminder": "{warning} {time_left} {mentions} {лейбл}", "extra": "?"}},
    )

    catalog = i18n.load_catalog("xx")

    assert catalog["war.someone"] == "Хтось"
    assert catalog["war.manual_reminder"] == english_catalog["war.manual_reminder"]
    assert catalog["commands.war"] == english_catalog["commands.war"]
    assert "lacks" in caplog.text
    assert "wrong {placeholders}" in caplog.text
    assert "war.extra" in caplog.text


def test_unknown_language_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    _write_locales(tmp_path, {})
    with pytest.raises(RuntimeError, match="zz"):
        i18n.load_catalog("zz")


def test_invalid_json_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    _write_locales(tmp_path, {})
    (tmp_path / "xx.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="invalid locale file"):
        i18n.load_catalog("xx")


@pytest.mark.parametrize(("minutes", "expected"), [(0, "0 min"), (45, "45 min"), (60, "1 h"), (150, "2 h 30 min")])
def test_format_duration(minutes, expected):
    assert i18n.format_duration(minutes) == expected


def test_format_number_uses_locale_separators(monkeypatch):
    assert i18n.format_number(30950) == "30,950"
    assert i18n.format_number(149.04, decimals=1) == "149.0"

    monkeypatch.setattr(i18n, "_catalog", i18n.load_catalog("uk"))
    assert i18n.format_number(30950) == "30 950"
    assert i18n.format_number(149.04, decimals=1) == "149,0"
