"""CI contracts (v0.5.2): the workflows under .github/workflows are part of the
project's behavior and are pinned like everything else.

  - test.yml runs the full suite (``python -m unittest discover -s tests``) on
    three Python versions for every push.
  - publish.yml builds and publishes to PyPI with **Trusted Publishing** — the
    job holds ``id-token: write`` and no token/password ever appears in the
    file.  It fires on ``v*`` tags and on manual dispatch with an explicit tag,
    so a tag created before the workflow existed can still be published.
    Before anything is uploaded it (1) re-runs the full test suite with the
    same command as test.yml and (2) refuses to build unless the git tag
    equals ``v`` + the package version from pyproject.toml.

The checks are text-level on purpose: the runner consumes the YAML verbatim,
so the bytes that matter are the ones in the file.
"""

import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    path = REPO / rel
    assert path.exists(), f"missing workflow file: {rel}"
    return path.read_text()


class T21CIContracts(unittest.TestCase):
    """T21: the CI contracts — test matrix, trusted publishing without tokens,
    tag/version match, and the suite gate."""

    def test_test_workflow_runs_the_suite_on_three_pythons(self):
        yml = _read(".github/workflows/test.yml")
        self.assertIn("python -m unittest discover -s tests", yml)
        # the supported matrix is exactly 3.10 / 3.11 / 3.12 (requires-python >=3.10)
        self.assertEqual(re.findall(r'"3\.1\d"', yml),
                         ['"3.10"', '"3.11"', '"3.12"'])

    def test_publish_uses_trusted_publishing_and_never_a_token(self):
        yml = _read(".github/workflows/publish.yml")
        self.assertIn("name: publish", yml)
        self.assertIn("pypa/gh-action-pypi-publish", yml)
        self.assertIn("id-token: write", yml)
        for banned in ("password:", "__token__", "PYPI_TOKEN", "pypi_token",
                       "api_token", "secrets.PYPI"):
            self.assertNotIn(banned, yml)

    def test_publish_triggers_on_version_tags_and_manual_dispatch(self):
        yml = _read(".github/workflows/publish.yml")
        self.assertRegex(yml, r'tags:\s*(?:\n\s*-\s*|\s*\[)\s*["\']v\*["\']')
        self.assertIn("workflow_dispatch", yml)
        # the dispatch input is the tag itself (backfill for earlier tags)
        self.assertIn("Tag to publish", yml)

    def test_publish_gates_on_the_full_test_suite(self):
        yml = _read(".github/workflows/publish.yml")
        self.assertIn("python -m unittest discover -s tests", yml)

    def test_publish_refuses_a_tag_that_does_not_match_the_version(self):
        yml = _read(".github/workflows/publish.yml")
        # the comparison reads the version from pyproject.toml and requires v<version>
        self.assertIn("project']['version'", yml)
        self.assertIn('"v$ver"', yml)
        self.assertIn("exit 1", yml)


if __name__ == "__main__":
    unittest.main()
