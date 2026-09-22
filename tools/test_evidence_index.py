"""Behavioral tests, including deterministic filesystem substitution races."""

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import evidence_index as index


class EvidenceIndexTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "root"
        self.root.mkdir()
        (self.root / "nested").mkdir()
        self.contents = {"a": b"abc", "nested/åäö.bin": bytes(range(256)) + b"\x00\xff"}
        for name, data in self.contents.items():
            (self.root / name).write_bytes(data)

    def manifest(self, paths=None):
        return index.create(self.root, list(self.contents) if paths is None else paths)

    def cli(self, *args, stdin=b""):
        result = subprocess.run(
            [sys.executable, "-B", str(Path(index.__file__).resolve()), *map(str, args)],
            input=stdin, capture_output=True, timeout=5,
        )
        self.assertNotIn(b"Traceback", result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_manifest_and_verification_binary_unicode_sorted(self):
        before = {p.relative_to(self.root) for p in self.root.rglob("*")}
        manifest = self.manifest(reversed(list(self.contents)))
        expected = {"version": 1, "files": [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in sorted(self.contents.items())
        ]}
        self.assertEqual(manifest, expected)
        self.assertEqual(index.verify(self.root, manifest), {"ok": True, "files": [
            {"path": name, "status": "ok"} for name in sorted(self.contents)
        ]})
        self.assertEqual(before, {p.relative_to(self.root) for p in self.root.rglob("*")})
        for name, data in self.contents.items():
            self.assertEqual((self.root / name).read_bytes(), data)

    def test_empty_manifest_and_empty_file(self):
        self.assertEqual(self.manifest([]), {"version": 1, "files": []})
        self.assertEqual(index.verify(self.root, self.manifest([])), {"ok": True, "files": []})
        (self.root / "empty").touch()
        entry = self.manifest(["empty"])["files"][0]
        self.assertEqual(entry["size"], 0)
        self.assertEqual(entry["sha256"], hashlib.sha256(b"").hexdigest())

    def test_all_entries_inspected_after_changes(self):
        (self.root / "z").write_bytes(b"unchanged")
        manifest = self.manifest(["z", "nested/åäö.bin", "a"])
        (self.root / "a").write_bytes(b"abd")  # Same size, different hash.
        (self.root / "nested/åäö.bin").unlink()
        self.assertEqual(index.verify(self.root, manifest), {"ok": False, "files": [
            {"path": "a", "status": "changed"},
            {"path": "nested/åäö.bin", "status": "missing"},
            {"path": "z", "status": "ok"},
        ]})

    def test_size_mismatch(self):
        manifest = self.manifest(["a"])
        manifest["files"][0]["size"] += 1
        self.assertEqual(index.verify(self.root, manifest)["files"][0]["status"], "changed")

    def test_invalid_paths(self):
        for path in ("", ".", "..", "a/", "a//b", "a/./b", "a/../b", "/a",
                     "\\a", "a\\b", "a\0b", "C:a", "z:/a", 1, None, True):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.manifest([path])
        for paths in (["a", "a"], "a", b"a", None, 1, {"a": 1}):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                index.create(self.root, paths)

    def test_invalid_roots_even_with_no_files(self):
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.root, target_is_directory=True)
        for root in (None, 1, "", "\0", self.root / "absent", self.root / "a",
                     link, str(link) + "/", str(link) + "/./"):
            with self.subTest(root=root):
                with self.assertRaises(ValueError):
                    index.create(root, [])
                with self.assertRaises(ValueError):
                    index.verify(root, {"version": 1, "files": []})

    def test_whole_manifest_validated_before_reads(self):
        good = self.manifest(["a"])
        bad = [None, [], {}, {**good, "extra": 1}, {**good, "version": True},
               {**good, "version": 1.0}, {**good, "version": 2},
               {**good, "files": ()}, {**good, "files": [None]},
               {**good, "files": good["files"] * 2}]
        entry = good["files"][0]
        bad_entries = [{}, {**entry, "extra": 1}]
        for key, values in {
            "path": ["", "../a", "/a", "a//b", "a\\b", "C:a", False],
            "sha256": ["A" * 64, "a" * 63, "a" * 65, "g" * 64, "a" * 64 + "\n", 1],
            "size": [-1, True, 1.0, "3", None],
        }.items():
            bad_entries.extend({**entry, key: value} for value in values)
        bad.extend({"version": 1, "files": [entry, value]} for value in bad_entries)
        with mock.patch.object(index, "_digest", side_effect=AssertionError("read invalid input")):
            for manifest in bad:
                with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                    index.verify(self.root, manifest)

    def test_symlinks_directories_fifos_and_missing_components(self):
        good = self.manifest(["a"])["files"][0]
        (self.root / "link").symlink_to(self.root / "a")
        (self.root / "dangling").symlink_to(self.root / "absent")
        (self.root / "dirlink").symlink_to(self.root / "nested", target_is_directory=True)
        os.mkfifo(self.root / "fifo")
        statuses = {"link": "unsafe", "dangling": "unsafe", "dirlink/åäö.bin": "unsafe",
                    "nested": "unsafe", "fifo": "unsafe", "a/child": "unsafe",
                    "absent/child": "missing", "absent": "missing"}
        manifest = {"version": 1, "files": [{**good, "path": name} for name in statuses]}
        for name in statuses:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.manifest([name])
        expected = {"ok": False, "files": [
            {"path": name, "status": status} for name, status in sorted(statuses.items())
        ]}
        self.assertEqual(index.verify(self.root, manifest), expected)
        self.assertEqual(self.cli("verify", self.root, stdin=json.dumps(manifest).encode()), (1, expected))
        code, result = self.cli("create", self.root, "fifo")
        self.assertEqual(code, 2)
        self.assertTrue(result["error"])

    def test_unreadable_is_unsafe(self):
        manifest = self.manifest(["a"])
        real_open = os.open

        def deny(path, flags, *args, **kwargs):
            if path == "a":
                raise PermissionError("denied")
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(index.os, "open", side_effect=deny):
            self.assertEqual(index.verify(self.root, manifest)["files"][0]["status"], "unsafe")
            with self.assertRaises(ValueError):
                self.manifest(["a"])

    def test_changes_during_read_are_reported(self):
        manifest = self.manifest(["a"])
        real_read = os.read
        for operation in ("create", "verify"):
            (self.root / "a").write_bytes(b"abc")
            changed = False

            def mutate(fd, size):
                nonlocal changed
                data = real_read(fd, size)
                if not changed:
                    changed = True
                    (self.root / "a").write_bytes(b"abcdef")
                return data

            with mock.patch.object(index.os, "read", side_effect=mutate):
                if operation == "create":
                    with self.assertRaisesRegex(ValueError, "changed"):
                        self.manifest(["a"])
                else:
                    self.assertEqual(index.verify(self.root, manifest)["files"][0]["status"], "changed")

    def test_replacement_during_read_is_reported(self):
        manifest = self.manifest(["a"])
        real_read = os.read
        replaced = False

        def replace(fd, size):
            nonlocal replaced
            data = real_read(fd, size)
            if not replaced:
                replaced = True
                (self.root / "replacement").write_bytes(b"abc")
                os.replace(self.root / "replacement", self.root / "a")
            return data

        with mock.patch.object(index.os, "read", side_effect=replace):
            self.assertEqual(index.verify(self.root, manifest)["files"][0]["status"], "changed")

    def test_substitution_cannot_follow_symlinks_or_block_on_fifo(self):
        real_open = os.open
        for kind in ("file_symlink", "directory_symlink", "fifo"):
            with self.subTest(kind=kind):
                target = self.root / ("race_dir" if kind == "directory_symlink" else "race")
                if kind == "directory_symlink":
                    target.mkdir()
                    (target / "file").write_bytes(b"inside")
                    selected = "race_dir/file"
                else:
                    target.write_bytes(b"inside")
                    selected = "race"
                manifest = self.manifest([selected])
                outside = Path(self.temp.name) / "outside"
                outside.mkdir(exist_ok=True)
                (outside / "file").write_bytes(b"outside")
                substituted = False

                def substitute(path, flags, *args, **kwargs):
                    nonlocal substituted
                    if path == target.name and not substituted:
                        substituted = True
                        if kind == "directory_symlink":
                            (target / "file").unlink()
                            target.rmdir()
                            target.symlink_to(outside, target_is_directory=True)
                        else:
                            target.unlink()
                            if kind == "fifo":
                                self.assertTrue(flags & os.O_NONBLOCK)
                                os.mkfifo(target)
                            else:
                                target.symlink_to(outside / "file")
                    return real_open(path, flags, *args, **kwargs)

                with mock.patch.object(index.os, "open", side_effect=substitute):
                    self.assertEqual(index.verify(self.root, manifest)["files"][0]["status"], "unsafe")
                target.unlink()

    def test_cli_roundtrip_and_exit_codes(self):
        code, manifest = self.cli("create", self.root, *reversed(list(self.contents)))
        self.assertEqual(code, 0)
        self.assertEqual(manifest, self.manifest())
        payload = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        self.assertEqual(self.cli("verify", self.root, stdin=payload), (0, index.verify(self.root, manifest)))
        (self.root / "a").unlink()
        self.assertEqual(self.cli("verify", self.root, stdin=payload)[0], 1)
        self.assertEqual(self.cli("create", self.root), (0, {"version": 1, "files": []}))

    def test_cli_invalid_invocations_and_stdin(self):
        for args in ((), ("create",), ("unknown", str(self.root)),
                     ("verify", str(self.root), "extra"), ("create", str(self.root), "../a")):
            with self.subTest(args=args):
                code, result = self.cli(*args)
                self.assertEqual(code, 2)
                self.assertTrue(result["error"])
        good = self.manifest(["a"])
        entry = json.dumps(good["files"][0])
        for payload in (b"", b"{", b"\xff", b"null", b"{} {}", b"NaN", b"Infinity",
                        b'{"version":1,"version":1,"files":[]}',
                        ('{"version":1,"files":[' + entry[:-1] + ',"size":3}]}').encode(),
                        json.dumps({**good, "version": True}).encode(), b"[" * 2000):
            with self.subTest(payload=payload[:100]):
                code, result = self.cli("verify", self.root, stdin=payload)
                self.assertEqual(code, 2)
                self.assertTrue(result["error"])

    def populate_tree(self):
        """Add nested, hidden and UTF-8 files plus empty directories; return the sorted paths."""
        (self.root / "nested" / "deeper").mkdir()
        (self.root / "b").mkdir()
        (self.root / "empty").mkdir()
        (self.root / "nested" / "empty").mkdir()
        (self.root / "nested" / "deeper" / ".empty").mkdir()
        added = {".hidden": b"h", "b.txt": b"before slash", "b/c": b"c",
                 "nested/.dot": b"dot", "nested/deeper/ünï.txt": "ünï".encode("utf-8")}
        for name, data in added.items():
            (self.root / name).write_bytes(data)
        self.contents.update(added)
        return sorted(self.contents)

    def test_select_tree_lists_nested_hidden_and_utf8_files_only(self):
        expected = self.populate_tree()
        before = {p.relative_to(self.root) for p in self.root.rglob("*")}
        # "b.txt" sorts before "b/c" because "." < "/", exactly as create orders paths.
        self.assertEqual(expected, [".hidden", "a", "b.txt", "b/c", "nested/.dot",
                                    "nested/deeper/ünï.txt", "nested/åäö.bin"])
        with mock.patch.object(index.os, "read", side_effect=AssertionError("read contents")):
            selected = index.select_tree(self.root)
            self.assertEqual(index.select_tree(str(self.root)), selected)
        self.assertEqual(selected, expected)
        self.assertEqual(selected, sorted(selected))
        manifest = index.create(self.root, index.select_tree(self.root))
        self.assertEqual(manifest, self.manifest(reversed(expected)))
        self.assertEqual([entry["path"] for entry in manifest["files"]], selected)
        self.assertEqual(index.verify(self.root, manifest)["ok"], True)
        self.assertEqual(before, {p.relative_to(self.root) for p in self.root.rglob("*")})
        for name, data in self.contents.items():
            self.assertEqual((self.root / name).read_bytes(), data)

    def test_select_tree_order_is_sorted_regardless_of_directory_order(self):
        expected = self.populate_tree()
        real_scandir = os.scandir

        class Listing:
            def __init__(self, entries):
                self.entries = entries

            def __enter__(self):
                return iter(self.entries)

            def __exit__(self, *exc_info):
                return False

        def reversed_scandir(fd):
            with real_scandir(fd) as entries:
                return Listing(sorted(entries, key=lambda entry: entry.name, reverse=True))

        with mock.patch.object(index.os, "scandir", side_effect=reversed_scandir):
            self.assertEqual(index.select_tree(self.root), expected)
        self.assertEqual(index.select_tree(self.root), expected)

    def test_select_tree_empty_root_and_empty_directories(self):
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        self.assertEqual(index.select_tree(empty), [])
        self.assertEqual(index.create(empty, index.select_tree(empty)), {"version": 1, "files": []})
        self.assertEqual(self.cli("create", empty, "--tree"), (0, {"version": 1, "files": []}))
        (empty / "only" / "dirs").mkdir(parents=True)
        (empty / ".hidden").mkdir()
        self.assertEqual(index.select_tree(empty), [])
        self.assertEqual(self.cli("create", empty, "--tree"), (0, {"version": 1, "files": []}))

    def test_select_tree_invalid_roots(self):
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.root, target_is_directory=True)
        for root in (None, 1, "", "\0", self.root / "absent", self.root / "a",
                     link, str(link) + "/", str(link) + "/./"):
            with self.subTest(root=root), self.assertRaises(ValueError):
                index.select_tree(root)

    def test_select_tree_refuses_symlinks_and_fifos_naming_the_path(self):
        self.populate_tree()
        cases = {
            "link": lambda p: p.symlink_to(self.root / "a"),
            "dangling": lambda p: p.symlink_to(self.root / "absent"),
            "dirlink": lambda p: p.symlink_to(self.root / "nested", target_is_directory=True),
            "nested/deeper/fifo": os.mkfifo,
            "b/.link": lambda p: p.symlink_to(self.root / "a"),
        }
        for name, make in cases.items():
            with self.subTest(name=name):
                target = self.root / name
                make(target)
                with self.assertRaisesRegex(ValueError, re.escape(name)):
                    index.select_tree(self.root)
                with self.assertRaisesRegex(ValueError, re.escape(name)):
                    index.create(self.root, index.select_tree(self.root))
                code, result = self.cli("create", self.root, "--tree")
                self.assertEqual(code, 2)
                self.assertEqual(list(result), ["error"])
                self.assertIn(name, result["error"])
                # Explicit paths remain the way to index a tree with refused entries.
                self.assertEqual(self.manifest(["a", "b/c"]), self.manifest(["b/c", "a"]))
                self.assertEqual(self.cli("create", self.root, "a")[0], 0)
                target.unlink()
        self.assertEqual(index.select_tree(self.root), sorted(self.contents))

    def test_select_tree_closes_every_descriptor(self):
        self.populate_tree()
        real_open, real_close = os.open, os.close
        opened, closed = [], []

        def record_open(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            opened.append(fd)
            self.assertTrue(flags & os.O_NOFOLLOW)
            if "dir_fd" in kwargs:
                # Below root, every open is a single name relative to a descriptor.
                self.assertNotIn("/", path)
            return fd

        def record_close(fd):
            closed.append(fd)
            real_close(fd)

        with mock.patch.object(index.os, "open", side_effect=record_open), \
                mock.patch.object(index.os, "close", side_effect=record_close):
            index.select_tree(self.root)
            self.assertTrue(opened)
            self.assertEqual(Counter(opened), Counter(closed))
            opened.clear()
            closed.clear()
            os.mkfifo(self.root / "nested" / "deeper" / "fifo")
            with self.assertRaisesRegex(ValueError, "nested/deeper/fifo"):
                index.select_tree(self.root)
            self.assertTrue(opened)
            self.assertEqual(Counter(opened), Counter(closed))

    def test_cli_tree_success_and_invocation_errors(self):
        expected = self.populate_tree()
        code, manifest = self.cli("create", self.root, "--tree")
        self.assertEqual(code, 0)
        self.assertEqual(manifest, index.create(self.root, index.select_tree(self.root)))
        self.assertEqual([entry["path"] for entry in manifest["files"]], expected)
        self.assertEqual(manifest["version"], 1)
        payload = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        self.assertEqual(self.cli("verify", self.root, stdin=payload)[0], 0)
        for args in (("create", str(self.root), "--tree", "a"),
                     ("create", str(self.root), "a", "--tree"),
                     ("create", str(self.root), "--tree", "--tree"),
                     ("verify", str(self.root), "--tree"),
                     ("create", str(self.root / "absent"), "--tree"),
                     ("create", str(self.root / "a"), "--tree")):
            with self.subTest(args=args):
                code, result = self.cli(*args, stdin=payload)
                self.assertEqual(code, 2)
                self.assertEqual(list(result), ["error"])
                self.assertTrue(result["error"])
        # A file literally named --tree is listed by the tree mode and selectable
        # through the importable function, but not as an explicit CLI path.
        (self.root / "--tree").write_bytes(b"flag")
        self.assertIn("--tree", index.select_tree(self.root))
        self.assertEqual(index.create(self.root, ["--tree"])["files"][0]["size"], 4)
        code, manifest = self.cli("create", self.root, "--tree")
        self.assertEqual(code, 0)
        self.assertIn("--tree", [entry["path"] for entry in manifest["files"]])
        self.assertEqual(self.cli("create", self.root), (0, {"version": 1, "files": []}))


if __name__ == "__main__":
    unittest.main()
