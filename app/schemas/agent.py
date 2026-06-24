"""Agent state schemas — LangGraph state definition and task envelopes."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.schemas.email import ClassifiedEmail, EmailMessage, ThreadSummary
from app.schemas.actions import ApprovalRequest, DraftReply, FollowUp


class AgentState(TypedDict):
    """LangGraph state that flows through the orchestrator graph.

    Uses TypedDict for LangGraph compatibility. Each key represents
    a slice of the agent's working memory (short-term context).
    """
    # LLM conversation messages (with reducer for appending)
    messages: Annotated[list, add_messages]

    # Current email being processed
    current_email: Optional[dict]

    # Classification result
    classification: Optional[dict]

    # Thread summary (if summarization was requested)
    thread_summary: Optional[dict]

    # Draft reply (if drafting was triggered)
    draft_reply: Optional[dict]

    # Follow-up to schedule
    follow_up: Optional[dict]

    # Pending approval requests
    pending_approvals: list[dict]

    # Actions that have been executed
    completed_actions: list[dict]

    # Long-term memory context retrieved for this email
    memory_context: list[str]

    # Routing decision from classifier
    next_action: str

    # Error tracking
    errors: list[str]


class TaskEnvelope(BaseModel):
    """Wrapper for passing structured tasks between agents."""
    task_id: str = Field(description="Unique task identifier")
    task_type: str = Field(description="Type of task: classify, summarize, draft, schedule")
    input_data: dict = Field(description="Task-specific input data")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class ToolCallRecord(BaseModel):
    """Record of a tool invocation for observability."""
    tool_name: str
    input_data: dict
    output_data: Any
    duration_ms: float
    success: bool
    error: Optional[str] = None

