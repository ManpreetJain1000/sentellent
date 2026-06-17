from __future__ import annotations

from typing import Annotated, Literal, TypedDict
from uuid import UUID

from datetime import timedelta

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_groq import ChatGroq
from groq import BadRequestError, RateLimitError
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agent.checkpoint import build_checkpoint_config, get_checkpointer
from app.agent.tools import WorkspaceToolContext, build_workspace_tools
from app.core.config import Settings
from app.services.memory import MemoryService
from app.services.timezone_utils import format_local_datetime, now_in_timezone


class AgentState(TypedDict):
    organization_id: str
    user_id: str
    conversation_id: str
    user_message: str
    conversation_history: list[tuple[str, str]]
    memories: list[str]
    messages: Annotated[list[BaseMessage], add_messages]
    assistant_response: str
    extracted_memories: list[dict[str, str]]
    email_memories_persisted: int


class ChiefOfStaffAgent:
    SYSTEM_PROMPT = (
        "You are Sentellent, a chief-of-staff AI assistant connected to the user's Google Workspace. "
        "Use stored preferences and facts when answering. "
        "When the user asks about inbox, email, schedule, meetings, or calendar, use the available tools. "
        "To delete/cancel a meeting, ALWAYS list_calendar_events_for_date first — memory may be outdated. "
        "Use the local start time from the list result, not old memory. "
        "Then delete_calendar_event_by_time or delete_calendar_event with the event id. "
        "After reading email, summarize what matters and mention any facts you stored in memory. "
        "When scheduling, honor preferences such as avoiding 9 AM or morning meetings. "
        "When scheduling a meeting with another person, always include their email in create_calendar_event attendees "
        "so they receive a Google Calendar invitation. "
        "Treat all meeting times as the user's local timezone unless they explicitly say otherwise. "
        "Be concise, proactive, and accurate. Only claim actions you completed via tools."
    )

    def _scheduling_context(self) -> str:
        timezone_name = self.settings.default_timezone
        now = now_in_timezone(timezone_name)
        tomorrow = (now + timedelta(days=1)).date()
        return (
            f"Scheduling context:\n"
            f"- User timezone: {timezone_name}\n"
            f"- Current local time: {format_local_datetime(now)}\n"
            f"- Tomorrow's date (local): {tomorrow.isoformat()}\n"
            f"- When calling create_calendar_event, use start_local/end_local in {timezone_name} "
            f"as YYYY-MM-DDTHH:MM:SS with NO Z suffix.\n"
            f"- Example: 3 PM tomorrow → start_local={tomorrow.isoformat()}T15:00:00\n"
            f"- Do NOT use UTC/Z suffix. Trust list_calendar_events_for_date over agent memory for event times.\n"
            f"- When scheduling with others, pass attendees as comma-separated emails so invitations are sent."
        )

    def __init__(self, *, settings: Settings, memory_service: MemoryService) -> None:
        self.settings = settings
        self.memory_service = memory_service
        self._checkpointer = None

    @property
    def checkpointer(self):
        if self._checkpointer is None:
            self._checkpointer = get_checkpointer(self.settings.sqlalchemy_database_url)
        return self._checkpointer

    def _build_llm(self, *, model_name: str | None = None) -> ChatGroq | None:
        if not self.settings.groq_api_key:
            return None
        return ChatGroq(
            api_key=self.settings.groq_api_key,
            model_name=model_name or self.settings.groq_model_name,
            temperature=0.2,
        )

    @staticmethod
    def _rate_limit_message() -> str:
        return (
            "All configured Groq models hit their rate or token limits. "
            "Wait a few minutes and try again, or switch GROQ_MODEL_NAME to another model "
            "such as qwen/qwen3-32b or openai/gpt-oss-120b in backend/.env."
        )

    def _invoke_llm(self, tools: list[StructuredTool], messages: list[BaseMessage]) -> BaseMessage:
        last_rate_limit: RateLimitError | None = None
        for model_name in self.settings.groq_model_chain:
            llm = self._build_llm(model_name=model_name)
            if llm is None:
                continue
            llm_with_tools = llm.bind_tools(tools) if tools else llm
            try:
                return llm_with_tools.invoke(messages)
            except RateLimitError as exc:
                last_rate_limit = exc
                continue
        if last_rate_limit is not None:
            raise last_rate_limit
        raise RuntimeError("No Groq models are configured")

    def _build_graph(self, tools: list[StructuredTool]):
        graph = StateGraph(AgentState)
        graph.add_node("retrieve_memory", self._retrieve_memory)
        graph.add_node("prepare_messages", self._prepare_messages)
        graph.add_node("agent", self._make_agent_node(tools))
        graph.add_node("extract_memory", self._extract_memory)

        graph.set_entry_point("retrieve_memory")
        graph.add_edge("retrieve_memory", "prepare_messages")
        graph.add_edge("prepare_messages", "agent")

        if tools:
            tool_node = ToolNode(tools)
            graph.add_node("tools", tool_node)
            graph.add_conditional_edges(
                "agent",
                self._route_after_agent,
                {"tools": "tools", "finish": "extract_memory"},
            )
            graph.add_edge("tools", "agent")
        else:
            graph.add_edge("agent", "extract_memory")

        graph.add_edge("extract_memory", END)
        return graph.compile(checkpointer=self.checkpointer)

    def _retrieve_memory(self, state: AgentState) -> AgentState:
        memories = self.memory_service.search_relevant_memories(
            organization_id=UUID(state["organization_id"]),
            user_id=UUID(state["user_id"]),
            query=state["user_message"],
            limit=3,
        )
        state["memories"] = [memory.content for memory in memories]
        return state

    def _prepare_messages(self, state: AgentState) -> AgentState:
        memory_block = "\n".join(f"- {item}" for item in state["memories"]) or "- No stored memories yet."
        messages: list[BaseMessage] = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            SystemMessage(content=self._scheduling_context()),
            SystemMessage(content=f"Relevant user memory:\n{memory_block}"),
        ]
        history = state["conversation_history"][-self.settings.agent_max_history_messages :]
        for role, content in history:
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=state["user_message"]))
        state["messages"] = messages
        return state

    def _make_agent_node(self, tools: list[StructuredTool]):
        def agent_node(state: AgentState) -> AgentState:
            if not self.settings.groq_api_key:
                state["assistant_response"] = self._fallback_response(state)
                state["messages"] = [AIMessage(content=state["assistant_response"])]
                return state

            try:
                response = self._invoke_llm(tools, state["messages"])
            except BadRequestError as exc:
                state["assistant_response"] = (
                    "I couldn't complete the calendar action because the scheduling request was invalid. "
                    "Please try again with a clear title, start time, and end time."
                )
                if self.settings.app_debug:
                    state["assistant_response"] += f" (debug: {exc})"
                state["messages"] = [AIMessage(content=state["assistant_response"])]
                return state
            except RateLimitError as exc:
                state["assistant_response"] = self._rate_limit_message()
                if self.settings.app_debug:
                    state["assistant_response"] += f" (debug: {exc})"
                state["messages"] = [AIMessage(content=state["assistant_response"])]
                return state
            state["messages"] = [response]
            if isinstance(response, AIMessage) and response.content and not response.tool_calls:
                state["assistant_response"] = str(response.content)
            elif isinstance(response, AIMessage) and response.tool_calls:
                state["assistant_response"] = ""
            elif isinstance(response, AIMessage):
                state["assistant_response"] = str(response.content or "")
            return state

        return agent_node

    @staticmethod
    def _route_after_agent(state: AgentState) -> Literal["tools", "finish"]:
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        return "finish"

    def _extract_memory(self, state: AgentState) -> AgentState:
        if not state.get("assistant_response"):
            for message in reversed(state["messages"]):
                if isinstance(message, AIMessage) and message.content:
                    state["assistant_response"] = str(message.content)
                    break
                if isinstance(message, ToolMessage):
                    continue

        extracted = self.memory_service.extract_memories_from_message(state["user_message"])
        state["extracted_memories"] = extracted
        return state

    def _fallback_response(self, state: AgentState) -> str:
        memory_block = "\n".join(f"- {item}" for item in state["memories"]) or "- No stored memories yet."
        lowered = state["user_message"].lower()
        if any(keyword in lowered for keyword in ("inbox", "email", "mail")):
            return (
                "I can read your Gmail inbox once Google Workspace is connected and an LLM API key is configured. "
                f"Relevant memory:\n{memory_block}"
            )
        if any(keyword in lowered for keyword in ("calendar", "schedule", "meeting")):
            return (
                "I can inspect and create calendar events once Google Workspace is connected and an LLM API key is configured. "
                f"Relevant memory:\n{memory_block}"
            )
        return (
            "I received your message and loaded your stored context. "
            f"Relevant memory:\n{memory_block}"
        )

    def run(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
        user_message: str,
        conversation_history: list[tuple[str, str]] | None = None,
        workspace_context: WorkspaceToolContext | None = None,
    ) -> AgentState:
        tools = build_workspace_tools(workspace_context) if workspace_context else []
        graph = self._build_graph(tools)

        initial_state: AgentState = {
            "organization_id": str(organization_id),
            "user_id": str(user_id),
            "conversation_id": str(conversation_id),
            "user_message": user_message,
            "conversation_history": conversation_history or [],
            "memories": [],
            "messages": [],
            "assistant_response": "",
            "extracted_memories": [],
            "email_memories_persisted": workspace_context.email_memories_persisted if workspace_context else 0,
        }
        checkpoint_config = build_checkpoint_config(
            organization_id=organization_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        recursion_limit = 4 + self.settings.agent_max_tool_rounds * 2
        invoke_config = {**checkpoint_config, "recursion_limit": recursion_limit}
        final_state = graph.invoke(initial_state, config=invoke_config)
        if workspace_context:
            final_state["email_memories_persisted"] = workspace_context.email_memories_persisted
        return final_state
