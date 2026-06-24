"""Tests for tools — mail_api, calendar_api, and knowledge_store."""

from datetime import datetime, timezone

from app.tools.mail_api import (
    apply_label,
    fetch_inbox,
    get_email,
    get_sent_emails,
    get_thread,
    mark_as_read,
    send_email,
)
from app.tools.calendar_api import (
    create_event,
    delete_event,
    get_event,
    list_events,
    reset_calendar,
)
from app.tools.knowledge_store import (
    add_documents,
    delete_document,
    get_all_documents,
    query,
    reset_store,
    CONTACTS,
    PREFERENCES,
    ORG_FACTS,
)
from app.schemas.email import EmailLabel


# ── Mail API Tests ───────────────────────────────────────────────────────────


class TestMailAPI:
    """Tests for the mock mail API adapter."""

    def test_fetch_inbox_returns_emails(self):
        """Inbox should be seeded with sample emails."""
        emails = fetch_inbox()
        assert len(emails) > 0
        assert "email-003" not in {email.id for email in emails}
        assert all(EmailLabel.INBOX in email.labels for email in emails)

    def test_sent_thread_context_not_listed_as_inbox(self):
        """Sent thread-history messages should not appear in the default inbox."""
        sent_context = get_email("email-003")
        assert sent_context is not None
        assert sent_context.from_address == "user@company.com"
        assert EmailLabel.SENT in sent_context.labels
        assert EmailLabel.INBOX not in sent_context.labels

        inbox = fetch_inbox()
        assert all(email.id != "email-003" for email in inbox)

        sent_label_messages = fetch_inbox(label=EmailLabel.SENT)
        assert any(email.id == "email-003" for email in sent_label_messages)

    def test_fetch_inbox_unread_filter(self):
        """Should filter to unread emails only."""
        unread = fetch_inbox(unread_only=True)
        for email in unread:
            assert email.is_read is False

    def test_fetch_inbox_label_filter(self):
        """Should filter by label."""
        emails = fetch_inbox(label=EmailLabel.INBOX)
        for email in emails:
            assert EmailLabel.INBOX in email.labels

    def test_get_email_existing(self):
        """Should return an email by ID."""
        email = get_email("email-001")
        assert email is not None
        assert email.id == "email-001"
        assert email.from_address == "sarah.chen@techcorp.com"

    def test_get_email_nonexistent(self):
        """Should return None for non-existent email."""
        assert get_email("nonexistent") is None

    def test_get_thread(self):
        """Should return all messages in a thread, sorted chronologically."""
        thread = get_thread("thread-002")
        assert len(thread) >= 2
        assert {email.id for email in thread} >= {"email-002", "email-003"}
        # Verify chronological order
        for i in range(1, len(thread)):
            assert thread[i].timestamp >= thread[i - 1].timestamp

    def test_mark_as_read(self):
        """Should mark an email as read."""
        email = get_email("email-001")
        assert email.is_read is False
        result = mark_as_read("email-001")
        assert result is True
        assert get_email("email-001").is_read is True

    def test_mark_as_read_nonexistent(self):
        """Should return False for non-existent email."""
        assert mark_as_read("nonexistent") is False

    def test_apply_label(self):
        """Should apply a label to an email."""
        result = apply_label("email-001", EmailLabel.ACTION_REQUIRED)
        assert result is True
        email = get_email("email-001")
        assert EmailLabel.ACTION_REQUIRED in email.labels

    def test_apply_label_idempotent(self):
        """Applying the same label twice should not duplicate."""
        apply_label("email-001", EmailLabel.MEETING)
        apply_label("email-001", EmailLabel.MEETING)
        email = get_email("email-001")
        assert email.labels.count(EmailLabel.MEETING) == 1

    def test_send_email(self):
        """Should create and store a sent email."""
        sent = send_email(
            to_addresses=["recipient@test.com"],
            subject="Test Subject",
            body="Test body content",
        )
        assert sent.id.startswith("sent-")
        assert sent.to_addresses == ["recipient@test.com"]
        assert sent.subject == "Test Subject"
        assert sent.from_address == "user@company.com"

        # Should appear in sent list
        all_sent = get_sent_emails()
        assert any(e.id == sent.id for e in all_sent)

    def test_send_email_with_thread_id(self):
        """Should preserve thread_id on sent emails."""
        sent = send_email(
            to_addresses=["test@test.com"],
            subject="Re: Thread test",
            body="Reply body",
            thread_id="thread-001",
        )
        assert sent.thread_id == "thread-001"


# ── Calendar API Tests ───────────────────────────────────────────────────────


