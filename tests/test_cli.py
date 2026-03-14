"""Test CLI argument parsing and basic commands."""

from __future__ import annotations

from typer.testing import CliRunner

from sat.cli import app

runner = CliRunner()


class TestCLI:
    """CLI should parse arguments correctly and show help."""

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Structured Analytic Techniques" in result.output

    def test_analyze_help(self):
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "question" in result.output.lower()

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
