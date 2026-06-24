"""Approval API routes — human-in-the-loop approval flow.

Allows users to review, approve, reject, or edit pending actions
before they are executed (sending emails, scheduling follow-ups, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.observability.metrics import metrics
from app.schemas.actions import ActionType, ApprovalStatus
from app.tools import calendar_api, mail_api

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/approvals", tags=["approvals"])

# ── In-memory approval store ────────────────────────────────────────────────

_approvals: dict[str, dict] = {}


def register_approvals(approvals: list[dict]) -> None:
    """Register pending approvals from a processing run."""
    for approval in approvals:
        _approvals[approval["approval_id"]] = approval
        logger.info("approval_registered", approval_id=approval["approval_id"])


class ApprovalDecision(BaseModel):
    """User's decision on a pending approval."""
    decision: ApprovalStatus = Field(description="approve, reject, or edited")
    edited_payload: Optional[dict] = Field(
        default=None, description="Modified payload if editing"
    )
    feedback: str = Field(default="", description="Optional feedback")


class ApprovalDetail(BaseModel):
    """Detailed view of an approval request."""
    approval_id: str
    action_type: str
    status: str
    description: str
    payload: dict
    email_id: str = ""
    thread_id: str = ""
    created_at: str = ""


@router.get("/")
async def list_approvals(status: ApprovalStatus | None = None):
    """List all approval requests, optionally filtered by status."""
    approvals = list(_approvals.values())
    if status:
        approvals = [a for a in approvals if a.get("status") == status.value]
    return {
        "total": len(approvals),
        "approvals": approvals,
    }


@router.get("/{approval_id}")
async def get_approval(approval_id: str):
    """Get details of a specific approval request."""
    approval = _approvals.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")
    return approval


@router.post("/{approval_id}/decide")
async def decide_approval(approval_id: str, decision: ApprovalDecision):
    """Submit a decision (approve/reject/edit) for a pending approval.

    If approved, the action is executed immediately.
    If edited, the modified payload is used for execution.
    If rejected, the action is cancelled.
    """
    approval = _approvals.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

    if approval.get("status") != ApprovalStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Approval {approval_id} is already {approval.get('status')}",
        )

    # Update status
    approval["status"] = decision.decision.value
    approval["feedback"] = decision.feedback
    approval["decided_at"] = datetime.now(timezone.utc).isoformat()

    result = {"approval_id": approval_id, "decision": decision.decision.value}

    if decision.decision == ApprovalStatus.APPROVED:
        execution_result = _execute_action(approval, approval["payload"])
        result["execution"] = execution_result
        metrics.increment("drafts_approved")
        logger.info("approval_approved", approval_id=approval_id)

    elif decision.decision == ApprovalStatus.EDITED:
        merged_payload = dict(approval["payload"])
        if decision.edited_payload:
            merged_payload.update(decision.edited_payload)
        approval["payload"] = merged_payload
        execution_result = _execute_action(approval, merged_payload)
        result["execution"] = execution_result
        metrics.increment("drafts_edited")
        logger.info("approval_edited", approval_id=approval_id)

    elif decision.decision == ApprovalStatus.REJECTED:
        result["execution"] = {"status": "cancelled"}
        metrics.increment("drafts_rejected")
        logger.info("approval_rejected", approval_id=approval_id, feedback=decision.feedback)

    return result


def _execute_action(approval: dict, payload: dict) -> dict:
    """Execute the approved action."""
    action_type = approval.get("action_type")

    if action_type == ActionType.SEND_REPLY.value:
        sent = mail_api.send_email(
            to_addresses=payload.get("to_addresses", []),
            subject=payload.get("subject", ""),
            body=payload.get("body", ""),
            cc_addresses=payload.get("cc_addresses"),
            thread_id=payload.get("thread_id"),
        )
        return {"status": "sent", "email_id": sent.id}

    elif action_type == ActionType.SCHEDULE_FOLLOWUP.value:
        event = calendar_api.create_event(
            title=f"Follow-up: {payload.get('description', '')}",
            scheduled_at=datetime.fromisoformat(payload["scheduled_at"]),
            description=payload.get("description", ""),
            event_type="follow_up",
            related_email_id=payload.get("email_id", ""),
            related_thread_id=payload.get("thread_id", ""),
        )
        metrics.increment("follow_ups_scheduled")
        return {"status": "scheduled", "event_id": event.event_id}

    elif action_type == ActionType.APPLY_LABEL.value:
        mail_api.apply_label(payload.get("email_id", ""), payload.get("label", "inbox"))
        return {"status": "label_applied"}

    else:
        return {"status": "unknown_action", "action_type": action_type}

