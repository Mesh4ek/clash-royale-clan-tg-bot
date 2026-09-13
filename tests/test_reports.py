from __future__ import annotations

from datetime import date, datetime, timezone

from telegram import MessageEntity

import reports
from database import Player
from markup import Link
from war_days import DayDecks

PLAYERS = [
    Player(1, "vasya", "#P1", "Vasya"),
    Player(1, "vasya", "#P2", "Vasya twink"),
    Player(2, None, "#P3", "Petro"),
]


def test_today_report_lists_registered_players_first(entity_text):
    members = {"#P1": "Vasya", "#P2": "Vasya twink", "#P3": "Petro", "#X": "stranger", "#Y": "Alpha"}
    decks = {"#P1": 1, "#P2": 4, "#P3": 0, "#X": 2}

    text, entities = reports.build_today_report(PLAYERS, members, decks)

    assert text == (
        "Decks not used today:\n\nVasya (3/4)\nPetro (4/4)\n\nNot in the Telegram group:\nAlpha (4/4)\nstranger (2/4)"
    )
    links = {entity_text(text, entity): entity.url for entity in entities if entity.type == MessageEntity.TEXT_LINK}
    assert links == {"Vasya": "https://t.me/vasya", "Petro": "tg://user?id=2"}


def test_today_report_when_everyone_played():
    text, _ = reports.build_today_report(PLAYERS, {"#P1": "Vasya"}, {"#P1": 4, "#P2": 4, "#P3": 4})
    assert text == "Decks not used today:\n\n🎉 All decks used! Well done!"


def test_day_report_lists_plain_nicknames_by_missing_decks():
    decks = DayDecks(by_tag={"#A": 4, "#B": 1, "#C": 3}, members={"#A": "Zed", "#B": "bob", "#C": "Carl", "#D": "Dan"})
    text, entities = reports.build_day_report(decks, 1, date(2026, 9, 10))
    assert text == "Decks not used · day 1, 10.09:\n\nDan (4/4)\nbob (3/4)\nCarl (1/4)"
    assert entities == []


def test_approximate_day_report_says_when_the_data_is_from():
    decks = DayDecks(by_tag={}, members={}, as_of=datetime(2026, 9, 11, 15, 0, tzinfo=timezone.utc))
    text, _ = reports.build_day_report(decks, 2, date(2026, 9, 11))
    assert "All decks were used that day!" in text
    assert text.endswith("Approximate: the bot's latest data for that day is from 11.09 15:00 UTC.")


def test_mentions_merge_accounts_of_one_person():
    war_rows = [("Vasya", 3, "vasya"), ("Vasya twink", 1, "vasya"), ("Petro", 4, None)]
    mentions = reports.build_unique_mentions(PLAYERS, war_rows)
    assert [(mention.label, mention.url) for mention in mentions] == [
        ("@vasya (+1)", None),
        ("Petro", "tg://user?id=2"),
    ]


def test_manual_reminder_links_players_without_username(entity_text):
    text, entities = reports.build_manual_reminder(
        [Link("@vasya"), Link("Petro 🐉", "tg://user?id=2")], "2 h", "@admin"
    )
    assert text.endswith("@vasya Petro 🐉\n\nNotified by: @admin")
    link = next(entity for entity in entities if entity.type == MessageEntity.TEXT_LINK)
    assert entity_text(text, link) == "Petro 🐉"


def test_players_tsv():
    tsv = reports.format_players_tsv([Player(1, None, "#P1", "Vasya", 0)])
    assert tsv.splitlines() == ["telegram_id\ttelegram_username\tplayer_tag\tclash_name\tactive", "1\t\t#P1\tVasya\t0"]
