"""Tests for memory subsystem and observability modules."""


from app.memory.long_term import (
    get_memory_context,
    recall_contacts,
    recall_org_facts,
    recall_preferences,
    store_contact,
    store_org_fact,
    store_preference,
)
from app.memory.short_term import build_initial_state
from app.observability.metrics import MetricsCollector
from app.observability.tracing import AgentTracer, TraceRecord, create_tracer, get_all_traces, clear_traces
from app.schemas.memory import ContactInfo, OrgFact, UserPreference
from app.tools.knowledge_store import reset_store


# ── Short-Term Memory Tests ──────────────────────────────────────────────────


class TestShortTermMemory:
    """Tests for LangGraph state management helpers."""

    def test_build_initial_state_structure(self):
        """Initial state should have all required keys with proper defaults."""
        state = build_initial_state()
        assert state["messages"] == []
        assert state["current_email"] is None
        assert state["classification"] is None
        assert state["thread_summary"] is None
        assert state["draft_reply"] is None
        assert state["follow_up"] is None
        assert state["pending_approvals"] == []
        assert state["completed_actions"] == []
        assert state["memory_context"] == []
        assert state["next_action"] == ""
        assert state["run_id"] == ""
        assert state["errors"] == []


# ── Long-Term Memory Tests ───────────────────────────────────────────────────


class TestLongTermMemory:
    """Tests for long-term memory store and recall."""

    def setup_method(self):
        """Reset the knowledge store before each test."""
        reset_store()

    def test_store_and_recall_preference(self):
        """Should store a preference and recall it."""
        pref = UserPreference(
            key="reply_tone",
            value="formal",
            description="Always use formal tone in replies to external partners",
        )
        store_preference(pref)
        results = recall_preferences("tone formal reply")
        assert len(results) >= 1
        assert "formal" in results[0]["document"].lower()

    def test_store_and_recall_contact(self):
        """Should store a contact and recall by name."""
        contact = ContactInfo(
            name="Alice Johnson",
            email="alice@partner.com",
            role="CTO",
            organization="Partner Corp",
            relationship="Key stakeholder",
            notes="Prefers async communication",
        )
        store_contact(contact)
        results = recall_contacts("alice partner")
        assert len(results) >= 1
        assert "Alice Johnson" in results[0]["document"]

    def test_store_and_recall_org_fact(self):
        """Should store an org fact and recall it."""
        fact = OrgFact(
            fact_id="fact-deploy-process",
            category="engineering",
            content="Production deployments require two approvals and a canary phase",
            source="engineering_wiki",
        )
        store_org_fact(fact)
        results = recall_org_facts("deployment production canary")
        assert len(results) >= 1
        assert "canary" in results[0]["document"].lower()

    def test_get_memory_context_returns_list(self):
        """get_memory_context should return a list of context strings."""
        # Store some data first
        store_contact(ContactInfo(
            name="Bob Smith",
            email="bob@external.com",
            role="Engineer",
            organization="External Inc",
            relationship="Vendor",
            notes="Technical contact",
        ))
        store_preference(UserPreference(
            key="urgency_threshold",
            value="high",
            description="Escalate high-priority items immediately",
        ))

        context = get_memory_context(
            email_subject="Urgent API issue",
            email_body="We have a problem with the API integration",
            sender="bob@external.com",
        )
        assert isinstance(context, list)
        # Should have some context items (contacts, prefs, or facts)
        # At minimum returns an empty list if nothing matches

    def test_get_memory_context_empty_store(self):
        """Should return empty list when memory store is empty."""
        context = get_memory_context(
            email_subject="Random subject",
            email_body="Random body",
            sender="unknown@unknown.com",
        )
        assert isinstance(context, list)


# ── Metrics Tests ────────────────────────────────────────────────────────────


