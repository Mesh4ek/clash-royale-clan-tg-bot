from __future__ import annotations

import dataclasses
import os
import tempfile
from pathlib import Path

import pytest

# The bot reads its settings when its modules are first imported, so they must be set before any test imports them.
# Every variable is set explicitly so that a developer's own .env can't leak into the tests.
os.environ.update(
    {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TELEGRAM_GROUP_ID": "-1001234567890",
        "CLASH_API_TOKEN": "test-clash-token",
        "CLAN_TAG": "#CLAN",
        "LOGS_ALLOWED_TG_IDS": "111,222",
        "BOT_LANGUAGE": "en",
        "WEEKLY_DATA_BACKUP": "1",
        "WAR_DAY_END_UTC": "9",
        "WAR_DAY_END_MINUTE": "30",
        "WAR_REMINDER_UTC": "9",
        "WAR_REMINDER_MINUTE": "0",
        "CLASH_LOCATION_ID": "",
        "TELEGRAM_PROXY": "",
        "HTTPS_PROXY": "",
        "DATABASE_PATH": str(Path(tempfile.mkdtemp(prefix="clan-bot-tests-")) / "database.db"),
    }
)


@pytest.fixture(scope="session")
def english_catalog():
    import i18n

    return i18n.load_catalog("en")


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch, english_catalog):
    import database
    import i18n
    import war_schedule
    from config import config

    test_config = dataclasses.replace(config, database_path=str(tmp_path / "database.db"))
    monkeypatch.setattr(database, "config", test_config)
    monkeypatch.setattr(war_schedule, "config", test_config)
    monkeypatch.setattr(database, "_connection", None)
    monkeypatch.setattr(war_schedule, "_state", None)
    monkeypatch.setattr(i18n, "_catalog", english_catalog)
    yield
    if database._connection is not None:
        database._connection.close()


@pytest.fixture
def entity_text():
    def extract(text, entity):
        raw = text.encode("utf-16-le")
        return raw[entity.offset * 2 : (entity.offset + entity.length) * 2].decode("utf-16-le")

    return extract
