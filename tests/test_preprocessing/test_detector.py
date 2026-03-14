"""Tests for evidence format detection.

@decision DEC-TEST-PREPROC-001: Comprehensive heuristic detection tests.
@title Format detection test coverage
@status accepted
@rationale Each EvidenceFormat variant needs positive tests plus edge cases
(empty input, ambiguous delimiters, priority ordering). Tests use raw strings
to avoid any preprocessing — the detector must handle real-world messiness.
"""

from sat.models.preprocessing import EvidenceFormat
from sat.preprocessing.detector import detect_format


class TestDetectFormat:
    def test_plain_text(self):
        assert detect_format("This is a simple paragraph of text.") == EvidenceFormat.PLAIN_TEXT

    def test_empty_string(self):
        assert detect_format("") == EvidenceFormat.PLAIN_TEXT

    def test_whitespace_only(self):
        assert detect_format("   \n\n  ") == EvidenceFormat.PLAIN_TEXT

    def test_json_object(self):
        assert detect_format('{"key": "value", "num": 42}') == EvidenceFormat.JSON

    def test_json_array(self):
        assert detect_format('[{"a": 1}, {"a": 2}]') == EvidenceFormat.JSON

    def test_json_with_whitespace(self):
        assert detect_format('  \n  {"key": "value"}  \n') == EvidenceFormat.JSON

    def test_jsonl(self):
        text = '{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}\n{"id": 3, "name": "Charlie"}'
        assert detect_format(text) == EvidenceFormat.JSONL

    def test_csv(self):
        text = "name,age,city\nAlice,30,NYC\nBob,25,LA\nCharlie,35,Chicago"
        assert detect_format(text) == EvidenceFormat.CSV

    def test_tsv(self):
        text = "name\tage\tcity\nAlice\t30\tNYC\nBob\t25\tLA\nCharlie\t35\tChicago"
        assert detect_format(text) == EvidenceFormat.CSV

    def test_csv_single_line(self):
        """Single-line CSV should fall through to plain text."""
        assert detect_format("name,age,city") == EvidenceFormat.PLAIN_TEXT

    def test_log_file_iso(self):
        text = """2024-01-15T10:30:00Z INFO Starting application
2024-01-15T10:30:01Z DEBUG Loading config
2024-01-15T10:30:02Z WARN Connection slow
2024-01-15T10:30:03Z ERROR Failed to connect
2024-01-15T10:30:04Z INFO Retrying..."""
        assert detect_format(text) == EvidenceFormat.LOG_FILE

    def test_log_file_syslog(self):
        text = """Jan 15 10:30:00 server1 sshd[1234]: Connection from 192.168.1.1
Jan 15 10:30:01 server1 sshd[1234]: Accepted password for user
Jan 15 10:30:02 server1 sshd[1234]: Session opened
Jan 15 10:30:03 server1 sshd[1234]: Session closed"""
        assert detect_format(text) == EvidenceFormat.LOG_FILE

    def test_multi_file(self):
        text = """--- Source: report.txt ---
This is report content.

--- Source: notes/meeting.md ---
Meeting notes here."""
        assert detect_format(text) == EvidenceFormat.MULTI_FILE

    def test_multi_file_takes_priority(self):
        """Multi-file markers should win even if content looks like CSV."""
        text = """--- Source: data.csv ---
name,age,city
Alice,30,NYC
Bob,25,LA

--- Source: other.csv ---
x,y,z
1,2,3"""
        assert detect_format(text) == EvidenceFormat.MULTI_FILE

    def test_json_not_jsonl_with_two_lines(self):
        """Two JSON lines should be JSON, not JSONL (need >= 3)."""
        text = '{"a": 1}\n{"b": 2}'
        assert detect_format(text) == EvidenceFormat.JSON

    def test_inconsistent_csv_delimiters(self):
        """Lines with different delimiter counts should not be CSV."""
        text = "name,age\nAlice\nBob,25,extra"
        assert detect_format(text) == EvidenceFormat.PLAIN_TEXT