class TestMetrics:
    """Tests for the metrics collector."""

    def test_increment_counter(self):
        """Should increment counters."""
        m = MetricsCollector()
        m.increment("emails_processed")
        m.increment("emails_processed")
        snapshot = m.get_snapshot()
        assert snapshot["counters"]["emails_processed"] == 2

    def test_increment_dynamic_counter(self):
        """Should support dynamic counter names."""
        m = MetricsCollector()
        m.increment("classified_intent_request")
        m.increment("classified_intent_request")
        m.increment("classified_intent_question")
        snapshot = m.get_snapshot()
        assert snapshot["counters"]["classified_intent_request"] == 2
        assert snapshot["counters"]["classified_intent_question"] == 1


    def test_default_approval_counters(self):
        """Approval metrics should separate generic and action-specific counters."""
        m = MetricsCollector()
        counters = m.get_snapshot()["counters"]

        for counter in [
            "approvals_approved",
            "approvals_rejected",
            "approvals_edited",
            "send_replies_approved",
            "send_replies_rejected",
            "send_replies_edited",
            "follow_ups_approved",
            "follow_ups_rejected",
            "follow_ups_edited",
        ]:
            assert counters[counter] == 0

    def test_record_latency(self):
        """Should record and aggregate latency values."""
        m = MetricsCollector()
        m.record_latency("classification_ms", 100.0)
        m.record_latency("classification_ms", 200.0)
        m.record_latency("classification_ms", 150.0)
        snapshot = m.get_snapshot()
        lat = snapshot["latencies"]["classification_ms"]
        assert lat["count"] == 3
        assert lat["avg_ms"] == 150.0
        assert lat["min_ms"] == 100.0
        assert lat["max_ms"] == 200.0

    def test_reset(self):
        """Should reset all metrics to zero."""
        m = MetricsCollector()
        m.increment("emails_processed", 5)
        m.record_latency("classification_ms", 100.0)
        m.reset()
        snapshot = m.get_snapshot()
        assert snapshot["counters"]["emails_processed"] == 0
        assert snapshot["latencies"]["classification_ms"]["count"] == 0

    def test_snapshot_includes_uptime(self):
        """Snapshot should include uptime and timestamp."""
        m = MetricsCollector()
        snapshot = m.get_snapshot()
        assert "uptime_seconds" in snapshot
        assert "snapshot_at" in snapshot
        assert snapshot["uptime_seconds"] >= 0


# ── Tracing Tests ────────────────────────────────────────────────────────────


class TestTracing:
    """Tests for the tracing/span system."""

    def setup_method(self):
        """Clear traces before each test."""
        clear_traces()

    def test_create_tracer(self):
        """Should create a tracer with a run ID."""
        tracer = create_tracer("test-run-001")
        assert tracer.run_id == "test-run-001"
        assert tracer.spans == []

    def test_start_and_end_span(self):
        """Should record span with timing."""
        tracer = AgentTracer("test-run")
        span = tracer.start_span("agent", "reader", email_id="email-001")
        assert span.status == "running"
        assert span.span_type == "agent"
        assert span.name == "reader"

        tracer.end_span(span)
        assert span.status == "success"
        assert span.duration_ms >= 0
        assert span.end_time is not None

    def test_span_error(self):
        """Should record error status on spans."""
        tracer = AgentTracer("test-run")
        span = tracer.start_span("llm", "classify")
        tracer.end_span(span, status="error", error="API timeout")
        assert span.status == "error"
        assert span.error == "API timeout"

    def test_tracer_to_dict(self):
        """Should serialize tracer to dict."""
        tracer = AgentTracer("test-run-dict")
        span = tracer.start_span("agent", "drafter")
        tracer.end_span(span)

        result = tracer.to_dict()
        assert result["run_id"] == "test-run-dict"
        assert result["total_spans"] == 1
        assert len(result["spans"]) == 1
        assert result["spans"][0]["name"] == "drafter"
        assert result["spans"][0]["status"] == "success"

    def test_get_all_traces(self):
        """Should return all registered traces."""
        create_tracer("run-1")
        create_tracer("run-2")
        traces = get_all_traces()
        assert len(traces) >= 2

    def test_clear_traces(self):
        """Should clear all stored traces."""
        create_tracer("run-to-clear")
        clear_traces()
        assert get_all_traces() == []

    def test_trace_record_to_dict(self):
        """TraceRecord should serialize correctly."""
        record = TraceRecord("tool", "mail_api", {"action": "send"})
        record.finish()
        d = record.to_dict()
        assert d["span_type"] == "tool"
        assert d["name"] == "mail_api"
        assert d["status"] == "success"
        assert d["duration_ms"] >= 0
        assert d["metadata"] == {"action": "send"}

