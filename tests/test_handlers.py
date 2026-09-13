from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import war_schedule
from database import get_players_by_tg, save_player, set_active_by_tg
from handlers import admin, registration
from handlers.registration import GroupRemoval

ADMIN_ID = 111
STRANGER_ID = 999


class FakeBot:
    def __init__(self, status="member", fail=False):
        self.status = status
        self.fail = fail
        self.calls = []

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status=self.status)

    async def promote_chat_member(self, chat_id, user_id, **rights):
        self.calls.append(("promote", any(rights.values())))

    async def unban_chat_member(self, chat_id, user_id, only_if_banned=False):
        if self.fail:
            raise RuntimeError("Not enough rights to restrict/unrestrict chat member")
        self.calls.append(("unban", only_if_banned))

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append(("send", text))


def message_update(user_id, replies):
    async def reply_text(text, **kwargs):
        replies.append(text)

    return SimpleNamespace(
        message=SimpleNamespace(reply_text=reply_text),
        effective_user=SimpleNamespace(id=user_id),
        callback_query=None,
    )


def callback_update(data, user_id=ADMIN_ID):
    answers, edits = [], []

    async def answer(**kwargs):
        answers.append(kwargs)

    async def edit_message_text(text, **kwargs):
        edits.append(text)

    query = SimpleNamespace(data=data, answer=answer, edit_message_text=edit_message_text)
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id)), answers, edits


def chat_member_update(user_id, username, full_name, old_status, new_status):
    user = SimpleNamespace(id=user_id, username=username, full_name=full_name)
    return SimpleNamespace(
        chat_member=SimpleNamespace(
            chat=SimpleNamespace(id=-1001234567890),
            old_chat_member=SimpleNamespace(status=old_status, user=user),
            new_chat_member=SimpleNamespace(status=new_status, user=user),
        )
    )


@pytest.fixture(autouse=True)
def no_pending_removals(monkeypatch):
    monkeypatch.setattr(registration, "_removed_by_bot", {})


@pytest.fixture
def registered():
    save_player(1, "vasya", "#P1", "Vasya")
    save_player(1, "vasya", "#P2", "Vasya twink")
    set_active_by_tg(1, True)


@pytest.mark.parametrize("args", [["boundary", "8"], ["boundary", "25", "0"], ["reminder", "x", "y"], ["auto", "9"]])
def test_time_rejects_bad_clock(args):
    with pytest.raises(ValueError):
        admin._apply_time_change(args)


@pytest.mark.parametrize("args", [["notify"], ["notify", "0"], ["notify", "25"], ["notify", "x"]])
def test_time_notify_rejects_bad_hours(args):
    with pytest.raises(admin._InvalidHoursError):
        admin._apply_time_change(args)


def test_time_unknown_subcommand():
    with pytest.raises(KeyError):
        admin._apply_time_change(["foo"])


def test_time_auto_sets_end_and_reminder():
    assert admin._apply_time_change(["auto", "9", "50"]) == "✅ War day end set to 09:50, group reminder to 09:20"
    assert war_schedule.get_war_reminder() == (9, 20)


def test_admin_commands_refuse_other_users():
    replies = []
    asyncio.run(admin.time_cmd(message_update(STRANGER_ID, replies), SimpleNamespace(args=[])))
    assert replies == ["Not allowed."]


def test_time_change_reply_warns_without_job_queue():
    replies = []
    context = SimpleNamespace(args=["notify", "8"], application=SimpleNamespace(job_queue=None))
    asyncio.run(admin.time_cmd(message_update(ADMIN_ID, replies), context))
    assert replies[0].startswith("✅ “Notify everyone” allowed from 01:30 (8 h before end)")
    assert replies[0].endswith("Job queue isn't running — the reminder and backup won't be sent.")


def test_unregister_one_twink_keeps_player_in_group(registered):
    bot = FakeBot()
    update, _, edits = callback_update("unreg:tag:#P2")
    asyncio.run(admin.unregister_confirm(update, SimpleNamespace(bot=bot)))
    assert [player.player_tag for player in get_players_by_tg(1)] == ["#P1"]
    assert "other accounts remain" in edits[0]
    assert bot.calls == []


def test_unregister_all_accounts_removes_player_without_ban(registered):
    bot = FakeBot(status="administrator")
    update, _, edits = callback_update("unreg:user:1")
    asyncio.run(admin.unregister_confirm(update, SimpleNamespace(bot=bot)))
    assert get_players_by_tg(1) == []
    assert bot.calls == [("promote", False), ("unban", False)]
    assert "Also removed from the Telegram group" in edits[0]


def test_unregister_buttons_refuse_other_users(registered):
    update, answers, _ = callback_update("unreg:user:1", user_id=STRANGER_ID)
    asyncio.run(admin.unregister_confirm(update, SimpleNamespace(bot=FakeBot())))
    assert answers == [{"text": "Not allowed.", "show_alert": True}]
    assert len(get_players_by_tg(1)) == 2


def test_farewell_after_unregister_uses_clash_name(registered):
    bot = FakeBot()
    update, _, _ = callback_update("unreg:user:1")
    asyncio.run(admin.unregister_confirm(update, SimpleNamespace(bot=bot)))
    asyncio.run(
        registration.member_left(chat_member_update(1, "vasya", "Василь", "member", "left"), SimpleNamespace(bot=bot))
    )
    assert bot.calls[-1] == ("send", "🚫 Vasya (@vasya) was removed from the group.")


@pytest.mark.parametrize(
    ("old_status", "new_status", "expected"),
    [
        ("member", "left", "🚪 Stranger (@stranger) left the group."),
        ("member", "kicked", "🚫 Stranger (@stranger) was removed from the group."),
        ("kicked", "left", None),
        ("member", "administrator", None),
    ],
)
def test_member_left_messages(old_status, new_status, expected):
    bot = FakeBot()
    update = chat_member_update(5, "stranger", "Stranger", old_status, new_status)
    asyncio.run(registration.member_left(update, SimpleNamespace(bot=bot)))
    assert [text for kind, text in bot.calls if kind == "send"] == ([expected] if expected else [])


@pytest.mark.parametrize(
    ("status", "fail", "expected"),
    [
        ("left", False, GroupRemoval.NOT_MEMBER),
        ("creator", False, GroupRemoval.FAILED),
        ("member", True, GroupRemoval.FAILED),
        ("member", False, GroupRemoval.REMOVED),
    ],
)
def test_remove_from_group_outcomes(status, fail, expected):
    bot = FakeBot(status=status, fail=fail)
    assert asyncio.run(registration.remove_from_group(SimpleNamespace(bot=bot), 7, "Name")) is expected
    assert registration._removed_by_bot == ({7: "Name"} if expected is GroupRemoval.REMOVED else {})
