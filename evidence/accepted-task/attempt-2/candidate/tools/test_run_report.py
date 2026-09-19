"""Candidate tests for the Codex phase; independent acceptance remains external."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from run_report import summarize


USAGE = {"input_tokens": 123, "cached_input_tokens": 45, "output_tokens": 6}
COMPLETED = {"type": "turn.completed", "usage": USAGE}
FAILED = {"type": "turn.failed", "error": {"message": "failed"}}
ERROR = {"type": "error", "message": "connection lost"}
FAILED_ITEM = {"type": "item.completed", "item": {"status": "failed"}}
SCRIPT = Path(__file__).with_name("run_report.py")


def report(*events):
    return summarize("codex", (json.dumps(event) for event in events))


class SummarizeTests(unittest.TestCase):
    def test_completion_preserves_exact_usage(self):
        self.assertEqual(report(COMPLETED), {
            "provider": "codex", "status": "completed", "usage": USAGE,
        })

    def test_missing_usage_and_counters_remain_null(self):
        for event in ({"type": "turn.completed"},
                      {"type": "turn.completed", "usage": None}):
            with self.subTest(event=event):
                self.assertEqual(report(event), {
                    "provider": "codex", "status": "completed", "usage": None,
                })
        self.assertEqual(report({"type": "turn.completed", "usage": {
            "input_tokens": 0, "output_tokens": 9007199254740993,
        }})["usage"], {
            "input_tokens": 0, "cached_input_tokens": None,
            "output_tokens": 9007199254740993,
        })

    def test_failure_events_without_completion(self):
        for event in (FAILED, ERROR, FAILED_ITEM):
            with self.subTest(event=event):
                self.assertEqual(report(event), {
                    "provider": "codex", "status": "failed", "usage": None,
                })

    def test_failure_is_sticky_before_or_after_completion(self):
        for failure in (ERROR, FAILED_ITEM):
            for events in ((failure, COMPLETED), (COMPLETED, failure)):
                with self.subTest(events=events):
                    self.assertEqual(report(*events), {
                        "provider": "codex", "status": "failed", "usage": USAGE,
                    })

    def test_every_pair_of_terminal_events_is_invalid(self):
        for first in (COMPLETED, FAILED):
            for second in (COMPLETED, FAILED):
                with self.subTest(first=first, second=second):
                    self.assertEqual(report(first, second)["status"], "invalid")

    def test_empty_blank_and_nonterminal_streams_are_incomplete(self):
        for lines in ([], ["", " \t\n"], [json.dumps(event) for event in (
            {"type": "thread.started"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"status": "completed"}},
        )]):
            with self.subTest(lines=lines):
                self.assertEqual(summarize("codex", iter(lines)), {
                    "provider": "codex", "status": "incomplete", "usage": None,
                })

    def test_unknown_events_are_ignored_and_blanks_allowed(self):
        lines = ["\n", '{"type":"future.event","usage":{"input_tokens":999}}',
                 json.dumps(COMPLETED), " \n", '{}', '{"type":[]}']
        self.assertEqual(summarize("codex", lines), report(COMPLETED))

    def test_bad_item_shapes_do_not_crash_or_imply_failure(self):
        for item in (None, [], "failed", {}, {"status": "in_progress"}):
            with self.subTest(item=item):
                self.assertEqual(report({"type": "item.completed", "item": item},
                                        COMPLETED)["status"], "completed")

    def test_malformed_or_nonobject_json_overrides_other_statuses(self):
        for bad in ('{', '{"type":', 'null', '[]', '42', 'true', '"text"',
                    '{} {}', '{"value":NaN}', '{"value":Infinity}'):
            for events in ([], [COMPLETED], [FAILED]):
                for bad_first in (True, False):
                    with self.subTest(bad=bad, events=events, bad_first=bad_first):
                        lines = [json.dumps(event) for event in events]
                        lines.insert(0 if bad_first else len(lines), bad)
                        self.assertEqual(summarize("codex", lines)["status"], "invalid")

    def test_summarize_is_silent_and_deterministic(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            first = report(ERROR, COMPLETED)
            second = report(ERROR, COMPLETED)
        self.assertEqual(first, second)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_unsupported_provider_and_deferred_claude_are_explicit(self):
        with self.assertRaises(ValueError):
            summarize("unknown", [])
        with self.assertRaisesRegex(NotImplementedError, "not implemented"):
            summarize("claude", [])


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=10)

    def test_status_exit_codes_single_json_and_unchanged_input(self):
        cases = ((json.dumps(COMPLETED), "completed", 0),
                 (json.dumps(FAILED), "failed", 1),
                 ("", "incomplete", 1),
                 ("{", "invalid", 1),
                 (json.dumps(COMPLETED) + "\n{} {}", "invalid", 1))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run with spaces.jsonl"
            for content, status, code in cases:
                with self.subTest(status=status, content=content):
                    path.write_text(content, encoding="utf-8")
                    result = self.invoke("--provider", "codex", str(path))
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertEqual(len(result.stdout.splitlines()), 1)
                    self.assertEqual(json.loads(result.stdout),
                                     summarize("codex", content.splitlines()))
                    self.assertEqual(json.loads(result.stdout)["status"], status)
                    self.assertEqual(path.read_text(encoding="utf-8"), content)
                    self.assertEqual(list(Path(directory).iterdir()), [path])
                    self.assertEqual(self.invoke("--provider", "codex", str(path)).stdout,
                                     result.stdout)

    def test_file_errors_exit_two_without_json(self):
        with tempfile.TemporaryDirectory() as directory:
            bad_encoding = Path(directory) / "non-utf8.jsonl"
            bad_encoding.write_bytes(b"\xff")
            for path in (Path(directory) / "missing", Path(directory), bad_encoding):
                with self.subTest(path=path):
                    result = self.invoke("--provider", "codex", str(path))
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("run_report:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_argument_errors_exit_two(self):
        for args in ((), ("log.jsonl",), ("--provider", "codex"),
                     ("--provider", "unknown", "log.jsonl")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    def test_claude_is_explicitly_unimplemented(self):
        result = self.invoke("--provider", "claude", "unused.jsonl")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("not implemented", result.stderr)


if __name__ == "__main__":
    unittest.main()
