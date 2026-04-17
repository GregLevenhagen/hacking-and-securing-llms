"""Tests for OTel trace helpers (trace_helpers.py)."""

import threading

import pytest
from opentelemetry import trace

from shared.python.telemetry.tests.conftest import InMemorySpanExporter
from shared.python.telemetry.trace_helpers import (
    add_demo_event,
    set_session_id,
    set_user_id,
    trace_demo,
)


class TestTraceDemo:
    """Tests for the @trace_demo decorator."""

    def test_creates_span_with_attributes(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """Decorator should create a span with demo.* attributes."""

        @trace_demo("Test Demo", demo_id="demo-99", category="attack")
        def my_func() -> str:
            return "result"

        result = my_func()
        assert result == "result"

        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "demo.demo-99"
        assert span.attributes["demo.name"] == "Test Demo"
        assert span.attributes["demo.id"] == "demo-99"
        assert span.attributes["demo.category"] == "attack"

    def test_auto_derives_demo_id(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """When demo_id is not provided, it should be derived from demo_name."""

        @trace_demo("Direct Prompt Injection")
        def my_func() -> None:
            pass

        my_func()
        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes["demo.id"] == "direct-prompt-injection"

    def test_preserves_function_return_value(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """Decorated function should return its original value."""

        @trace_demo("test")
        def add(a: int, b: int) -> int:
            return a + b

        assert add(3, 4) == 7

    def test_preserves_function_exceptions(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """Decorated function should propagate exceptions."""

        @trace_demo("test")
        def fail() -> None:
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            fail()

    def test_defense_category(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """Category can be 'defense' or 'azure-defense'."""

        @trace_demo("Azure Content Safety", demo_id="demo-19", category="azure-defense")
        def my_func() -> None:
            pass

        my_func()
        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes["demo.category"] == "azure-defense"

    def test_nested_decorators_create_parent_child_spans(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """Nested @trace_demo calls should create parent-child span relationships."""

        @trace_demo("Outer Demo", demo_id="demo-outer", category="attack")
        def outer() -> str:
            return inner()

        @trace_demo("Inner Demo", demo_id="demo-inner", category="defense")
        def inner() -> str:
            return "inner-result"

        result = outer()
        assert result == "inner-result"

        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 2

        # Inner span finishes first
        inner_span = spans[0]
        outer_span = spans[1]
        assert inner_span.attributes["demo.id"] == "demo-inner"
        assert outer_span.attributes["demo.id"] == "demo-outer"

        # Inner should be child of outer (same trace, different span)
        assert inner_span.context.trace_id == outer_span.context.trace_id
        assert inner_span.parent.span_id == outer_span.context.span_id

    def test_preserves_function_name(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """Decorated function should preserve its original name (functools.wraps)."""

        @trace_demo("test")
        def my_special_function() -> None:
            pass

        assert my_special_function.__name__ == "my_special_function"


class TestSetUserId:
    """Tests for set_user_id()."""

    def test_adds_user_id_to_span(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """set_user_id should add user.id attribute to active span."""
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            set_user_id("user-123")

        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes["user.id"] == "user-123"


class TestSetSessionId:
    """Tests for set_session_id()."""

    def test_adds_session_id_to_span(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """set_session_id should add session.id attribute to active span."""
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            set_session_id("session-abc")

        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes["session.id"] == "session-abc"


class TestAddDemoEvent:
    """Tests for add_demo_event()."""

    def test_creates_span_event(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """add_demo_event should create a named event on the active span."""
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            add_demo_event("attack.attempted", {"payload": "test"})

        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 1
        events = spans[0].events
        assert len(events) == 1
        assert events[0].name == "attack.attempted"
        assert events[0].attributes["payload"] == "test"

    def test_event_without_attributes(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """add_demo_event should work without attributes."""
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            add_demo_event("defense.blocked")

        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].events[0].name == "defense.blocked"


class TestConcurrentSpanCreation:
    """Tests for span creation across multiple threads."""

    def test_concurrent_spans_from_threads(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """Spans created in parallel threads should all be captured."""
        results: list[str] = []
        errors: list[Exception] = []

        def create_span(thread_id: int) -> None:
            try:
                tracer = trace.get_tracer("test-threads")
                with tracer.start_as_current_span(
                    f"thread-span-{thread_id}",
                    attributes={"thread.id": thread_id},
                ):
                    pass  # Span finishes immediately
                results.append(f"done-{thread_id}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_span, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 8

        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 8
        thread_ids = {s.attributes["thread.id"] for s in spans}
        assert thread_ids == set(range(8))

    def test_thread_spans_are_independent_traces(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """Each thread's span should be its own trace (no automatic propagation)."""
        def create_span(thread_id: int) -> None:
            tracer = trace.get_tracer("test-isolation")
            with tracer.start_as_current_span(f"isolated-{thread_id}"):
                pass

        threads = [threading.Thread(target=create_span, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        spans = mock_otel_exporter.get_finished_spans()
        trace_ids = {s.context.trace_id for s in spans}
        # Each thread creates an independent trace (no context propagation)
        assert len(trace_ids) == 4

    def test_set_user_id_in_thread(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """set_user_id should work correctly within a thread's span context."""
        def create_span_with_user(user: str) -> None:
            tracer = trace.get_tracer("test-user-thread")
            with tracer.start_as_current_span(f"user-span-{user}"):
                set_user_id(user)

        threads = [
            threading.Thread(target=create_span_with_user, args=(f"user-{i}",))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        spans = mock_otel_exporter.get_finished_spans()
        user_ids = {s.attributes["user.id"] for s in spans}
        assert user_ids == {f"user-{i}" for i in range(4)}


class TestHighVolumeSpanCreation:
    """Performance tests for span creation under load."""

    def test_many_spans_sequential(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """Creating many spans sequentially should work without errors."""
        tracer = trace.get_tracer("test-volume")
        for i in range(200):
            with tracer.start_as_current_span(
                f"volume-span-{i}",
                attributes={"index": i},
            ):
                pass

        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 200

    def test_many_events_on_single_span(
        self, mock_otel_exporter: InMemorySpanExporter
    ) -> None:
        """A single span should support many events without issue."""
        tracer = trace.get_tracer("test-events")
        with tracer.start_as_current_span("event-heavy"):
            for i in range(50):
                add_demo_event(f"event-{i}", {"index": i})

        spans = mock_otel_exporter.get_finished_spans()
        assert len(spans) == 1
        assert len(spans[0].events) == 50


class TestTracedContextHelper:
    """Tests for the traced_context fixture helper."""

    def test_traced_context_captures_spans(
        self, traced_context: tuple  # type: ignore[type-arg]
    ) -> None:
        """The traced_context fixture should provide a working tracer+exporter pair."""
        tracer, exporter = traced_context
        with tracer.start_as_current_span("helper-test"):
            set_user_id("ctx-user")

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes["user.id"] == "ctx-user"
