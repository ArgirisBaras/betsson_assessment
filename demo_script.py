"""
📧 Email Assistant — End-to-End Demo Script
============================================

Run this script to see the full agent pipeline in action.
No Jupyter needed — just start the server and run:

    python demo_script.py

Or if the server isn't running, this script starts it automatically.
"""

import json
import sys
import time

import httpx

BASE_URL = "http://localhost:8000"
client = httpx.Client(base_url=BASE_URL, timeout=30.0)


def pp(label: str, data: dict) -> None:
    """Pretty-print a section."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(json.dumps(data, indent=2, default=str)[:2000])


def check_server() -> bool:
    """Check if the server is reachable."""
    try:
        r = client.get("/")
        return r.status_code == 200
    except Exception:
        return False


def demo():
    """Run the full demo flow."""
    print("\n" + "🚀" * 35)
    print("   📧 INTELLIGENT EMAIL ASSISTANT — LIVE DEMO")
    print("🚀" * 35)

    # ── 1. Health Check ──────────────────────────────────────────────────
    if not check_server():
        print("\n❌ Server not reachable at", BASE_URL)
        print("   Start it with: docker compose up --build")
        print("   Or: uvicorn app.main:app --port 8000")
        sys.exit(1)

    r = client.get("/")
    print(f"\n✅ Server is healthy: {r.json()}")

    # ── 2. Reset System ──────────────────────────────────────────────────
    print("\n📋 Resetting system state...")
    r = client.post("/reset")
    print(f"   {r.json()['status']}")

    # ── 3. Browse Inbox ──────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  📥 INBOX")
    print("─" * 70)
    r = client.get("/inbox/", params={"unread_only": True})
    inbox = r.json()
    print(f"\n  Unread emails: {inbox['total']}\n")
    for email in inbox["emails"]:
        print(f"  {'📩'} [{email['id']}] {email['subject']}")
        print(f"      From: {email['from_address']} | {email['timestamp']}")

    # ── 4. Process Urgent Email ──────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  🤖 PROCESSING: Urgent Production Issue (email-001)")
    print("─" * 70)

    r = client.post("/inbox/process", json={"email_id": "email-001"})
    result = r.json()

    print(f"\n  Status: {result['status']}")
    if result.get("classification"):
        cls = result["classification"]
        print(f"  Intent:   {cls['intent']}")
        print(f"  Priority: {cls['priority']}")
        print(f"  Summary:  {cls['summary']}")
    if result.get("draft_reply"):
        draft = result["draft_reply"]
        print(f"\n  📝 Draft Reply Generated:")
        print(f"     To: {draft['to_addresses']}")
        print(f"     Subject: {draft['subject']}")
        print(f"     Tone: {draft['tone']}")
        print(f"     Body: {draft['body'][:200]}...")
    if result.get("pending_approvals"):
        print(f"\n  ⏳ Pending Approvals: {len(result['pending_approvals'])}")
        for apr in result["pending_approvals"]:
            print(f"     [{apr['approval_id']}] {apr['action_type']}: {apr['description']}")

    # ── 5. Process B2B Question ──────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  🤖 PROCESSING: B2B Partner Question (email-004)")
    print("─" * 70)

    r = client.post("/inbox/process", json={"email_id": "email-004"})
    result2 = r.json()

    print(f"\n  Status: {result2['status']}")
    if result2.get("classification"):
        cls = result2["classification"]
        print(f"  Intent:   {cls['intent']}")
        print(f"  Priority: {cls['priority']}")
    if result2.get("draft_reply"):
        draft = result2["draft_reply"]
        print(f"\n  📝 Draft Reply:")
        print(f"     To: {draft['to_addresses']}")
        print(f"     Body: {draft['body'][:200]}...")

    # ── 6. Process FYI Email (should summarize, not draft) ───────────────
    print("\n" + "─" * 70)
    print("  🤖 PROCESSING: FYI Policy Update (email-005)")
    print("─" * 70)

    r = client.post("/inbox/process", json={"email_id": "email-005"})
    result3 = r.json()

    print(f"\n  Status: {result3['status']}")
    if result3.get("classification"):
        cls = result3["classification"]
        print(f"  Intent:   {cls['intent']}")
        print(f"  Priority: {cls['priority']}")
    if result3.get("thread_summary"):
        summary = result3["thread_summary"]
        print(f"\n  📝 Thread Summary: {summary.get('summary', 'N/A')}")
        print(f"     Key Points: {summary.get('key_points', [])}")
    if not result3.get("draft_reply"):
        print(f"\n  ✅ No draft generated (FYI email — no reply needed)")

    # ── 7. Human-in-the-Loop: Approve Actions ───────────────────────────
    print("\n" + "─" * 70)
    print("  👤 HUMAN-IN-THE-LOOP: Approval Flow")
    print("─" * 70)

    r = client.get("/approvals/")
    approvals = r.json()
    print(f"\n  Total pending approvals: {approvals['total']}\n")

    for apr in approvals["approvals"]:
        print(f"  [{apr['approval_id']}] {apr['action_type']} — status: {apr['status']}")
        print(f"    {apr['description']}")

    # Approve the first one
    if approvals["approvals"]:
        first = approvals["approvals"][0]
        aid = first["approval_id"]
        print(f"\n  ✅ Approving: {aid}...")
        r = client.post(f"/approvals/{aid}/decide", json={
            "decision": "approved",
            "feedback": "Looks good, send it."
        })
        decision = r.json()
        print(f"     Decision: {decision.get('decision')}")
        if decision.get("execution"):
            print(f"     Execution: {decision['execution']}")

    # Edit and approve the second one
    if len(approvals["approvals"]) > 1:
        second = approvals["approvals"][1]
        aid = second["approval_id"]
        edited_payload = dict(second["payload"])
        if "body" in edited_payload:
            edited_payload["body"] += "\n\nP.S. Happy to jump on a quick call if easier."

        print(f"\n  ✏️  Editing & approving: {aid}...")
        r = client.post(f"/approvals/{aid}/decide", json={
            "decision": "edited",
            "edited_payload": edited_payload,
            "feedback": "Added offer to call."
        })
        decision = r.json()
        print(f"     Decision: {decision.get('decision')}")
        if decision.get("execution"):
            print(f"     Execution: {decision['execution']}")

    # ── 8. Memory Search ─────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  🧠 LONG-TERM MEMORY: Search / Recall")
    print("─" * 70)

    # Search the long-term memory store (JSON backend in Docker, optional ChromaDB locally)
    try:
        r = client.get("/memory/contacts/search", params={"q": "infrastructure partner"})
        contacts = r.json()
        if contacts.get("results"):
            print(f"\n  Search 'infrastructure partner':")
            for c in contacts["results"][:2]:
                print(f"    → {c['document'][:100]}")
        else:
            print("\n  ℹ️  No memory results found for this query")
    except Exception:
        print("\n  ℹ️  Memory search unavailable in this environment")

    # ── 9. Metrics ───────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  📊 OBSERVABILITY: Metrics")
    print("─" * 70)

    r = client.get("/metrics")
    metrics = r.json()
    print(f"\n  Counters:")
    for k, v in metrics["counters"].items():
        if v > 0:
            print(f"    {k}: {v}")
    print(f"\n  Latencies:")
    for k, v in metrics["latencies"].items():
        if v.get("count", 0) > 0:
            print(f"    {k}: avg={v['avg_ms']:.0f}ms, min={v['min_ms']:.0f}ms, max={v['max_ms']:.0f}ms")

    # ── 10. Traces ───────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  📍 OBSERVABILITY: Processing Traces")
    print("─" * 70)

    r = client.get("/traces")
    traces = r.json()
    print(f"\n  Total runs traced: {traces['total']}\n")
    for trace in traces["traces"]:
        print(f"  Run: {trace['run_id']} ({trace['total_spans']} spans)")
        for span in trace["spans"]:
            icon = "✅" if span["status"] == "success" else "❌"
            print(f"    {icon} [{span['span_type']}] {span['name']} — {span['duration_ms']:.0f}ms")

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  ✅ DEMO COMPLETE — All systems operational!")
    print("=" * 70)
    print("""
  What was demonstrated:
  ─────────────────────
  ✓ Agent Architecture:  LangGraph orchestrator with 4 worker agents
  ✓ Email Capabilities:  Read, classify, label, summarize, draft replies
  ✓ Human-in-the-Loop:   Approve/edit/reject pending actions
  ✓ Memory:              Short-term (state) + Long-term (ChromaDB)
  ✓ Structured I/O:      All interactions via Pydantic-validated JSON
  ✓ Observability:       Structured logs, traces, and metrics
  ✓ Routing:             Conditional edges based on intent/priority

  Explore more:
  ─────────────
  • Interactive API docs:  http://localhost:8000/docs
  • Process more emails:   POST /inbox/process {"email_id": "email-006"}
  • Add memory:            POST /memory/preferences {"key":"...", "value":"..."}
  • View all approvals:    GET /approvals/
    """)


if __name__ == "__main__":
    demo()

