import unittest

from prrecheck import certificate as C


class CanonicalJsonTests(unittest.TestCase):
    def test_sorted_and_compact(self):
        self.assertEqual(C.canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_key_order_does_not_change_digest(self):
        self.assertEqual(
            C.sha256_hex(C.canonical_json({"a": 1, "b": [2, 3]})),
            C.sha256_hex(C.canonical_json({"b": [2, 3], "a": 1})),
        )

    def test_non_ascii_is_preserved(self):
        self.assertIn("日本語", C.canonical_json({"k": "日本語"}))


class CertificateTests(unittest.TestCase):
    def test_roundtrip_verifies(self):
        cert = C.make_certificate({"decision": "KEEP", "speedup": 1.9})
        self.assertTrue(C.verify_certificate(cert))

    def test_tamper_is_detected(self):
        cert = C.make_certificate({"decision": "KEEP", "speedup": 1.9})
        cert["speedup"] = 9.9
        self.assertFalse(C.verify_certificate(cert))

    def test_missing_digest_is_invalid(self):
        self.assertFalse(C.verify_certificate({"decision": "KEEP"}))

    def test_double_make_raises(self):
        cert = C.make_certificate({"a": 1})
        with self.assertRaises(ValueError):
            C.make_certificate(cert)

    def test_dump_is_deterministic(self):
        cert = C.make_certificate({"a": 1, "b": {"c": 2}})
        self.assertEqual(C.dumps_certificate(cert), C.dumps_certificate(cert))
        self.assertTrue(C.dumps_certificate(cert).endswith("\n"))

    def test_sha256_bytes(self):
        self.assertEqual(
            C.sha256_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )


if __name__ == "__main__":
    unittest.main()