class TestCalendarAPI:
    """Tests for the mock calendar API."""

    def setup_method(self):
        """Reset calendar before each test."""
        reset_calendar()

    def test_create_event(self):
        """Should create and store an event."""
        event = create_event(
            title="Test Meeting",
            scheduled_at=datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc),
            description="A test meeting",
            event_type="meeting",
        )
        assert event.event_id.startswith("evt-")
        assert event.title == "Test Meeting"
        assert event.event_type == "meeting"

    def test_get_event(self):
        """Should retrieve an event by ID."""
        event = create_event(
            title="Retrieve Test",
            scheduled_at=datetime(2026, 6, 25, 14, 0, tzinfo=timezone.utc),
        )
        retrieved = get_event(event.event_id)
        assert retrieved is not None
        assert retrieved.title == "Retrieve Test"

    def test_get_event_nonexistent(self):
        """Should return None for non-existent event."""
        assert get_event("fake-id") is None

    def test_list_events_all(self):
        """Should list all events."""
        create_event(title="Event 1", scheduled_at=datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc))
        create_event(title="Event 2", scheduled_at=datetime(2026, 6, 26, 10, 0, tzinfo=timezone.utc))
        events = list_events()
        assert len(events) == 2

    def test_list_events_filtered_by_type(self):
        """Should filter events by type."""
        create_event(title="Meeting", scheduled_at=datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc), event_type="meeting")
        create_event(title="Follow-up", scheduled_at=datetime(2026, 6, 25, 14, 0, tzinfo=timezone.utc), event_type="follow_up")
        meetings = list_events(event_type="meeting")
        assert len(meetings) == 1
        assert meetings[0].title == "Meeting"

    def test_delete_event(self):
        """Should delete an event."""
        event = create_event(title="To Delete", scheduled_at=datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc))
        assert delete_event(event.event_id) is True
        assert get_event(event.event_id) is None

    def test_delete_event_nonexistent(self):
        """Should return False for non-existent event."""
        assert delete_event("fake-id") is False


# ── Knowledge Store Tests ────────────────────────────────────────────────────


class TestKnowledgeStore:
    """Tests for the hybrid knowledge store."""

    def setup_method(self):
        """Reset store before each test."""
        reset_store()

    def test_add_and_query_documents(self):
        """Should add documents and find them via keyword search."""
        add_documents(
            collection_name=CONTACTS,
            documents=["John Smith, Engineering Manager at Acme Corp"],
            ids=["contact-john"],
            metadatas=[{"email": "john@acme.com"}],
        )
        results = query(CONTACTS, "John Engineering")
        assert len(results) >= 1
        assert "John Smith" in results[0]["document"]

    def test_query_empty_collection(self):
        """Query on a collection with no documents added in this test returns empty from keyword search."""
        # Use a collection name that hasn't been populated by other tests
        from app.tools.knowledge_store import _keyword_search
        results = _keyword_search("empty_test_collection", "anything", 5)
        assert results == []

    def test_add_multiple_documents(self):
        """Should store multiple documents and retrieve them."""
        add_documents(
            collection_name=PREFERENCES,
            documents=[
                "User prefers formal tone in replies",
                "User prefers morning meetings before 11 AM",
                "User prefers short concise replies",
            ],
            ids=["pref-tone", "pref-meetings", "pref-length"],
        )
        results = query(PREFERENCES, "tone reply formal")
        assert len(results) >= 1

    def test_get_all_documents(self):
        """Should return all documents in a collection."""
        add_documents(
            collection_name=ORG_FACTS,
            documents=["Fact 1: Company uses microservices", "Fact 2: Team has 12 engineers"],
            ids=["fact-1", "fact-2"],
        )
        all_docs = get_all_documents(ORG_FACTS)
        assert len(all_docs) == 2

    def test_delete_document(self):
        """Should delete a document by ID."""
        add_documents(
            collection_name=CONTACTS,
            documents=["Test contact"],
            ids=["contact-delete-test"],
        )
        assert delete_document(CONTACTS, "contact-delete-test") is True
        all_docs = get_all_documents(CONTACTS)
        assert not any(d["id"] == "contact-delete-test" for d in all_docs)

    def test_delete_nonexistent_document(self):
        """Should return False for non-existent document."""
        assert delete_document(CONTACTS, "fake-id") is False

    def test_upsert_overwrites(self):
        """Adding a document with the same ID should overwrite."""
        add_documents(CONTACTS, documents=["Original"], ids=["upsert-test"])
        add_documents(CONTACTS, documents=["Updated"], ids=["upsert-test"])
        all_docs = get_all_documents(CONTACTS)
        matching = [d for d in all_docs if d["id"] == "upsert-test"]
        assert len(matching) == 1
        assert matching[0]["document"] == "Updated"

    def test_keyword_search_scoring(self):
        """Documents with more keyword matches should rank higher."""
        add_documents(
            collection_name=ORG_FACTS,
            documents=[
                "The ML team handles machine learning model deployment",
                "HR handles employee onboarding and policies",
                "The ML team uses Python and machine learning frameworks for deployment pipelines",
            ],
            ids=["fact-ml", "fact-hr", "fact-ml-detail"],
        )
        results = query(ORG_FACTS, "ML machine learning deployment")
        assert len(results) >= 2
        # The more detailed ML doc should rank at top (more keyword matches)
        assert "ML" in results[0]["document"] or "machine learning" in results[0]["document"]

