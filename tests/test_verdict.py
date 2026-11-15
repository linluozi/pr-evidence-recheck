import unittest

from prrecheck import verdict as V


def summary(speed, rsd=0.01):
    return {"speedup": speed, "baseline_rsd": rsd, "candidate_rsd": rsd}


def base_kwargs(**over):
    kw = dict(
        same_tree=True,
        tree_detail="patched == head tree",
        tests_baseline_failed=0,
        tests_patched_failed=0,
        tests_baseline_passed=1401,
        tests_patched_passed=1401,
        diff_unique_inputs=2000,
        diff_mismatches=0,
        diff_min_unique=1000,
        scales={"small": summary(1.9), "medium": summary(2.0), "large": summary(1.8)},
        keep_threshold=1.30,
        worst_case_floor=1.00,
    )
    kw.update(over)
    return kw


class DecideTests(unittest.TestCase):
    def test_all_gates_pass_is_keep(self):
        v = V.decide(**base_kwargs())
        self.assertEqual(v.decision, V.KEEP)
        self.assertEqual(v.reasons, [])
        self.assertTrue(all(g.passed for g in v.gates))

    def test_different_tree_retracts(self):
        v = V.decide(**base_kwargs(same_tree=False))
        self.assertEqual(v.decision, V.RETRACT)
        self.assertIn("T1-same-tree", [g.name for g in v.gates if not g.passed])

    def test_patched_test_regression_retracts(self):
        v = V.decide(**base_kwargs(tests_baseline_failed=0, tests_patched_failed=1))
        self.assertEqual(v.decision, V.RETRACT)

    def test_same_failure_count_is_not_a_regression(self):
        v = V.decide(**base_kwargs(tests_baseline_failed=1, tests_patched_failed=1))
        self.assertEqual(v.decision, V.KEEP)

    def test_missing_tests_retracts(self):
        v = V.decide(**base_kwargs(tests_baseline_failed=None, tests_patched_failed=None))
        self.assertEqual(v.decision, V.RETRACT)

    def test_differential_mismatch_retracts(self):
        v = V.decide(**base_kwargs(diff_mismatches=1))
        self.assertEqual(v.decision, V.RETRACT)

    def test_too_few_unique_inputs_retracts(self):
        v = V.decide(**base_kwargs(diff_unique_inputs=999))
        self.assertEqual(v.decision, V.RETRACT)

    def test_median_below_bar_retracts(self):
        v = V.decide(**base_kwargs(scales={
            "small": summary(1.2), "medium": summary(1.9), "large": summary(1.1)}))
        self.assertEqual(v.decision, V.RETRACT)
        self.assertAlmostEqual(v.median_speedup, 1.2)
        self.assertTrue(any("median" in r for r in v.reasons))

    def test_median_at_bar_is_keep(self):
        v = V.decide(**base_kwargs(scales={
            "small": summary(1.30), "medium": summary(1.30), "large": summary(1.30)}))
        self.assertEqual(v.decision, V.KEEP)

    def test_worst_case_regression_retracts(self):
        v = V.decide(**base_kwargs(scales={
            "small": summary(2.0), "medium": summary(2.0), "large": summary(0.94)}))
        self.assertEqual(v.decision, V.RETRACT)
        self.assertAlmostEqual(v.worst_speedup, 0.94)

    def test_worst_case_at_floor_is_keep(self):
        v = V.decide(**base_kwargs(scales={
            "small": summary(2.0), "medium": summary(2.0), "large": summary(1.00)}))
        self.assertEqual(v.decision, V.KEEP)

    def test_noisy_only_is_inconclusive(self):
        v = V.decide(**base_kwargs(scales={
            "small": summary(1.9, rsd=0.30), "medium": summary(2.0), "large": summary(1.8)}))
        self.assertEqual(v.decision, V.INCONCLUSIVE)

    def test_no_scales_retracts(self):
        v = V.decide(**base_kwargs(scales={}))
        self.assertEqual(v.decision, V.RETRACT)

    def test_verdict_dict_is_serialisable(self):
        d = V.decide(**base_kwargs()).as_dict()
        self.assertEqual(d["decision"], "KEEP")
        self.assertEqual(len(d["gates"]), 6)


if __name__ == "__main__":
    unittest.main()
