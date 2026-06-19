"""Unit tests for the Stage-B pre-filter (P5.3) — pure, deterministic, no LLM.

Pins the gate's shape: concrete out-of-range levels and clearly-foreign locations drop; unknown/
null fields and US signals pass; the level set is config-driven and the gate is coarse by design.
"""

from vja.prefilter import PrefilterConfig, passes_prefilter

_CFG = PrefilterConfig(locations=("US",), levels=("intern", "new_grad", "early_career"))


def test_early_career_us_passes() -> None:
    assert passes_prefilter("new_grad", "Houston, TX", _CFG)
    assert passes_prefilter("intern", "Boston, MA", _CFG)


def test_senior_and_mid_drop() -> None:
    assert not passes_prefilter("senior", "Houston, TX", _CFG)
    assert not passes_prefilter("mid", "Austin, TX", _CFG)


def test_unknown_level_passes() -> None:
    # Coarse gate: it never *requires* a confirmed level — only drops a confirmed out-of-range one.
    assert passes_prefilter("unknown", "Houston, TX", _CFG)
    assert passes_prefilter(None, "Houston, TX", _CFG)


def test_null_or_remote_location_passes() -> None:
    assert passes_prefilter("new_grad", None, _CFG)
    assert passes_prefilter("new_grad", "Remote - US", _CFG)
    assert passes_prefilter("new_grad", "Remote", _CFG)


def test_us_signal_variants_pass() -> None:
    for loc in ("United States", "New York, NY", "Denver, Colorado", "USA"):
        assert passes_prefilter("new_grad", loc, _CFG), loc


def test_clearly_foreign_location_drops() -> None:
    for loc in ("London, United Kingdom", "Bengaluru, India", "Toronto, Canada"):
        assert not passes_prefilter("new_grad", loc, _CFG), loc


def test_level_set_is_config_driven() -> None:
    # A config that allows `mid` keeps a mid-level posting that the default config drops.
    permissive = PrefilterConfig(locations=("US",), levels=("new_grad", "mid"))
    assert passes_prefilter("mid", "Houston, TX", permissive)
    assert not passes_prefilter("senior", "Houston, TX", permissive)
