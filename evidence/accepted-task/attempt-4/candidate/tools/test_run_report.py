"""Candidate tests for both provider phases; independent acceptance remains external."""

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

CLAUDE_USAGE = {
    "input_tokens": 4, "cache_creation_input_tokens": 1500,
    "cache_read_input_tokens": 22000, "output_tokens": 310,
    "server_tool_use": {"web_search_requests": 0},
}
CLAUDE_COST = 0.0523
CLAUDE_SUCCESS = {
    "type": "result", "subtype": "success", "is_error": False,
    "duration_ms": 1200, "num_turns": 3, "result": "done",
    "usage": CLAUDE_USAGE, "total_cost_usd": CLAUDE_COST,
}
# Real log shape: the subtype claims success but is_error is true.
CLAUDE_SUCCESS_IS_ERROR = dict(CLAUDE_SUCCESS, is_error=True)
CLAUDE_ERROR_SUBTYPE = dict(CLAUDE_SUCCESS, subtype="error_during_execution",
                            is_error=True)
CLAUDE_INIT = {"type": "system", "subtype": "init", "session_id": "abc"}
CLAUDE_ASSISTANT = {"type": "assistant", "message": {"content": [
    {"type": "text", "text": "hello"}]}}


def report(*events):
    return summarize("codex", (json.dumps(event) for event in events))


def claude(*events):
    return summarize("claude", (json.dumps(event) for event in events))


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
            third = claude(CLAUDE_INIT, CLAUDE_SUCCESS)
            fourth = claude(CLAUDE_INIT, CLAUDE_SUCCESS)
        self.assertEqual(first, second)
        self.assertEqual(third, fourth)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_unsupported_provider_is_explicit(self):
        for provider in ("unknown", "", None, "Codex", "CLAUDE"):
            with self.subTest(provider=provider):
                with self.assertRaises(ValueError):
                    summarize(provider, [])

    def test_codex_reports_do_not_grow_a_cost_field(self):
        self.assertEqual(set(report(COMPLETED)), {"provider", "status", "usage"})


