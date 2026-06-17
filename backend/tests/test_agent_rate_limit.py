from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage
from groq import RateLimitError

from app.agent.graph import ChiefOfStaffAgent
from app.core.config import Settings


def _make_agent() -> ChiefOfStaffAgent:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        groq_api_key="test-key",
        groq_model_name="llama-3.3-70b-versatile",
        groq_fallback_model_name="qwen/qwen3-32b",
        groq_fallback_models="openai/gpt-oss-120b",
    )
    memory_service = MagicMock()
    memory_service.search_relevant_memories.return_value = []
    memory_service.extract_memories_from_message.return_value = []
    return ChiefOfStaffAgent(settings=settings, memory_service=memory_service)


def test_rate_limit_returns_friendly_message_instead_of_raising() -> None:
    agent = _make_agent()
    state = {
        "organization_id": "00000000-0000-0000-0000-000000000001",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "user_message": "Hello",
        "conversation_history": [],
        "memories": [],
        "messages": [],
    }
    agent._retrieve_memory(state)  # type: ignore[arg-type]
    agent._prepare_messages(state)  # type: ignore[arg-type]

    rate_limit = RateLimitError(
        "Rate limit reached",
        response=MagicMock(status_code=429),
        body={"error": {"message": "Rate limit reached"}},
    )

    with patch.object(agent, "_invoke_llm", side_effect=rate_limit):
        agent_node = agent._make_agent_node([])
        result = agent_node(state)  # type: ignore[arg-type]

    assert "rate" in result["assistant_response"].lower() or "token" in result["assistant_response"].lower()
    assert result["messages"][-1].content == result["assistant_response"]


def test_invoke_llm_falls_back_through_model_chain_on_rate_limit() -> None:
    agent = _make_agent()
    rate_limit = RateLimitError(
        "Rate limit reached",
        response=MagicMock(status_code=429),
        body={"error": {"message": "Rate limit reached"}},
    )

    primary = MagicMock()
    primary.invoke.side_effect = rate_limit
    fallback = MagicMock()
    fallback.invoke.return_value = AIMessage(content="Fallback reply")

    with patch.object(agent, "_build_llm") as build_llm:
        build_llm.side_effect = lambda *, model_name=None: (
            primary if model_name == "llama-3.3-70b-versatile" else fallback
        )

        response = agent._invoke_llm([], [])

    assert response.content == "Fallback reply"
    build_llm.assert_any_call(model_name="qwen/qwen3-32b")
