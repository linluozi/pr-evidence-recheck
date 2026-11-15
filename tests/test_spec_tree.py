import json
import os
import subprocess
import tempfile
import unittest

from prrecheck import cli, twotree


def _spec(**over):
    spec = {
        "name": "x",
        "upstream": "o/r",
        "pr": 1,
        "git_url": "git@example:o/r.git",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "head_tree_sha": "c" * 40,
        "patch": "patches/x.diff",
        "pythonpath_rel": "src",
        "workload": "workloads/x.py",
        "scales": ["small"],
        "upstream_tests": {"command": ["-m", "pytest"]},
        "keep_threshold": 1.3,
        "worst_case_floor": 1.0,
    }
    spec.update(over)
    return spec


class SpecTests(unittest.TestCase):
    def _write(self, spec):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(spec, fh)
        self.addCleanup(os.unlink, path)
        return path

    def test_load_valid_spec(self):
        spec = cli.load_spec(self._write(_spec()))
        self.assertEqual(spec["name"], "x")

    def test_missing_key_raises(self):
        bad = _spec()
        del bad["head_tree_sha"]
        with self.assertRaises(ValueError):
            cli.load_spec(self._write(bad))

    def test_empty_scales_raises(self):
        with self.assertRaises(ValueError):
            cli.load_spec(self._write(_spec(scales=[])))

    def test_floor_above_bar_raises(self):
        with self.assertRaises(ValueError):
            cli.load_spec(self._write(_spec(keep_threshold=1.0, worst_case_floor=1.1)))


class ParsePytestSummaryTests(unittest.TestCase):
    def test_green_run_has_zero_failed(self):
        s = twotree.parse_pytest_summary("1401 passed, 10 skipped, 1 xfailed in 11.33s", 0)
        self.assertEqual(s["passed"], 1401)
        self.assertEqual(s["failed"], 0)
        self.assertEqual(s["errors"], 0)
        self.assertEqual(s["skipped"], 10)

    def test_failure_is_parsed(self):
        s = twotree.parse_pytest_summary("1 failed, 345 passed, 448 subtests passed in 2.49s", 1)
        self.assertEqual(s["failed"], 1)
        self.assertEqual(s["passed"], 345)
        self.assertIsNone(s["errors"])

    def test_errors_token(self):
        s = twotree.parse_pytest_summary("2 errors in 0.38s", 2)
        self.assertEqual(s["errors"], 2)


class SameTreeTests(unittest.TestCase):
    def test_equal_hashes(self):
        self.assertTrue(twotree.same_tree("abc", "abc"))

    def test_different_hashes(self):
        self.assertFalse(twotree.same_tree("abc", "abd"))


class RunnerEnvTests(unittest.TestCase):
    def test_pythonpath_and_hashseed(self):
        env = twotree.runner_env("/t", "src")
        self.assertEqual(env["PYTHONPATH"].split(os.pathsep)[0], "/t/src")
        self.assertEqual(env["PYTHONHASHSEED"], "0")

    def test_root_pythonpath(self):
        env = twotree.runner_env("/t", ".")
        self.assertEqual(env["PYTHONPATH"].split(os.pathsep)[0], "/t")


class ApplyPatchTests(unittest.TestCase):
    def _repo(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        run = lambda *a: subprocess.run(a, cwd=d, check=True, stdout=subprocess.PIPE, text=True)
        run("git", "init", "-q", "-b", "main")
        run("git", "config", "user.email", "t@example.com")
        run("git", "config", "user.name", "t")
        with open(os.path.join(d, "f.txt"), "w") as fh:
            fh.write("one\n")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "base")
        return d

    def test_apply_patch_changes_tree_hash(self):
        d = self._repo()
        before = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=d,
                                stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
        patch = os.path.join(d, "p.diff")
        with open(patch, "w") as fh:
            fh.write("diff --git a/f.txt b/f.txt\n--- a/f.txt\n+++ b/f.txt\n@@ -1 +1 @@\n-one\n+two\n")
        proof = twotree.apply_patch(twotree.Tree(d, before), patch)
        self.assertNotEqual(proof["tree_sha"], before)
        self.assertIn("f.txt", proof["diff_stat"])

    def test_bad_patch_raises(self):
        d = self._repo()
        patch = os.path.join(d, "bad.diff")
        with open(patch, "w") as fh:
            fh.write("diff --git a/nope.txt b/nope.txt\n--- a/nope.txt\n+++ b/nope.txt\n@@ -1 +1 @@\n-a\n+b\n")
        with self.assertRaises(twotree.TwoTreeError):
            twotree.apply_patch(twotree.Tree(d, "x"), patch)


if __name__ == "__main__":
    unittest.main()
