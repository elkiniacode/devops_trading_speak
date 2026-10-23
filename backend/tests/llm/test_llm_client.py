import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.llm import client
from app.llm.schemas import ChatReply


def fake_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def fake_litellm(monkeypatch):
    """Stand-in for the litellm module (the real one takes seconds to import and would call out)."""
    module = ModuleType("litellm")
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


async def test_call_matches_the_cerebras_skill(fake_litellm):
    calls = []

    async def acompletion(**kwargs):
        calls.append(kwargs)
        return fake_response('{"message": "hi", "trades": [], "watchlist_changes": []}')

    fake_litellm.acompletion = acompletion
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    assert await client.complete(messages) == '{"message": "hi", "trades": [], "watchlist_changes": []}'

    (kwargs,) = calls
    assert kwargs == {
        "model": "openrouter/openai/gpt-oss-120b",
        "messages": messages,
        "response_format": ChatReply,
        "reasoning_effort": "low",
        "extra_body": {"provider": {"order": ["cerebras"]}},
        "timeout": 30.0,
    }


async def test_whole_call_is_bounded_by_the_timeout(fake_litellm, monkeypatch):
    async def hangs(**kwargs):
        await asyncio.sleep(10)

    fake_litellm.acompletion = hangs
    monkeypatch.setattr(client, "TIMEOUT_SECONDS", 0.05)
    with pytest.raises(TimeoutError):
        await client.complete([{"role": "user", "content": "u"}])


async def test_provider_errors_propagate(fake_litellm):
    async def fails(**kwargs):
        raise ConnectionError("openrouter unreachable")

    fake_litellm.acompletion = fails
    with pytest.raises(ConnectionError):
        await client.complete([{"role": "user", "content": "u"}])



async def test_preload_imports_the_module(fake_litellm):
    assert await client._litellm() is fake_litellm
    await client.preload()
