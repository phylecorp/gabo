"""Test CLI argument parsing and basic commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from sat.cli import app
from sat.config import get_default_runs_dir

runner = CliRunner()


class TestCLI:
    """CLI should parse arguments correctly and show help."""

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Gabo" in result.output

    def test_analyze_help(self):
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "question" in result.output.lower()

    def test_analyze_help_mentions_default_runs_dir(self):
        """--output-dir help text must mention ~/.sat/runs/ as the default."""
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "~/.sat/runs/" in result.output, (
            f"Expected '~/.sat/runs/' in analyze --help, got:\n{result.output}"
        )

    def test_list_techniques(self):
        result = runner.invoke(app, ["list-techniques"])
        assert result.exit_code == 0
        assert "assumptions" in result.output
        assert "ach" in result.output
        assert "diagnostic" in result.output

    def test_list_techniques_by_category(self):
        result = runner.invoke(app, ["list-techniques", "--category", "contrarian"])
        assert result.exit_code == 0
        assert "devils_advocacy" in result.output

    def test_analyze_with_invalid_technique(self):
        result = runner.invoke(app, ["analyze", "test question", "--techniques", "fake_technique"])
        assert result.exit_code == 1
        assert "Unknown technique" in result.output


class TestCLIOutputDirDefault:
    """CLI output_dir should default to ~/.sat/runs/, not '.'."""

    def test_analysis_config_output_dir_defaults_to_none(self):
        """AnalysisConfig.output_dir must default to None (not Path('.'))."""
        from sat.config import AnalysisConfig

        config = AnalysisConfig(question="Is this a test?")
        assert config.output_dir is None, (
            f"AnalysisConfig.output_dir should default to None, got {config.output_dir!r}"
        )

    def test_get_default_runs_dir_not_cwd(self, monkeypatch, tmp_path):
        """get_default_runs_dir() must not return Path('.') (the CWD)."""
        monkeypatch.setenv("SAT_RUNS_DIR", str(tmp_path / "runs"))
        result = get_default_runs_dir()
        assert result != Path("."), (
            "get_default_runs_dir() must not return Path('.') — "
            "that writes to CWD which is unpredictable in packaged Electron apps"
        )
