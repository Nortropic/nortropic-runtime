"""The Runtime entry start check (UNDERHALL-INGANGAR-20260924), tried against real Git repositories in a temporary
directory. Each test builds its own small origin and a clone of it; no real repository, no real Git configuration and no
network is used.
"""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import check_entry


class EntryCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        (base / "gitconfig").write_text("")
        environment = mock.patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": str(base / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"})
        environment.start()
        self.addCleanup(environment.stop)
        self.seed, self.origin, self.entry = base / "seed", base / "origin.git", base / "entry"
        self.git(base, "init", "--quiet", "-b", "main", str(self.seed))
        self.commit(self.seed, "docs/plan.md", "# Plan\n\nNo branch named.\n")
        self.git(base, "clone", "--quiet", "--bare", str(self.seed), str(self.origin))
        self.git(self.seed, "remote", "add", "origin", str(self.origin))
        self.git(base, "clone", "--quiet", str(self.origin), str(self.entry))

    def tearDown(self):
        self.temp.cleanup()

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, repo, name, text):
        path = Path(repo) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.git(repo, "add", name)
        self.git(repo, "commit", "--quiet", "-m", "test: " + name)

    def publish_plan(self, text):
        self.commit(self.seed, "docs/plan.md", text)
        self.git(self.seed, "push", "--quiet", "origin", "main")

    def test_an_entry_on_main_equal_to_origin_has_no_warnings(self):
        self.assertEqual(check_entry.check(self.entry), [])

    def test_another_branch_is_named(self):
        self.git(self.entry, "switch", "--quiet", "-c", "work/other")
        self.git(self.entry, "push", "--quiet", "origin", "work/other")
        self.assertEqual(check_entry.check(self.entry), ["the entry is on work/other, not on main"])

    def test_a_detached_entry_is_named(self):
        self.git(self.entry, "switch", "--quiet", "--detach")
        self.assertEqual(check_entry.check(self.entry), ["the entry is not on a branch but on a detached commit"])

    def test_own_commits_and_lag_are_counted_and_point_to_the_plan_on_origin(self):
        self.commit(self.entry, "local.txt", "local\n")
        self.publish_plan("# Plan\n\nA new version on origin.\n")
        warnings = check_entry.check(self.entry)
        self.assertEqual(len(warnings), 2, warnings)
        self.assertIn("(1 own commits, 1 behind)", warnings[0])
        self.assertIn("git show origin/main:docs/plan.md", warnings[0])
        self.assertTrue(warnings[1].startswith("local branches with no copy on origin"), warnings)

    def test_uncommitted_tracked_changes_are_counted_and_untracked_files_are_not(self):
        (self.entry / "docs/plan.md").write_text("changed locally\n")
        (self.entry / "untracked.txt").write_text("untracked\n")
        self.assertEqual(check_entry.check(self.entry), ["1 tracked files have uncommitted changes"])

    def test_a_local_only_branch_warns_until_the_plan_on_origin_names_it(self):
        self.git(self.entry, "branch", "work/local")
        self.git(self.entry, "switch", "--quiet", "work/local")
        self.commit(self.entry, "local.txt", "local\n")
        self.git(self.entry, "switch", "--quiet", "main")
        self.assertEqual(check_entry.check(self.entry),
                         ["local branches with no copy on origin and no named reason in the plan: work/local"])
        self.publish_plan("# Plan\n\nBranch work/local is archived; reason named.\n")
        warnings = check_entry.check(self.entry)
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("0 own commits, 1 behind", warnings[0])

    def test_a_failed_fetch_is_a_warning_and_the_comparison_still_runs(self):
        self.git(self.entry, "remote", "set-url", "origin", str(Path(self.temp.name) / "missing.git"))
        self.assertEqual(check_entry.check(self.entry), ["origin could not be fetched; the comparison uses the last fetched state"])

    def test_without_origin_main_the_entry_cannot_be_compared(self):
        self.git(self.entry, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(check_entry.check(self.entry, fetch=False), ["origin/main is not present locally; the entry cannot be compared"])

    def test_the_check_changes_no_branch_file_or_configuration(self):
        self.commit(self.entry, "local.txt", "local\n")
        (self.entry / "docs/plan.md").write_text("changed locally\n")
        before = (self.git(self.entry, "rev-parse", "HEAD"), self.git(self.entry, "rev-parse", "--abbrev-ref", "HEAD"),
                  self.git(self.entry, "status", "--porcelain"), (self.entry / ".git/config").read_bytes())
        check_entry.check(self.entry)
        after = (self.git(self.entry, "rev-parse", "HEAD"), self.git(self.entry, "rev-parse", "--abbrev-ref", "HEAD"),
                 self.git(self.entry, "status", "--porcelain"), (self.entry / ".git/config").read_bytes())
        self.assertEqual(before, after)

    def test_the_command_prints_each_warning_and_a_summary_and_always_exits_zero(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(check_entry.main(["--no-fetch"], repo=self.entry), 0)
        self.assertEqual(out.getvalue(), "ENTRY OK\n")
        self.git(self.entry, "switch", "--quiet", "--detach")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(check_entry.main(["--no-fetch"], repo=self.entry), 0)
        self.assertEqual(out.getvalue(), "WARNING: the entry is not on a branch but on a detached commit\n"
                                         "ENTRY: 1 warnings\n")


if __name__ == "__main__":
    unittest.main()
