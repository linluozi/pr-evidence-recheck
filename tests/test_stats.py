import unittest

from prrecheck import stats


class PercentileTests(unittest.TestCase):
    def test_median_odd(self):
        self.assertEqual(stats.median([3, 1, 2]), 2)

    def test_median_even(self):
        self.assertEqual(stats.median([1, 2, 3, 4]), 2.5)

    def test_percentile_interpolates(self):
        self.assertAlmostEqual(stats.percentile([0, 10], 25), 2.5)

    def test_percentile_bounds(self):
        self.assertEqual(stats.percentile([5, 1, 9], 0), 1)
        self.assertEqual(stats.percentile([5, 1, 9], 100), 9)

    def test_percentile_single(self):
        self.assertEqual(stats.percentile([7], 42), 7)

    def test_percentile_rejects_empty(self):
        with self.assertRaises(ValueError):
            stats.percentile([], 50)

    def test_percentile_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            stats.percentile([1, 2], 101)

    def test_quartiles(self):
        xs = list(range(1, 9))
        self.assertAlmostEqual(stats.p25(xs), 2.75)
        self.assertAlmostEqual(stats.p75(xs), 6.25)


class SpreadTests(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(stats.mean([2, 4, 6]), 4)

    def test_stdev_sample(self):
        self.assertAlmostEqual(stats.stdev([2, 4, 4, 4, 5, 5, 7, 9]), 2.1380899352993947)

    def test_stdev_short_is_zero(self):
        self.assertEqual(stats.stdev([3]), 0.0)

    def test_rsd_zero_mean(self):
        self.assertEqual(stats.rsd([0, 0, 0]), 0.0)

    def test_rsd_positive(self):
        self.assertGreater(stats.rsd([1, 2, 3, 4]), 0.0)


class SpeedupTests(unittest.TestCase):
    def test_speedup_ratio_of_medians(self):
        self.assertAlmostEqual(stats.speedup([2, 4, 6], [1, 2, 3]), 2.0)

    def test_noise_gives_one(self):
        self.assertAlmostEqual(stats.speedup([1, 2, 3], [1, 2, 3]), 1.0)


class BootstrapTests(unittest.TestCase):
    def test_deterministic_for_seed(self):
        a = [10, 11, 12, 13, 14]
        b = [5, 6, 7, 8, 9]
        self.assertEqual(stats.bootstrap_ci(a, b, seed=1), stats.bootstrap_ci(a, b, seed=1))

    def test_interval_contains_ratio(self):
        a = [100, 101, 99, 102, 98]
        b = [50, 51, 49, 52, 48]
        lo, hi = stats.bootstrap_ci(a, b, iterations=500, seed=5)
        self.assertLessEqual(lo, 2.0)
        self.assertGreaterEqual(hi, 2.0)

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            stats.bootstrap_ci([], [1])

    def test_rejects_low_iterations(self):
        with self.assertRaises(ValueError):
            stats.bootstrap_ci([1], [1], iterations=10)


class SummarizeTests(unittest.TestCase):
    def test_keys_and_values(self):
        s = stats.summarize([10, 12, 11], [5, 6, 5.5], ci_iterations=200, seed=3)
        self.assertEqual(s["n"], [3, 3])
        self.assertAlmostEqual(s["speedup"], 2.0)
        self.assertEqual(len(s["speedup_ci95"]), 2)
        for key in ("baseline_median_ns", "candidate_median_ns", "baseline_rsd", "candidate_rsd"):
            self.assertIn(key, s)


if __name__ == "__main__":
    unittest.main()
