"""Tests for concurrent analysis guardrails: RunManager queue, ProviderRateLimiter, API endpoints.

@decision DEC-CONCURRENCY-TESTS-001
@title Test-first coverage for concurrency cap, queue dequeue, cancel, and rate limiting
@status accepted
@rationale Concurrency bugs are silent and intermittent. Tests exercise the full state
machine: submit → queue → start → complete → dequeue next. Cancel tests cover both
queued and running runs. Rate limiter tests verify semaphore contention. Endpoint tests
cover /api/runs/{id}/cancel and GET /api/concurrency.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from sat.api.run_manager import RunManager
from sat.config import AnalysisConfig, ProviderConfig
from sat.providers.rate_limiter import ProviderRateLimiter, RateLimitedProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(question: str = "test question") -> AnalysisConfig:
    return AnalysisConfig(
        question=question,
        output_dir=Path("."),
        provider=ProviderConfig(provider="anthropic"),
    )


def _make_manager(max_concurrent: int = 2) -> RunManager:
    return RunManager(max_concurrent=max_concurrent)


# ---------------------------------------------------------------------------
# RunManager: running_count property
# ---------------------------------------------------------------------------

class TestRunManagerRunningCount:
    def test_initial_running_count_is_zero(self):
        manager = _make_manager()
        assert manager.running_count == 0

    @pytest.mark.asyncio
    async def test_running_count_increments_on_start(self):
        manager = _make_manager(max_concurrent=5)
        run = manager.create_run(_make_config())

        done_event = asyncio.Event()

        async def slow_task():
            await done_event.wait()

        manager.start_or_queue(run, slow_task)
        await asyncio.sleep(0)
        assert manager.running_count == 1
        done_event.set()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_running_count_decrements_on_completion(self):
        manager = _make_manager(max_concurrent=5)
        run = manager.create_run(_make_config())

        done = asyncio.Event()

        async def task_fn():
            await done.wait()

        manager.start_or_queue(run, task_fn)
        await asyncio.sleep(0)
        assert manager.running_count == 1

        done.set()
        await asyncio.sleep(0.05)
        assert manager.running_count == 0


# ---------------------------------------------------------------------------
# RunManager: queuing behaviour
# ---------------------------------------------------------------------------

class TestRunManagerQueuing:
    @pytest.mark.asyncio
    async def test_third_run_is_queued_when_cap_is_2(self):
        manager = _make_manager(max_concurrent=2)
        done = asyncio.Event()

        runs = []
        for i in range(3):
            run = manager.create_run(_make_config(f"question {i}"))
            runs.append(run)

            async def task_fn(ev=done):
                await ev.wait()

            manager.start_or_queue(run, task_fn)

        await asyncio.sleep(0)

        assert runs[0].status == "running"
        assert runs[1].status == "running"
        assert runs[2].status == "queued"
        assert manager.running_count == 2
        done.set()

    @pytest.mark.asyncio
    async def test_queue_dequeues_on_completion(self):
        manager = _make_manager(max_concurrent=2)
        done_events = [asyncio.Event() for _ in range(3)]

        runs = []
        for i in range(3):
            run = manager.create_run(_make_config(f"q{i}"))
            runs.append(run)

            async def task_fn(ev=done_events[i]):
                await ev.wait()

            manager.start_or_queue(run, task_fn)

        await asyncio.sleep(0)
        assert runs[2].status == "queued"

        done_events[0].set()
        await asyncio.sleep(0.05)

        assert runs[2].status == "running"
        assert manager.running_count == 2
        done_events[1].set()
        done_events[2].set()

    @pytest.mark.asyncio
    async def test_queue_position_returns_none_for_nonqueued(self):
        manager = _make_manager(max_concurrent=5)
        run = manager.create_run(_make_config())

        async def task_fn():
            await asyncio.sleep(0)

        manager.start_or_queue(run, task_fn)
        await asyncio.sleep(0)
        assert manager.queue_position(run.run_id) is None

    @pytest.mark.asyncio
    async def test_queue_position_returns_zero_for_first_queued(self):
        manager = _make_manager(max_concurrent=2)
        done = asyncio.Event()

        runs = []
        for i in range(3):
            run = manager.create_run(_make_config(f"q{i}"))
            runs.append(run)

            async def task_fn(ev=done):
                await ev.wait()

            manager.start_or_queue(run, task_fn)

        await asyncio.sleep(0)
        assert manager.queue_position(runs[2].run_id) == 0
        done.set()

    @pytest.mark.asyncio
    async def test_queued_run_has_queued_status(self):
        manager = _make_manager(max_concurrent=1)
        done = asyncio.Event()

        run0 = manager.create_run(_make_config("q0"))
        run1 = manager.create_run(_make_config("q1"))

        async def task_fn(ev=done):
            await ev.wait()

        manager.start_or_queue(run0, task_fn)
        manager.start_or_queue(run1, task_fn)
        await asyncio.sleep(0)

        assert run1.status == "queued"
        done.set()


# ---------------------------------------------------------------------------
# RunManager: cancel
# ---------------------------------------------------------------------------

class TestRunManagerCancel:
    @pytest.mark.asyncio
    async def test_cancel_queued_run_removes_from_queue(self):
        manager = _make_manager(max_concurrent=2)
        done = asyncio.Event()

        runs = []
        for i in range(3):
            run = manager.create_run(_make_config(f"q{i}"))
            runs.append(run)

            async def task_fn(ev=done):
                await ev.wait()

            manager.start_or_queue(run, task_fn)

        await asyncio.sleep(0)
        assert runs[2].status == "queued"

        result = manager.cancel_run(runs[2].run_id)
        assert result is True
        assert runs[2].status == "cancelled"
        assert manager.queue_position(runs[2].run_id) is None
        done.set()

    @pytest.mark.asyncio
    async def test_cancel_running_run_cancels_task(self):
        manager = _make_manager(max_concurrent=2)
        done = asyncio.Event()

        run = manager.create_run(_make_config())

        async def task_fn():
            await done.wait()

        manager.start_or_queue(run, task_fn)
        await asyncio.sleep(0)
        assert run.status == "running"

        result = manager.cancel_run(run.run_id)
        assert result is True
        assert run.task is not None
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_run_returns_false(self):
        manager = _make_manager()
        result = manager.cancel_run("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_completed_run_returns_false(self):
        manager = _make_manager()
        run = manager.create_run(_make_config())

        async def task_fn():
            pass

        manager.start_or_queue(run, task_fn)
        await asyncio.sleep(0.05)

        result = manager.cancel_run(run.run_id)
        assert result is False


# ---------------------------------------------------------------------------
# RunManager: concurrency_status property
# ---------------------------------------------------------------------------

class TestRunManagerConcurrencyStatus:
    @pytest.mark.asyncio
    async def test_concurrency_status_reflects_state(self):
        manager = _make_manager(max_concurrent=2)
        done = asyncio.Event()

        runs = []
        for i in range(3):
            run = manager.create_run(_make_config(f"q{i}"))
            runs.append(run)

            async def task_fn(ev=done):
                await ev.wait()

            manager.start_or_queue(run, task_fn)

        await asyncio.sleep(0)

        status = manager.concurrency_status
        assert status["running_count"] == 2
        assert status["queued_count"] == 1
        assert status["max_concurrent"] == 2
        done.set()


# ---------------------------------------------------------------------------
# ProviderRateLimiter
# ---------------------------------------------------------------------------

class TestProviderRateLimiter:
    @pytest.mark.asyncio
    async def test_rate_limiter_allows_up_to_max_concurrent(self):
        limiter = ProviderRateLimiter(max_concurrent_per_provider=3)
        results = []

        async def work(i: int):
            async with limiter.acquire("anthropic"):
                results.append(f"start-{i}")
                await asyncio.sleep(0.01)
                results.append(f"end-{i}")

        await asyncio.gather(*[work(i) for i in range(3)])
        assert len(results) == 6

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_at_cap(self):
        limiter = ProviderRateLimiter(max_concurrent_per_provider=1)
        in_flight = []

        async def work(i: int):
            async with limiter.acquire("anthropic"):
                in_flight.append(i)
                assert len(in_flight) <= 1, f"Exceeded cap: {in_flight}"
                await asyncio.sleep(0.02)
                in_flight.remove(i)

        await asyncio.gather(*[work(i) for i in range(3)])

    @pytest.mark.asyncio
    async def test_rate_limiter_creates_separate_semaphores_per_provider(self):
        limiter = ProviderRateLimiter(max_concurrent_per_provider=1)
        acquired = []

        async def acquire_both():
            async with limiter.acquire("anthropic"):
                acquired.append("anthropic")
                async with limiter.acquire("openai"):
                    acquired.append("openai")

        await acquire_both()
        assert "anthropic" in acquired
        assert "openai" in acquired

    @pytest.mark.asyncio
    async def test_rate_limiter_releases_on_exception(self):
        limiter = ProviderRateLimiter(max_concurrent_per_provider=1)

        async def failing_work():
            async with limiter.acquire("anthropic"):
                raise ValueError("boom")

        with pytest.raises(ValueError):
            await failing_work()

        acquired = False
        async with limiter.acquire("anthropic"):
            acquired = True
        assert acquired


# ---------------------------------------------------------------------------
# RateLimitedProvider
# ---------------------------------------------------------------------------

class TestRateLimitedProvider:
    @pytest.mark.asyncio
    async def test_rate_limited_provider_calls_inner_generate(self):
        from sat.providers.base import LLMMessage, LLMResult

        inner = AsyncMock()
        inner.generate = AsyncMock(return_value=LLMResult(text="hello"))

        limiter = ProviderRateLimiter(max_concurrent_per_provider=4)
        provider = RateLimitedProvider(inner, limiter, "anthropic")

        result = await provider.generate("sys", [LLMMessage(role="user", content="hi")])
        assert result.text == "hello"
        inner.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limited_provider_calls_inner_generate_structured(self):
        from pydantic import BaseModel
        from sat.providers.base import LLMMessage

        class MySchema(BaseModel):
            value: str

        inner = AsyncMock()
        inner.generate_structured = AsyncMock(return_value=MySchema(value="test"))

        limiter = ProviderRateLimiter(max_concurrent_per_provider=4)
        provider = RateLimitedProvider(inner, limiter, "anthropic")

        result = await provider.generate_structured(
            "sys",
            [LLMMessage(role="user", content="hi")],
            MySchema,
        )
        assert result.value == "test"

    @pytest.mark.asyncio
    async def test_rate_limited_provider_enforces_semaphore(self):
        from sat.providers.base import LLMMessage, LLMResult

        in_flight_count = 0
        max_observed = 0

        async def slow_generate(*args, **kwargs):
            nonlocal in_flight_count, max_observed
            in_flight_count += 1
            max_observed = max(max_observed, in_flight_count)
            await asyncio.sleep(0.02)
            in_flight_count -= 1
            return LLMResult(text="ok")

        inner = AsyncMock()
        inner.generate = slow_generate

        limiter = ProviderRateLimiter(max_concurrent_per_provider=2)
        provider = RateLimitedProvider(inner, limiter, "anthropic")

        await asyncio.gather(
            *[
                provider.generate("sys", [LLMMessage(role="user", content="hi")])
                for _ in range(5)
            ]
        )
        assert max_observed <= 2


# ---------------------------------------------------------------------------
# API endpoints: cancel and concurrency
# ---------------------------------------------------------------------------

class TestConcurrencyEndpoints:
    """Test the /api/runs/{run_id}/cancel and GET /api/concurrency endpoints."""

    def _make_app(self, manager: RunManager):
        from sat.api.routes.runs import create_runs_router
        from sat.api.routes.analysis import create_analysis_router

        app = FastAPI()
        app.include_router(create_runs_router(manager))
        app.include_router(create_analysis_router(manager, port=8742))
        return app

    @pytest.mark.asyncio
    async def test_cancel_queued_run_returns_200(self):
        manager = _make_manager(max_concurrent=1)
        done = asyncio.Event()

        run0 = manager.create_run(_make_config("q0"))
        run1 = manager.create_run(_make_config("q1"))

        async def blocker(ev=done):
            await ev.wait()

        manager.start_or_queue(run0, blocker)
        manager.start_or_queue(run1, blocker)
        await asyncio.sleep(0)

        assert run1.status == "queued"

        app = self._make_app(manager)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/runs/{run1.run_id}/cancel")
            assert resp.status_code == 200
            data = resp.json()
            assert data["cancelled"] is True

        done.set()

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_run_returns_404(self):
        manager = _make_manager()
        app = self._make_app(manager)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/runs/nonexistent/cancel")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_concurrency_status_endpoint(self):
        manager = _make_manager(max_concurrent=3)
        done = asyncio.Event()

        for i in range(4):
            run = manager.create_run(_make_config(f"q{i}"))

            async def task_fn(ev=done):
                await ev.wait()

            manager.start_or_queue(run, task_fn)

        await asyncio.sleep(0)

        app = self._make_app(manager)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/concurrency")
            assert resp.status_code == 200
            data = resp.json()
            assert data["running"] == 3
            assert data["queued"] == 1
            assert data["max_concurrent"] == 3

        done.set()


# ---------------------------------------------------------------------------
# RunManager: completed/failed run eviction (single source of truth)
# ---------------------------------------------------------------------------

class TestRunEvictionOnCompletion:
    """Verify that completed and failed runs are evicted from _runs.

    After eviction, the filesystem manifest is the sole source of truth,
    preventing duplicate entries in the runs list API.
    """

    @pytest.mark.asyncio
    async def test_completed_run_removed_from_runs_dict(self):
        """A run that completes successfully must be evicted from _runs."""
        manager = _make_manager()
        run = manager.create_run(_make_config())
        run_id = run.run_id

        async def task_fn():
            pass

        manager.start_or_queue(run, task_fn)
        await asyncio.sleep(0.05)

        assert run.status == "completed"
        # After eviction, get_run returns None
        assert manager.get_run(run_id) is None
        assert run_id not in [r.run_id for r in manager.list_active_runs()]

    @pytest.mark.asyncio
    async def test_failed_run_removed_from_runs_dict(self):
        """A run that raises an exception must be evicted from _runs."""
        manager = _make_manager()
        run = manager.create_run(_make_config())
        run_id = run.run_id

        async def failing_task():
            raise RuntimeError("boom")

        manager.start_or_queue(run, failing_task)
        await asyncio.sleep(0.05)

        assert run.status == "failed"
        assert manager.get_run(run_id) is None
        assert run_id not in [r.run_id for r in manager.list_active_runs()]

    @pytest.mark.asyncio
    async def test_cancelled_run_stays_in_runs_dict(self):
        """A cancelled run must NOT be evicted — it has no manifest to fall back to."""
        manager = _make_manager()
        done = asyncio.Event()
        run = manager.create_run(_make_config())
        run_id = run.run_id

        async def slow_task():
            await done.wait()

        manager.start_or_queue(run, slow_task)
        await asyncio.sleep(0)
        assert run.status == "running"

        manager.cancel_run(run_id)
        await asyncio.sleep(0.05)

        # Cancelled run stays in registry (no manifest to fall back to)
        assert manager.get_run(run_id) is not None
        assert manager.get_run(run_id).status == "cancelled"

    @pytest.mark.asyncio
    async def test_queue_dequeue_still_works_after_eviction(self):
        """Evicting the first run from _runs must not break queue promotion."""
        manager = _make_manager(max_concurrent=1)
        done_events = [asyncio.Event() for _ in range(2)]

        run0 = manager.create_run(_make_config("q0"))
        run1 = manager.create_run(_make_config("q1"))
        run1_id = run1.run_id

        async def task0(ev=done_events[0]):
            await ev.wait()

        async def task1(ev=done_events[1]):
            await ev.wait()

        manager.start_or_queue(run0, task0)
        manager.start_or_queue(run1, task1)

        await asyncio.sleep(0)
        assert run1.status == "queued"

        # Complete run0 — triggers eviction AND queue promotion
        done_events[0].set()
        await asyncio.sleep(0.05)

        # run0 is evicted; run1 must be promoted to running
        assert run0.status == "completed"
        assert manager.get_run(run0.run_id) is None
        assert run1.status == "running"
        assert manager.get_run(run1_id) is not None  # run1 still active

        done_events[1].set()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_list_runs_no_duplicate_when_manifest_on_disk(self, tmp_path):
        """GET /api/runs must return exactly one entry when a run has completed
        (manifest on disk) and has been evicted from the active registry."""
        import json
        from datetime import datetime, UTC
        from httpx import AsyncClient, ASGITransport
        from fastapi import FastAPI
        from sat.api.routes.runs import create_runs_router

        manager = _make_manager()
        run = manager.create_run(_make_config("no duplicates please"))
        run_id = run.run_id

        # Write a manifest on disk (simulating what the pipeline does)
        sat_dir = tmp_path / f"sat-{run_id}"
        sat_dir.mkdir()
        manifest = {
            "run_id": run_id,
            "question": "no duplicates please",
            "name": None,
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "techniques_selected": [],
            "techniques_completed": [],
            "evidence_provided": False,
            "adversarial_enabled": False,
            "providers_used": [],
            "artifacts": [],
            "synthesis_path": None,
        }
        (sat_dir / "manifest.json").write_text(json.dumps(manifest))

        # Simulate the fix: evict the completed run from the active registry
        run.status = "completed"
        run.output_dir = str(sat_dir)
        del manager._runs[run_id]

        # list_runs should return exactly one entry (from filesystem only)
        app = FastAPI()
        app.include_router(create_runs_router(manager))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/runs?dir={tmp_path}")
            assert resp.status_code == 200
            runs = resp.json()
            assert len(runs) == 1, f"Expected 1 run, got {len(runs)}: {runs}"
            assert runs[0]["run_id"] == run_id


# ---------------------------------------------------------------------------
# Docling thread offloading
# ---------------------------------------------------------------------------

class TestDoclingThreadOffloading:
    @pytest.mark.asyncio
    async def test_parse_document_is_async(self):
        import inspect
        from sat.ingestion.parser import parse_document
        assert inspect.iscoroutinefunction(parse_document)

    @pytest.mark.asyncio
    async def test_parse_document_text_file(self, tmp_path: Path):
        from sat.ingestion.parser import parse_document
        txt = tmp_path / "test.txt"
        txt.write_text("Hello world\n", encoding="utf-8")
        result = await parse_document(txt)
        assert "Hello world" in result.markdown
        assert result.source_type == "text"

    @pytest.mark.asyncio
    async def test_docling_convert_called_in_executor(self, tmp_path: Path, monkeypatch):
        import sat.ingestion.parser as parser_module
        from sat.ingestion.parser import parse_document

        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = "# Parsed Doc"
        mock_result.document.tables = []
        mock_result.document.pages = [1, 2]

        mock_converter = MagicMock()
        mock_converter.convert.return_value = mock_result

        monkeypatch.setattr(parser_module, "DOCLING_AVAILABLE", True)
        monkeypatch.setattr(parser_module, "_converter", mock_converter)

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        result = await parse_document(pdf)

        mock_converter.convert.assert_called_once_with(str(pdf))
        assert result.markdown == "# Parsed Doc"
