import tempfile
from pathlib import Path
from typer.testing import CliRunner
from sat.cli import app
from unittest.mock import patch

runner = CliRunner()

def test_evidence_file_single():
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_file = Path(tmpdir) / "evidence.txt"
        evidence_file.write_text("This is evidence from a single file.")

        # We use a mock to avoid actually running the analysis pipeline
        with patch("sat.pipeline.run_analysis") as mock_run:
            result = runner.invoke(app, ["analyze", "What is the capital of France?", "--evidence-file", str(evidence_file)])
            assert result.exit_code == 0

            # Check if the evidence was correctly read
            args, kwargs = mock_run.call_args
            config = args[0]
            assert config.evidence == "This is evidence from a single file."

def test_evidence_folder():
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir) / "evidence_folder"
        evidence_dir.mkdir()
        (evidence_dir / "file1.txt").write_text("Evidence 1")
        (evidence_dir / "file2.txt").write_text("Evidence 2")
        (evidence_dir / "subdir").mkdir()
        (evidence_dir / "subdir" / "file3.txt").write_text("Evidence 3")

        with patch("sat.pipeline.run_analysis") as mock_run:
            result = runner.invoke(app, ["analyze", "Question?", "--evidence-file", str(evidence_dir)])

            assert result.exit_code == 0
            args, kwargs = mock_run.call_args
            config = args[0]
            # We expect all files to be aggregated
            assert "Evidence 1" in config.evidence
            assert "Evidence 2" in config.evidence
            assert "Evidence 3" in config.evidence

            # Check headers
            assert "--- Source: file1.txt ---" in config.evidence
            assert "--- Source: subdir/file3.txt ---" in config.evidence

def test_evidence_folder_hidden_ignored():
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir) / "evidence_folder"
        evidence_dir.mkdir()
        (evidence_dir / "visible.txt").write_text("Visible content")
        (evidence_dir / ".hidden.txt").write_text("Hidden content")

        with patch("sat.pipeline.run_analysis") as mock_run:
            result = runner.invoke(app, ["analyze", "Question?", "--evidence-file", str(evidence_dir)])

            assert result.exit_code == 0
            args, kwargs = mock_run.call_args
            config = args[0]

            assert "Visible content" in config.evidence
            assert "Hidden content" not in config.evidence
