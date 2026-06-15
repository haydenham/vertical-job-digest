"""Smoke test: the package imports and the toolchain is wired.

Replaced by real unit tests as Chunk 2+ land; for now it just proves
`pytest` is green off a clean scaffold.
"""

import vja


def test_package_imports_and_has_version() -> None:
    assert vja.__version__ == "0.0.1"
