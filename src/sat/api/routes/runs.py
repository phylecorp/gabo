"""GET /api/runs and GET /api/runs/{run_id} — list and inspect analysis runs.

@decision DEC-API-005
@title Dual-source run listing: in-process RunManager + filesystem manifest scan
@status accepted
@rationale Active runs live in RunManager (in-process, have live status). Completed
runs from previous server sessions or the current session persist as manifest.json
files on disk. The list endpoint merges both views: in-process runs take precedence
(they have live status) and filesystem manifests fill in the rest. This keeps the
API useful across server restarts without requiring a database.

@decision DEC-API-006
@title Shared _find_output_dir helper + artifact endpoint
@status accepted
@rationale get_run_report and delete_run duplicated the same logic to locate a run's
output directory (check active RunManager, then scan filesystem manifests). Factored
into _find_output_dir() to eliminate duplication. The new artifact endpoint uses this
helper and adds path-traversal protection via Path.resolve() prefix checking.

@decision DEC-API-007
@title Download and export endpoints for artifact files and run ZIP bundles
@status accepted
@rationale Wave 3 adds two download-oriented endpoints: /artifact/download returns
a single file with Content-Disposition: attachment so browsers trigger a save dialog.
/export creates an in-memory ZIP of the entire run output directory (via io.BytesIO
+ zipfile) and returns it as application/zip. Both reuse _find_output_dir and apply
the same path-traversal guard as the existing /artifact endpoint. Media type is
inferred from file extension for the download endpoint to ensure browsers handle
JSON, Markdown, and HTML files correctly.

@decision DEC-API-008
@title Strip sat-{run_id}/ prefix from artifact paths to prevent double-nesting
@status accepted
@rationale The manifest stores artifact paths that may include the run directory name
as a leading component (e.g. sat-abc123/01-preprocessing.json). _find_output_dir()
already returns the sat-abc123/ directory, so naively joining output_dir / path
produces sat-abc123/sat-abc123/01-preprocessing.json (double-nested, 404). The fix
strips the leading directory component when it matches the output dir name before
joining — preserving path-traversal protection unchanged.

@decision DEC-API-009
@title POST /report/generate endpoint — regenerate reports from existing artifacts
@status accepted
@rationale Users may run analyses without report generation enabled, then want a
report later. This endpoint calls generate_report(output_dir, fmt=fmt) on demand.
FileNotFoundError (missing manifest) maps to 400; run-not-found maps to 404. The
endpoint is synchronous — report generation is fast (template rendering) and does
not require a background task.

@decision DEC-API-010
@title GET /runs/{run_id}/evidence endpoint — retrieve persisted EvidencePool JSON
@status accepted
@rationale Curated-evidence analysis runs persist the EvidencePool as evidence.json
in the run output directory. This endpoint reads and returns that file directly.
Returns 404 for runs without evidence (legacy runs or non-curated runs). The
endpoint reuses _find_output_dir() and returns raw bytes with application/json
media type — same pattern as get_run_artifact().
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from sat.api.auth import verify_token
from sat.api.models import ConcurrencyStatusResponse, RenameRunRequest, RunDetail, RunSummary
from sat.api.run_manager import RunManager
from sat.config import get_default_runs_dir
from sat.models.base import ArtifactManifest
from sat.report import generate_report

logger = logging.getLogger(__name__)

def _manifest_to_summary(manifest: ArtifactManifest, status: str = "completed") -> RunSummary:
    """Convert an ArtifactManifest to a RunSummary for the API response."""
    return RunSummary(
        run_id=manifest.run_id,
        question=manifest.question,
        name=manifest.name,
        started_at=manifest.started_at.isoformat(),
        completed_at=manifest.completed_at.isoformat() if manifest.completed_at else None,
        techniques_selected=manifest.techniques_selected,
        techniques_completed=manifest.techniques_completed,
        evidence_provided=manifest.evidence_provided,
        adversarial_enabled=manifest.adversarial_enabled,
        providers_used=manifest.providers_used,
        status=status,
    )


def _read_bundled_data(
    manifest: ArtifactManifest,
    output_dir: Path,
) -> tuple[dict | None, dict[str, str] | None]:
    """Read synthesis content and technique summaries from disk for bundling.

    Returns (synthesis_content, technique_summaries). Either can be None if
    the corresponding files are absent or unreadable.

    @decision DEC-API-011
    @title Bundle synthesis + technique summaries into GET /api/runs/{run_id}
    @status accepted
    @rationale The frontend previously made N+1 requests on every RunDetail load:
      one GET for synthesis JSON and one per technique for its summary. This
      caused a visible "Loading..." flash even for completed runs. Inlining the
      data into the initial RunDetail response eliminates those round-trips.
      We apply the same DEC-API-008 prefix-stripping logic used by the artifact
      endpoints to resolve manifest-relative paths. Missing files are silently
      skipped with a debug log — partial results are better than a 500 error.
    """
    synthesis_content: dict | None = None
    if manifest.synthesis_path:
        stripped = _strip_run_dir_prefix(manifest.synthesis_path, output_dir)
        # Use os.path.realpath to resolve symlinks before the prefix check (DEC-SEC-011)
        real_output = os.path.realpath(output_dir)
        synth_file = Path(os.path.realpath(output_dir / stripped))
        if str(synth_file).startswith(real_output):
            # synthesis_path may point to .md; try the .json variant too
            if not synth_file.exists() and synth_file.suffix == ".md":
                synth_file = synth_file.with_suffix(".json")
            if synth_file.exists():
                try:
                    synthesis_content = json.loads(synth_file.read_text(encoding="utf-8"))
                except Exception as exc:
                    logger.debug("Failed to read synthesis file %s: %s", synth_file, exc)

    technique_summaries: dict[str, str] | None = None
    artifacts_with_json = [a for a in manifest.artifacts if a.json_path]
    if artifacts_with_json:
        summaries: dict[str, str] = {}
        real_output = os.path.realpath(output_dir)
        for artifact in artifacts_with_json:
            if not artifact.json_path:
                continue
            stripped = _strip_run_dir_prefix(artifact.json_path, output_dir)
            art_file = Path(os.path.realpath(output_dir / stripped))
            if not str(art_file).startswith(real_output):
                continue
            if not art_file.exists():
                logger.debug(
                    "Artifact file not found for bundling (technique=%s): %s",
                    artifact.technique_id,
                    art_file,
                )
                continue
            try:
                data = json.loads(art_file.read_text(encoding="utf-8"))
                summary = data.get("summary")
                if summary and isinstance(summary, str):
                    summaries[artifact.technique_id] = summary
            except Exception as exc:
                logger.debug(
                    "Failed to read artifact for bundling (technique=%s): %s",
                    artifact.technique_id,
                    exc,
                )
        technique_summaries = summaries if summaries else None

    return synthesis_content, technique_summaries


def _manifest_to_detail(
    manifest: ArtifactManifest,
    status: str = "completed",
    output_dir: Path | None = None,
) -> RunDetail:
    """Convert an ArtifactManifest to a RunDetail for the API response.

    When *output_dir* is provided and the run is completed, synthesis_content
    and technique_summaries are populated by reading the artifact files from
    disk, eliminating N+1 frontend fetches (DEC-API-011).
    """
    synthesis_content: dict | None = None
    technique_summaries: dict[str, str] | None = None
    if output_dir is not None and status == "completed":
        synthesis_content, technique_summaries = _read_bundled_data(manifest, output_dir)

    return RunDetail(
        run_id=manifest.run_id,
        question=manifest.question,
        name=manifest.name,
        started_at=manifest.started_at.isoformat(),
        completed_at=manifest.completed_at.isoformat() if manifest.completed_at else None,
        techniques_selected=manifest.techniques_selected,
        techniques_completed=manifest.techniques_completed,
        evidence_provided=manifest.evidence_provided,
        adversarial_enabled=manifest.adversarial_enabled,
        providers_used=manifest.providers_used,
        status=status,
        artifacts=[a.model_dump(mode="json") for a in manifest.artifacts],
        synthesis_path=manifest.synthesis_path,
        evidence_path=manifest.evidence_path,
        synthesis_content=synthesis_content,
        technique_summaries=technique_summaries,
    )


def _scan_manifests(search_dir: Path) -> dict[str, ArtifactManifest]:
    """Scan search_dir for sat-*/manifest.json files and parse them.

    Returns a dict keyed by run_id. Invalid manifest files are silently skipped.
    """
    results: dict[str, ArtifactManifest] = {}
    for manifest_path in search_dir.glob("sat-*/manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = ArtifactManifest.model_validate(data)
            results[manifest.run_id] = manifest
        except Exception:
            pass
    return results


def _strip_run_dir_prefix(path: str, output_dir: Path) -> str:
    """Strip a leading sat-{run_id}/ prefix from an artifact path if present.

    The manifest may store paths that include the run directory name as the
    first component (e.g. ``sat-abc123/01-preprocessing.json``).
    ``_find_output_dir`` already returns the ``sat-abc123/`` directory, so
    joining without stripping would produce a double-nested path that does
    not exist on disk.  Only the exact directory name is stripped — deeper
    traversal is caught by the path-traversal guard downstream.
    """
    parts = Path(path).parts
    if parts and parts[0] == output_dir.name:
        # Rebuild path without the leading run-dir component
        return str(Path(*parts[1:])) if len(parts) > 1 else ""
    return path


def _find_output_dir(manager: RunManager, run_id: str, search_dir: Path) -> Path | None:
    """Locate the output directory for a run. Returns None if not found.

    Checks active in-process runs first (fast), then falls back to scanning
    sat-*/manifest.json files on the filesystem (covers completed/restarted runs).
    """
    active_run = manager.get_run(run_id)
    if active_run and active_run.output_dir:
        return Path(active_run.output_dir)
    for manifest_path in search_dir.glob("sat-*/manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if data.get("run_id") == run_id:
                return manifest_path.parent
        except Exception as exc:
            logger.debug("Skipping unreadable manifest %s: %s", manifest_path, exc)
    return None


def create_runs_router(manager: RunManager) -> APIRouter:
    """Return the runs router wired to *manager*."""
    router = APIRouter(dependencies=[Depends(verify_token)])

    @router.get("/api/runs", response_model=list[RunSummary])
    async def list_runs(
        dir: str | None = Query(default=None, description="Directory to scan for sat-* output folders (defaults to ~/.sat/runs/)"),
    ) -> list[RunSummary]:
        """List all analysis runs — active (in-process) and completed (filesystem)."""
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()

        # Scan filesystem for manifests
        fs_manifests = _scan_manifests(search_dir)

        # Build summary list: in-process runs first (they have live status),
        # then filesystem runs not already covered
        summaries: list[RunSummary] = []
        seen_ids: set[str] = set()

        for active_run in manager.list_active_runs():
            seen_ids.add(active_run.run_id)
            # Try to get manifest info if run completed
            if active_run.output_dir:
                manifest_path = Path(active_run.output_dir) / "manifest.json"
                if manifest_path.exists():
                    try:
                        data = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest = ArtifactManifest.model_validate(data)
                        summaries.append(_manifest_to_summary(manifest, status=active_run.status))
                        continue
                    except Exception:
                        pass
            # Fallback: build summary from config
            summaries.append(
                RunSummary(
                    run_id=active_run.run_id,
                    question=active_run.config.question,
                    name=active_run.name,
                    started_at="",
                    completed_at=None,
                    techniques_selected=active_run.config.techniques or [],
                    techniques_completed=active_run.techniques_completed,
                    evidence_provided=active_run.config.evidence is not None,
                    adversarial_enabled=bool(
                        active_run.config.adversarial and active_run.config.adversarial.enabled
                    ),
                    providers_used=[],
                    status=active_run.status,
                )
            )

        # Add filesystem runs not already shown
        for run_id, manifest in fs_manifests.items():
            if run_id not in seen_ids:
                summaries.append(_manifest_to_summary(manifest))

        return summaries

    @router.get("/api/runs/{run_id}", response_model=RunDetail)
    async def get_run(
        run_id: str,
        dir: str | None = Query(default=None, description="Directory to scan for sat-* output folders (defaults to ~/.sat/runs/)"),
    ) -> RunDetail:
        """Get full detail for a single run by ID."""
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()

        # Check active runs first
        active_run = manager.get_run(run_id)
        if active_run:
            if active_run.output_dir:
                active_output_dir = Path(active_run.output_dir)
                manifest_path = active_output_dir / "manifest.json"
                if manifest_path.exists():
                    try:
                        data = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest = ArtifactManifest.model_validate(data)
                        return _manifest_to_detail(
                            manifest,
                            status=active_run.status,
                            output_dir=active_output_dir,
                        )
                    except Exception as exc:
                        logger.warning("Failed to read manifest for run %s: %s", run_id, exc)
            # Return partial detail for in-flight or partially-completed run
            return RunDetail(
                run_id=active_run.run_id,
                question=active_run.config.question,
                name=active_run.name,
                started_at="",
                completed_at=None,
                techniques_selected=active_run.config.techniques or [],
                techniques_completed=[],
                evidence_provided=active_run.config.evidence is not None,
                adversarial_enabled=bool(
                    active_run.config.adversarial and active_run.config.adversarial.enabled
                ),
                providers_used=[],
                status=active_run.status,
                artifacts=[],
                synthesis_path=None,
            )

        # Fall back to filesystem scan — locate the output dir so bundled data
        # (synthesis_content, technique_summaries) can be populated (DEC-API-011).
        output_dir = _find_output_dir(manager, run_id, search_dir)
        if output_dir is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
        manifest_path = output_dir / "manifest.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = ArtifactManifest.model_validate(data)
        except Exception as exc:
            logger.warning("Failed to read manifest for run %s: %s", run_id, exc)
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found") from exc
        return _manifest_to_detail(manifest, output_dir=output_dir)

    @router.get("/api/runs/{run_id}/report")
    async def get_run_report(
        run_id: str,
        dir: str | None = Query(default=None, description="Directory to scan for sat-* output folders (defaults to ~/.sat/runs/)"),
        fmt: str = Query(default="html", description="Report format: 'html' or 'markdown'"),
    ) -> HTMLResponse:
        """Return the executive report for a run (HTML by default)."""
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()

        output_dir = _find_output_dir(manager, run_id, search_dir)
        if not output_dir:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        # Try to serve the requested format
        if fmt == "html":
            report_file = output_dir / "report.html"
            if report_file.exists():
                return HTMLResponse(content=report_file.read_text(encoding="utf-8"))
            # Fall back to markdown if html not available
            report_file = output_dir / "report.md"
            if report_file.exists():
                content = report_file.read_text(encoding="utf-8")
                return HTMLResponse(
                    content=f"<pre>{content}</pre>",
                    media_type="text/html",
                )
        else:
            report_file = output_dir / "report.md"
            if report_file.exists():
                return HTMLResponse(
                    content=report_file.read_text(encoding="utf-8"),
                    media_type="text/markdown",
                )

        raise HTTPException(
            status_code=404,
            detail=f"Report not found for run {run_id!r} (fmt={fmt!r})",
        )

    @router.post("/api/runs/{run_id}/report/generate")
    async def generate_run_report(
        run_id: str,
        dir: str | None = Query(default=None),
        fmt: str = Query(default="both"),
    ) -> dict:
        """Generate an executive report from existing run artifacts.

        Calls generate_report(output_dir, fmt=fmt) on the run's output directory.
        Returns 200 with the list of generated file paths on success.
        Returns 404 if the run is not found, 400 if report generation fails
        (e.g. manifest.json is missing or malformed).
        """
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()

        output_dir = _find_output_dir(manager, run_id, search_dir)
        if not output_dir:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        try:
            paths = generate_report(output_dir, fmt=fmt)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Report generation failed for run %s", run_id)
            raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}") from exc

        return {"paths": [str(p) for p in paths]}

    @router.get("/api/runs/{run_id}/artifact")
    async def get_run_artifact(
        run_id: str,
        path: str = Query(..., description="Path to the JSON artifact file"),
        dir: str | None = Query(default=None, description="Directory to scan for sat-* output folders (defaults to ~/.sat/runs/)"),
    ) -> Response:
        """Return a JSON artifact file for a run.

        The *path* parameter is resolved relative to the run's output directory.
        Path traversal (e.g. ../../etc/passwd) is rejected with 400.
        Returns 404 if the run or the artifact file is not found.
        """
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()

        output_dir = _find_output_dir(manager, run_id, search_dir)
        if not output_dir:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        # Strip leading sat-{run_id}/ prefix to avoid double-nesting (DEC-API-008)
        path = _strip_run_dir_prefix(path, output_dir)

        # Use os.path.realpath (not just Path.resolve) to resolve symlinks before
        # the prefix check — this prevents symlink-based traversal bypasses where
        # a symlink inside the run dir points to a file outside it (DEC-SEC-011).
        real_output = os.path.realpath(output_dir)
        artifact_path = Path(os.path.realpath(output_dir / path))
        if not str(artifact_path).startswith(real_output + os.sep) and str(artifact_path) != real_output:
            raise HTTPException(status_code=400, detail="Path traversal detected")

        if not artifact_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Artifact {path!r} not found for run {run_id!r}",
            )

        return Response(
            content=artifact_path.read_bytes(),
            media_type="application/json",
        )

    @router.get("/api/runs/{run_id}/evidence")
    async def get_run_evidence(
        run_id: str,
        dir: str | None = Query(default=None, description="Directory to scan for sat-* output folders (defaults to ~/.sat/runs/)"),
    ) -> Response:
        """Return the persisted EvidencePool JSON for a run.

        Reads evidence.json from the run's output directory. Returns 200 with the
        EvidencePool JSON on success. Returns 404 if the run is not found or if
        evidence.json does not exist (legacy runs or runs without curated evidence).
        """
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()

        output_dir = _find_output_dir(manager, run_id, search_dir)
        if not output_dir:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        evidence_file = output_dir / "evidence.json"
        if not evidence_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No evidence artifact found for run {run_id!r}",
            )

        return Response(
            content=evidence_file.read_bytes(),
            media_type="application/json",
        )

    @router.get("/api/runs/{run_id}/artifact/download")
    async def download_artifact(
        run_id: str,
        path: str = Query(..., description="Path to the artifact file"),
        dir: str | None = Query(default=None, description="Directory to scan for sat-* output folders (defaults to ~/.sat/runs/)"),
    ) -> Response:
        """Download an artifact file with Content-Disposition: attachment.

        The *path* parameter is resolved relative to the run's output directory.
        Path traversal (e.g. ../../etc/passwd) is rejected with 400.
        Returns 404 if the run or the artifact file is not found.
        Media type is inferred from the file extension.
        """
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()

        output_dir = _find_output_dir(manager, run_id, search_dir)
        if not output_dir:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        # Strip leading sat-{run_id}/ prefix to avoid double-nesting (DEC-API-008)
        path = _strip_run_dir_prefix(path, output_dir)

        # Use os.path.realpath to resolve symlinks before the prefix check —
        # prevents symlink-based traversal bypasses (DEC-SEC-011).
        real_output = os.path.realpath(output_dir)
        file_path = Path(os.path.realpath(output_dir / path))
        if not str(file_path).startswith(real_output + os.sep) and str(file_path) != real_output:
            raise HTTPException(status_code=400, detail="Path traversal not allowed")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {path}")

        # Infer media type from extension
        suffix = file_path.suffix.lower()
        if suffix == ".json":
            media_type = "application/json"
        elif suffix == ".md":
            media_type = "text/markdown"
        elif suffix == ".html":
            media_type = "text/html"
        else:
            media_type = "application/octet-stream"

        return Response(
            content=file_path.read_bytes(),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{file_path.name}"'},
        )

    @router.get("/api/runs/{run_id}/export")
    async def export_run(
        run_id: str,
        dir: str | None = Query(default=None, description="Directory to scan for sat-* output folders (defaults to ~/.sat/runs/)"),
    ) -> Response:
        """Download the entire run output directory as a ZIP archive.

        Creates a ZIP in-memory (no temp files) containing all files from the
        run's output directory. The ZIP preserves the directory structure with
        the run folder name as the top-level entry.
        """
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()

        output_dir = _find_output_dir(manager, run_id, search_dir)
        if not output_dir:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        # Build ZIP in memory — avoids writing to disk and simplifies cleanup
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(output_dir.rglob("*")):
                if file_path.is_file():
                    arcname = file_path.relative_to(output_dir.parent)
                    zf.write(file_path, arcname)
        buffer.seek(0)

        zip_name = f"{output_dir.name}.zip"
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
        )

    @router.patch("/api/runs/{run_id}", response_model=RunSummary)
    async def rename_run(
        run_id: str,
        body: RenameRunRequest,
        dir: str | None = Query(default=None, description="Directory to scan for sat-* output folders (defaults to ~/.sat/runs/)"),
    ) -> RunSummary:
        """Rename a run by updating the name field in manifest.json.

        Accepts a JSON body with a ``name`` field. Updates the on-disk
        manifest.json and the in-process ActiveRun if present. Returns
        the updated RunSummary.
        """
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()
        new_name = body.name.strip()

        # Update in-process run if present
        active_run = manager.get_run(run_id)
        if active_run:
            active_run.name = new_name

        # Update manifest.json on disk if present
        output_dir = _find_output_dir(manager, run_id, search_dir)
        if output_dir:
            manifest_path = output_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    data["name"] = new_name
                    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    manifest = ArtifactManifest.model_validate(data)
                    status = active_run.status if active_run else "completed"
                    return _manifest_to_summary(manifest, status=status)
                except Exception as exc:
                    logger.warning("Failed to update manifest for run %s: %s", run_id, exc)

        # If no manifest, build summary from active run
        if active_run:
            return RunSummary(
                run_id=active_run.run_id,
                question=active_run.config.question,
                name=active_run.name,
                started_at="",
                completed_at=None,
                techniques_selected=active_run.config.techniques or [],
                techniques_completed=[],
                evidence_provided=active_run.config.evidence is not None,
                adversarial_enabled=bool(
                    active_run.config.adversarial and active_run.config.adversarial.enabled
                ),
                providers_used=[],
                status=active_run.status,
            )

        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    @router.delete("/api/runs/{run_id}", status_code=204)
    async def delete_run(
        run_id: str,
        dir: str | None = Query(default=None, description="Directory to scan for sat-* output folders (defaults to ~/.sat/runs/)"),
    ) -> Response:
        """Delete a run and its output directory.

        Refuses to delete a run that is actively running (409 Conflict).
        Returns 204 No Content on success, 404 if the run is not found.
        """
        search_dir = Path(dir) if dir is not None else get_default_runs_dir()

        # Refuse to delete an actively running run
        active_run = manager.get_run(run_id)
        if active_run and active_run.status == "running":
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id!r} is currently running; stop it before deleting",
            )

        # Locate the output directory on the filesystem
        output_dir = _find_output_dir(manager, run_id, search_dir)
        if output_dir is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        # Remove the output directory and deregister from in-process state
        shutil.rmtree(output_dir, ignore_errors=True)
        manager.remove_run(run_id)

        return Response(status_code=204)

    @router.post("/api/runs/{run_id}/cancel")
    async def cancel_run_endpoint(run_id: str) -> dict:
        """Cancel a queued or running analysis run.

        Queued runs are removed from the queue immediately. Running runs have their
        asyncio task cancelled (the pipeline will raise CancelledError on the next
        await point). Completed or failed runs cannot be cancelled (returns 404).

        Returns JSON with {"cancelled": true} on success.
        """
        result = manager.cancel_run(run_id)
        if not result:
            # Run doesn't exist or is already completed/failed
            active_run = manager.get_run(run_id)
            if active_run is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found or already finished")
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail=f"Run {run_id!r} cannot be cancelled (status: {active_run.status})",
            )
        return {"cancelled": True, "run_id": run_id}

    @router.get("/api/concurrency", response_model=ConcurrencyStatusResponse)
    async def get_concurrency_status() -> ConcurrencyStatusResponse:
        """Return current concurrency state: running count, queued count, and cap.

        Useful for frontend to show the system status indicator and decide
        whether to warn the user that a new run will be queued.
        """
        status = manager.concurrency_status
        return ConcurrencyStatusResponse(
            running=status["running_count"],
            queued=status["queued_count"],
            max_concurrent=status["max_concurrent"],
        )

    return router
