from __future__ import annotations

from telegram import MessageEntity

from markup import Bold, Link, join, placeholders, render, utf16_len


def test_utf16_len_counts_astral_characters_as_two():
    assert utf16_len("ab") == 2
    assert utf16_len("🐉") == 2


def test_render_fills_params_and_keeps_unknown_placeholders():
    text, entities = render("Hi {name}, {missing}!", name="Vasya")
    assert text == "Hi Vasya, {missing}!"
    assert entities == []


def test_emoji_placeholder_becomes_custom_emoji(entity_text):
    text, entities = render("{check} done")
    assert text == "✅ done"
    assert entities[0].type == MessageEntity.CUSTOM_EMOJI
    assert entity_text(text, entities[0]) == "✅"


def test_bold_and_italic_offsets_after_astral_emoji(entity_text):
    text, entities = render("🐉 <b>bold</b> and <i>italic</i>")
    assert text == "🐉 bold and italic"
    assert {entity.type: entity_text(text, entity) for entity in entities} == {
        MessageEntity.BOLD: "bold",
        MessageEntity.ITALIC: "italic",
    }


def test_markup_inside_values_stays_literal():
    text, entities = render("Player: {name}", name="<b>x</b> {check}")
    assert text == "Player: <b>x</b> {check}"
    assert entities == []


def test_unclosed_tag_is_ignored():
    text, entities = render("<b>never closed")
    assert text == "never closed"
    assert entities == []


def test_link_and_bold_segments(entity_text):
    items = join([Link("Vasya", "https://t.me/vasya"), Link("plain"), Bold("strong")], ", ")
    text, entities = render("{items}", items=items)
    assert text == "Vasya, plain, strong"
    assert [(entity.type, entity_text(text, entity)) for entity in entities] == [
        (MessageEntity.TEXT_LINK, "Vasya"),
        (MessageEntity.BOLD, "strong"),
    ]
    assert entities[0].url == "https://t.me/vasya"


def test_rendered_text_as_param_keeps_its_entities(entity_text):
    inner = render("<b>{name}</b>", name="Olya")
    text, entities = render("🐉 hello {inner}", inner=inner)
    assert text == "🐉 hello Olya"
    assert entity_text(text, entities[0]) == "Olya"


def test_placeholders_skip_emoji_names():
    assert placeholders("{check} {name} and {time_left}") == {"name", "time_left"}


def test_join_flattens_line_parts():
    assert join([["a", "1"], "b"], "\n") == ["a", "1", "\n", "b"]