class ClaudeSummarizeTests(unittest.TestCase):
    def test_success_requires_explicit_false_is_error_and_keeps_usage_and_cost(self):
        self.assertEqual(claude(CLAUDE_INIT, CLAUDE_ASSISTANT, CLAUDE_SUCCESS), {
            "provider": "claude", "status": "completed",
            "usage": CLAUDE_USAGE, "total_cost_usd": CLAUDE_COST,
        })

    def test_success_subtype_with_is_error_true_is_failed(self):
        self.assertEqual(claude(CLAUDE_INIT, CLAUDE_SUCCESS_IS_ERROR), {
            "provider": "claude", "status": "failed",
            "usage": CLAUDE_USAGE, "total_cost_usd": CLAUDE_COST,
        })

    def test_error_subtypes_are_failed_regardless_of_is_error(self):
        for subtype in ("error_during_execution", "error_max_turns",
                        "error_max_budget_usd", "error"):
            for is_error in (True, False, None, "false"):
                event = dict(CLAUDE_SUCCESS, subtype=subtype)
                if is_error is None:
                    del event["is_error"]
                else:
                    event["is_error"] = is_error
                with self.subTest(subtype=subtype, is_error=is_error):
                    self.assertEqual(claude(event)["status"], "failed")

    def test_success_without_explicit_boolean_false_is_never_completed(self):
        missing = dict(CLAUDE_SUCCESS)
        del missing["is_error"]
        for event in (missing, dict(CLAUDE_SUCCESS, is_error=None),
                      dict(CLAUDE_SUCCESS, is_error="false"),
                      dict(CLAUDE_SUCCESS, is_error=0),
                      dict(CLAUDE_SUCCESS, is_error=[])):
            with self.subTest(event=event):
                result = claude(event)
                self.assertNotEqual(result["status"], "completed")
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["usage"], CLAUDE_USAGE)
                self.assertEqual(result["total_cost_usd"], CLAUDE_COST)

    def test_result_without_string_subtype_is_not_completed(self):
        no_subtype = dict(CLAUDE_SUCCESS)
        del no_subtype["subtype"]
        for event in (no_subtype, dict(CLAUDE_SUCCESS, subtype=None),
                      dict(CLAUDE_SUCCESS, subtype=["success"])):
            with self.subTest(event=event):
                self.assertEqual(claude(event)["status"], "invalid")
        # A true is_error still wins over an unusable subtype.
        self.assertEqual(claude(dict(no_subtype, is_error=True))["status"], "failed")

    def test_missing_usage_and_cost_remain_null_never_inferred(self):
        bare = {"type": "result", "subtype": "success", "is_error": False}
        self.assertEqual(claude(bare), {
            "provider": "claude", "status": "completed",
            "usage": None, "total_cost_usd": None,
        })
        for usage in (None, "lots", 7, ["input_tokens"]):
            with self.subTest(usage=usage):
                self.assertIsNone(claude(dict(bare, usage=usage))["usage"])
        self.assertEqual(claude(dict(bare, usage={}))["usage"], {})
        self.assertEqual(claude(dict(bare, total_cost_usd=0))["total_cost_usd"], 0)
        self.assertEqual(claude(dict(bare, total_cost_usd=None))["total_cost_usd"],
                         None)

    def test_usage_dict_is_a_copy_of_the_reported_object(self):
        reported = {"input_tokens": 1, "nested": {"a": [1, 2]}, "extra": "kept"}
        result = claude(dict(CLAUDE_SUCCESS, usage=reported))
        self.assertEqual(result["usage"], reported)
        self.assertIsNot(result["usage"], reported)

    def test_missing_result_is_incomplete(self):
        for lines in ([], ["", "\n"], [json.dumps(CLAUDE_INIT)],
                      [json.dumps(CLAUDE_INIT), json.dumps(CLAUDE_ASSISTANT)],
                      [json.dumps({"type": "user", "message": {}})]):
            with self.subTest(lines=lines):
                self.assertEqual(summarize("claude", iter(lines)), {
                    "provider": "claude", "status": "incomplete",
                    "usage": None, "total_cost_usd": None,
                })

    def test_duplicate_result_is_invalid_and_keeps_first_evidence(self):
        second = dict(CLAUDE_SUCCESS, usage={"output_tokens": 1}, total_cost_usd=9.9)
        for events in ((CLAUDE_SUCCESS, CLAUDE_SUCCESS),
                       (CLAUDE_SUCCESS, second),
                       (CLAUDE_SUCCESS, CLAUDE_ERROR_SUBTYPE),
                       (CLAUDE_ERROR_SUBTYPE, CLAUDE_SUCCESS),
                       (CLAUDE_SUCCESS_IS_ERROR, CLAUDE_SUCCESS)):
            with self.subTest(events=events):
                result = claude(*events)
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["usage"], events[0]["usage"])
                self.assertEqual(result["total_cost_usd"], events[0]["total_cost_usd"])

    def test_non_result_events_never_terminate_or_fail(self):
        lines = [json.dumps(event) for event in (
            {"type": "system", "subtype": "error", "is_error": True},
            {"type": "assistant", "subtype": "success", "is_error": False},
            {"type": "error", "message": "ignored for claude"},
            {"type": "future", "usage": {"input_tokens": 999}, "total_cost_usd": 5},
            {}, {"type": None}, {"subtype": "success", "is_error": False},
        )]
        self.assertEqual(summarize("claude", lines)["status"], "incomplete")
        lines.append(json.dumps(CLAUDE_SUCCESS))
        self.assertEqual(summarize("claude", lines), claude(CLAUDE_SUCCESS))

    def test_malformed_or_nonobject_json_overrides_other_statuses(self):
        for bad in ('{', 'null', '[]', '"result"', '{"type":"result"} {}',
                    '{"type":"result","total_cost_usd":NaN}'):
            for events in ([], [CLAUDE_SUCCESS], [CLAUDE_ERROR_SUBTYPE]):
                for bad_first in (True, False):
                    with self.subTest(bad=bad, events=events, bad_first=bad_first):
                        lines = [json.dumps(event) for event in events]
                        lines.insert(0 if bad_first else len(lines), bad)
                        self.assertEqual(summarize("claude", lines)["status"], "invalid")


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=10)

    def check_cases(self, provider, cases):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run with spaces.jsonl"
            for content, status, code in cases:
                with self.subTest(provider=provider, status=status, content=content):
                    path.write_text(content, encoding="utf-8")
                    result = self.invoke("--provider", provider, str(path))
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertEqual(len(result.stdout.splitlines()), 1)
                    self.assertEqual(json.loads(result.stdout),
                                     summarize(provider, content.splitlines()))
                    self.assertEqual(json.loads(result.stdout)["status"], status)
                    self.assertEqual(path.read_text(encoding="utf-8"), content)
                    self.assertEqual(list(Path(directory).iterdir()), [path])
                    self.assertEqual(
                        self.invoke("--provider", provider, str(path)).stdout,
                        result.stdout)

    def test_codex_status_exit_codes_single_json_and_unchanged_input(self):
        self.check_cases("codex", (
            (json.dumps(COMPLETED), "completed", 0),
            (json.dumps(FAILED), "failed", 1),
            ("", "incomplete", 1),
            ("{", "invalid", 1),
            (json.dumps(COMPLETED) + "\n{} {}", "invalid", 1),
        ))

    def test_claude_status_exit_codes_single_json_and_unchanged_input(self):
        self.check_cases("claude", (
            ("\n".join(json.dumps(e) for e in (CLAUDE_INIT, CLAUDE_ASSISTANT,
                                                CLAUDE_SUCCESS)) + "\n",
             "completed", 0),
            (json.dumps(CLAUDE_SUCCESS_IS_ERROR), "failed", 1),
            (json.dumps(CLAUDE_ERROR_SUBTYPE), "failed", 1),
            (json.dumps(CLAUDE_INIT), "incomplete", 1),
            ("", "incomplete", 1),
            (json.dumps(CLAUDE_SUCCESS) + "\n" + json.dumps(CLAUDE_SUCCESS),
             "invalid", 1),
            ("{", "invalid", 1),
        ))

    def test_claude_cli_output_carries_top_level_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claude.jsonl"
            path.write_text(json.dumps(CLAUDE_SUCCESS) + "\n", encoding="utf-8")
            result = self.invoke("--provider", "claude", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "provider": "claude", "status": "completed",
            "usage": CLAUDE_USAGE, "total_cost_usd": CLAUDE_COST,
        })

    def test_numeric_overflow_is_invalid_without_traceback(self):
        for provider, event in (("codex", COMPLETED), ("claude", CLAUDE_SUCCESS)):
            for number in ("1e400", "-1e400"):
                for field in ("usage", "total_cost_usd", "unknown"):
                    bad = dict(event)
                    bad[field] = {"input_tokens": "OVERFLOW"} if field == "usage" else "OVERFLOW"
                    line = json.dumps(bad).replace('"OVERFLOW"', number)
                    with self.subTest(provider=provider, number=number, field=field):
                        self.check_cases(provider, (
                            (line, "invalid", 1),
                            (line + "\n" + json.dumps(event), "invalid", 1),
                            (json.dumps(event) + "\n" + line, "invalid", 1),
                        ))

    def test_excessive_nesting_is_invalid_without_traceback(self):
        line = '{"nested":' + '[' * 20000 + '0' + ']' * 20000 + '}'
        for provider, event in (("codex", COMPLETED), ("claude", CLAUDE_SUCCESS)):
            self.check_cases(provider, (
                (line, "invalid", 1),
                (line + "\n" + json.dumps(event), "invalid", 1),
                (json.dumps(event) + "\n" + line, "invalid", 1),
            ))

    def test_file_errors_exit_two_without_json(self):
        with tempfile.TemporaryDirectory() as directory:
            bad_encoding = Path(directory) / "non-utf8.jsonl"
            bad_encoding.write_bytes(b"\xff")
            late_bad_encoding = Path(directory) / "late-non-utf8.jsonl"
            # Decoding can fail after a terminal has already been consumed.
            late_bad_encoding.write_bytes(
                (json.dumps(COMPLETED) + "\n" + json.dumps(CLAUDE_SUCCESS) + "\n").encode()
                + b"\n" * 10000 + b"\xff")
            for provider in ("codex", "claude"):
                for path in (Path(directory) / "missing", Path(directory),
                             bad_encoding, late_bad_encoding):
                    with self.subTest(provider=provider, path=path):
                        result = self.invoke("--provider", provider, str(path))
                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(result.stdout, "")
                        self.assertIn("run_report:", result.stderr)
                        self.assertNotIn("Traceback", result.stderr)
                        repeated = self.invoke("--provider", provider, str(path))
                        self.assertEqual((repeated.returncode, repeated.stdout, repeated.stderr),
                                         (result.returncode, result.stdout, result.stderr))

    def test_argument_errors_exit_two(self):
        for args in ((), ("log.jsonl",), ("--provider", "codex"),
                     ("--provider", "claude"),
                     ("--provider", "unknown", "log.jsonl")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                repeated = self.invoke(*args)
                self.assertEqual((repeated.returncode, repeated.stdout, repeated.stderr),
                                 (result.returncode, result.stdout, result.stderr))


if __name__ == "__main__":
    unittest.main()
