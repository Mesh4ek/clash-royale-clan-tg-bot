from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import NamedTuple

from telegram import MessageEntity

from emoji_ids import EMOJI_FALLBACK, EMOJI_IDS

_TOKEN = re.compile(r"\{(\w+)\}|<(/?)([bi])>")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_STYLES = {"b": MessageEntity.BOLD, "i": MessageEntity.ITALIC}


class RichText(NamedTuple):
    text: str
    entities: list[MessageEntity]


class Link(NamedTuple):
    label: str
    url: str | None = None


class Bold(NamedTuple):
    text: str


Segment = str | int | Link | Bold | RichText
Param = Segment | Sequence[Segment]
_SINGLE_SEGMENT = (str, int, Link, Bold, RichText)


def utf16_len(text: str) -> int:
    return sum(2 if ord(char) > 0xFFFF else 1 for char in text)


def placeholders(template: str) -> set[str]:
    # Emoji placeholders are left out: a translation may drop or move them freely.
    return {name for name in _PLACEHOLDER.findall(template) if name not in EMOJI_FALLBACK}


def join(parts: Iterable[Param], separator: str) -> list[Segment]:
    segments: list[Segment] = []
    for index, part in enumerate(parts):
        if index:
            segments.append(separator)
        segments.extend([part] if isinstance(part, _SINGLE_SEGMENT) else part)
    return segments


def _shifted(entity: MessageEntity, offset: int) -> MessageEntity:
    return MessageEntity(
        type=entity.type,
        offset=entity.offset + offset,
        length=entity.length,
        url=entity.url,
        user=entity.user,
        language=entity.language,
        custom_emoji_id=entity.custom_emoji_id,
    )


class _Builder:
    def __init__(self) -> None:
        self.text = ""
        self.offset = 0
        self.entities: list[MessageEntity] = []

    def add(self, chunk: str, entity_type: str | None = None, **entity_fields: str) -> None:
        length = utf16_len(chunk)
        if entity_type and length:
            self.entities.append(MessageEntity(type=entity_type, offset=self.offset, length=length, **entity_fields))
        self.text += chunk
        self.offset += length

    def add_param(self, value: Param) -> None:
        for segment in [value] if isinstance(value, _SINGLE_SEGMENT) else value:
            self.add_segment(segment)

    def add_segment(self, segment: Segment) -> None:
        if isinstance(segment, RichText):
            self.entities.extend(_shifted(entity, self.offset) for entity in segment.entities)
            self.add(segment.text)
        elif isinstance(segment, Link) and segment.url:
            self.add(segment.label, MessageEntity.TEXT_LINK, url=segment.url)
        elif isinstance(segment, Link):
            self.add(segment.label)
        elif isinstance(segment, Bold):
            self.add(segment.text, MessageEntity.BOLD)
        else:
            self.add(str(segment))

    def add_emoji(self, name: str) -> None:
        emoji_id = EMOJI_IDS.get(name)
        if emoji_id:
            self.add(EMOJI_FALLBACK[name], MessageEntity.CUSTOM_EMOJI, custom_emoji_id=emoji_id)
        else:
            self.add(EMOJI_FALLBACK[name])


def render(template: str, **params: Param) -> RichText:
    # Markup is parsed in the template only, so <b> or {wave} inside a value (e.g. a player name) stays literal.
    builder = _Builder()
    style_starts: dict[str, int] = {}
    position = 0
    for match in _TOKEN.finditer(template):
        builder.add(template[position : match.start()])
        position = match.end()
        name, closing, style = match.groups()
        if style and not closing:
            style_starts[style] = builder.offset
        elif style:
            start = style_starts.pop(style, None)
            if start is not None and builder.offset > start:
                builder.entities.append(MessageEntity(type=_STYLES[style], offset=start, length=builder.offset - start))
        elif name in params:
            builder.add_param(params[name])
        elif name in EMOJI_FALLBACK:
            builder.add_emoji(name)
        else:
            builder.add(match.group(0))
    builder.add(template[position:])
    return RichText(builder.text, sorted(builder.entities, key=lambda entity: entity.offset))
