"""Sieve Schema Contract v1 conformance corpus replica (Crowd JSON layer).

A sha256-pinned copy of the canonical corpus from the sieve-lens
repository (tests/corpus/schema_contract_v1.json), following the
sieve-tray vendor-sync precedent: silent drift between the copies
fails the build and a human reviews the diff.

Scope: corpus cases with layer == "json" and violations within
{"dup_key", "nan_inf"} — the JSON-layer core Crowd implements
(sieve_crowd.jsonio). The BOM case is a DECLARED divergence per the
conformance matrix in the contract (docs section §6): Crowd decodes
with utf-8-sig on purpose (spreadsheet/Excel exports carry a BOM), so
the runner pins the acceptance instead of the refusal. Schema-layer
cases are out of Crowd's scope: record shapes are checked by the
io/engine domains, not by the shared mini-validator.
"""

import hashlib
import json
import unittest
from pathlib import Path

from sieve_crowd.jsonio import _load
from sieve_crowd.model import InputError

CORPUS = Path(__file__).resolve().parent / "corpus" / "schema_contract_v1.json"
CORPUS_SHA256 = "514d45eb2580a9ea5a4336094be347d9c9bd8fb2990044551aec96cd094ae6aa"


def _load_corpus():
    return json.loads(CORPUS.read_text(encoding="utf-8"))


class CorpusIntegrity(unittest.TestCase):
    def test_corpus_file_matches_pin(self):
        actual = hashlib.sha256(CORPUS.read_bytes()).hexdigest()
        self.assertEqual(
            actual, CORPUS_SHA256,
            "the replicated corpus drifted from its pin; if the contract "
            "update is intentional, refresh the pin in the same cycle as "
            "the sieve-lens canonical copy")

    def test_corpus_declares_the_current_contract(self):
        corpus = _load_corpus()
        self.assertEqual(corpus["contract"], "sieve-schema-contract-v1")
        self.assertEqual(corpus["corpus_version"], "1")
        ids = [case["id"] for case in corpus["cases"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate case ids")


class JsonLayerCoreConformance(unittest.TestCase):
    def test_dup_key_and_nan_inf_cases(self):
        corpus = _load_corpus()
        for case in corpus["cases"]:
            if case["layer"] != "json" or case["expect"] != "reject":
                continue
            if not set(case.get("violations", [])) <= {"dup_key", "nan_inf"}:
                continue  # bom / size-cap are declared divergences
            with self.subTest(case=case["id"]):
                with self.assertRaises(InputError):
                    _load(case["input_text"].encode("utf-8"))

    def test_accept_case_parses(self):
        corpus = _load_corpus()
        accept = [c for c in corpus["cases"]
                  if c["layer"] == "json" and c["expect"] == "accept"]
        self.assertTrue(accept)
        for case in accept:
            with self.subTest(case=case["id"]):
                self.assertIsNotNone(_load(case["input_text"].encode("utf-8")))

    def test_bom_is_a_declared_divergence(self):
        # Contract v1 refuses a leading BOM; Crowd accepts it on purpose
        # (utf-8-sig for spreadsheet exports). Pin the decision here so
        # a future silent change shows up as a diff.
        corpus = _load_corpus()
        bom = [c for c in corpus["cases"]
               if "bom" in c.get("violations", [])]
        self.assertTrue(bom)
        for case in bom:
            with self.subTest(case=case["id"]):
                self.assertIsNotNone(_load(case["input_text"].encode("utf-8")))


if __name__ == "__main__":
    unittest.main()
