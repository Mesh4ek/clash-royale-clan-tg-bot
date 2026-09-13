from __future__ import annotations

import json
import logging

from config import LOCALES_DIR, config
from markup import Param, RichText, placeholders, render

logger = logging.getLogger(__name__)

REFERENCE_LANGUAGE = "en"
MINUTES_PER_HOUR = 60

_catalog: dict[str, str] | None = None


def available_languages() -> list[str]:
    return sorted(path.stem for path in LOCALES_DIR.glob("*.json"))


def _flatten(tree: dict, prefix: str = "") -> dict:
    flat = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def _read_locale(language: str) -> dict:
    path = LOCALES_DIR / f"{language}.json"
    if not path.is_file():
        available = ", ".join(available_languages()) or "none"
        raise RuntimeError(f"BOT_LANGUAGE={language!r}: {path} not found (available: {available})")
    try:
        return _flatten(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, AttributeError) as exc:
        raise RuntimeError(f"{path}: invalid locale file: {exc}") from exc


def load_catalog(language: str) -> dict[str, str]:
    reference = _read_locale(REFERENCE_LANGUAGE)
    if language == REFERENCE_LANGUAGE:
        return reference
    translated = _read_locale(language)

    catalog = dict(reference)
    missing, mismatched = [], []
    for key, template in reference.items():
        value = translated.get(key)
        if not isinstance(value, str):
            missing.append(key)
        elif placeholders(value) != placeholders(template):
            mismatched.append(key)
        else:
            catalog[key] = value

    if missing:
        logger.warning("i18n: %s.json lacks %d key(s), using English: %s", language, len(missing), ", ".join(missing))
    if mismatched:
        logger.warning(
            "i18n: %s.json has wrong {placeholders} in %d key(s), using English: %s",
            language,
            len(mismatched),
            ", ".join(mismatched),
        )
    unknown = sorted(translated.keys() - reference.keys())
    if unknown:
        logger.warning("i18n: %s.json has unknown key(s), ignored: %s", language, ", ".join(unknown))
    return catalog


def init_i18n() -> None:
    global _catalog
    _catalog = load_catalog(config.language)
    logger.info("i18n: language %s", config.language)


def _template(key: str) -> str:
    if _catalog is None:
        init_i18n()
    return _catalog[key]


def t(key: str, **params: Param) -> str:
    return render(_template(key), **params)[0]


def rich(key: str, **params: Param) -> RichText:
    return render(_template(key), **params)


def format_number(value: float, decimals: int = 0) -> str:
    separators = {",": t("format.thousands_separator"), ".": t("format.decimal_separator")}
    return "".join(separators.get(char, char) for char in f"{value:,.{decimals}f}")


def format_duration(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, MINUTES_PER_HOUR)
    if not hours:
        return t("duration.minutes", minutes=minutes)
    if not minutes:
        return t("duration.hours", hours=hours)
    return t("duration.hours_minutes", hours=hours, minutes=minutes)
