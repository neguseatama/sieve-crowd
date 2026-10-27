import json
import os
import re
import unittest

import sieve_crowd
from sieve_crowd.generalize import make_generalizer
from sieve_crowd.pseudonym import pseudonym

HERE = os.path.dirname(__file__)


def load():
    with open(os.path.join(HERE, "vectors", "vectors.json"), encoding="utf-8") as fh:
        return json.load(fh)


class VectorTests(unittest.TestCase):
    def test_generalization_vectors(self):
        for case in load()["generalization"]:
            g = make_generalizer(case["settings"])
            g.prepare(case["values"])
            for value, labels in zip(case["values"], case["labels"]):
                self.assertEqual([g.label(value, l) for l in range(g.levels + 1)], labels, (case["name"], value))

    def test_pseudonym_vectors(self):
        v = load()["pseudonym"]
        key = bytes.fromhex(v["key_hex"])
        for column, value, expected in v["cases"]:
            self.assertEqual(pseudonym(key, column, value), expected)


class VersionConsistency(unittest.TestCase):
    def test_package_and_pyproject_versions_agree(self):
        with open(os.path.join(os.path.dirname(HERE), "pyproject.toml"), encoding="utf-8") as fh:
            m = re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.M)
        self.assertEqual(m.group(1), sieve_crowd.__version__)


if __name__ == "__main__":
    unittest.main()
