"""Unit tests for the vertical config loader (P5.1, D-004).

Loads the real vertical configs; uses tmp configs for the error paths.
"""

import importlib
from pathlib import Path

import pytest

import vja.verticals as verticals_module
from vja.scope import in_scope
from vja.verticals import ConfigError, load_vertical_config


def test_loads_real_grid_config() -> None:
    cfg = load_vertical_config("grid_power_software")
    assert cfg.key == "grid_power_software"
    assert cfg.user_email == "haydenham10@gmail.com"
    assert "Hayden" in cfg.resume_text  # resume path resolved + read
    assert cfg.domain_vocabulary  # non-empty
    assert "software" in cfg.scope.role_include
    assert "senior" in cfg.scope.exclude
    assert cfg.prefilter_locations == ("US",)
    assert "new_grad" in cfg.prefilter_levels


def test_loads_real_aviation_config() -> None:
    """Phase 7 (D-004): aviation loads through the same loader as grid — config only, no code."""
    cfg = load_vertical_config("aviation_software")
    assert cfg.key == "aviation_software"
    assert cfg.user_email == "haydenham10@gmail.com"
    assert "Hayden" in cfg.resume_text  # aviation résumé path resolved + read
    assert "Flight Delay" in cfg.resume_text  # the aviation-tilted project is present
    assert cfg.domain_vocabulary  # non-empty
    assert "software" in cfg.scope.role_include
    assert "pilot" in cfg.scope.exclude  # aviation-specific non-software exclusion
    assert cfg.prefilter_locations == ("US",)
    assert "new_grad" in cfg.prefilter_levels


def test_loads_real_robotics_config() -> None:
    """D-004: Robotics stands up through config + seed/profile data, not application code."""
    cfg = load_vertical_config("robotics_software")
    assert cfg.key == "robotics_software"
    assert cfg.user_email == "haydenham10@gmail.com"
    assert "Hayden" in cfg.resume_text
    assert "Robotics & Autonomous Systems" in cfg.resume_text
    assert "ROS / ROS 2" in cfg.domain_vocabulary
    assert "robotics" in cfg.scope.role_include
    assert "firmware" in cfg.scope.role_include
    assert "technician" in cfg.scope.exclude
    assert cfg.prefilter_locations == ("US",)
    assert "new_grad" in cfg.prefilter_levels


def test_loads_real_trading_config() -> None:
    """D-097: Trading is the fourth config-only vertical add — same loader, no code change."""
    cfg = load_vertical_config("trading_software")
    assert cfg.key == "trading_software"
    assert cfg.user_email == "haydenham10@gmail.com"
    assert "Hayden" in cfg.resume_text
    assert "Quantitative Trading & Market Microstructure" in cfg.resume_text
    assert "market microstructure" in cfg.domain_vocabulary
    assert "quantitative" in cfg.scope.role_include
    assert "trading" in cfg.scope.role_include
    assert "compliance" in cfg.scope.exclude  # trading-specific non-software exclusion
    assert "experienced" in cfg.scope.exclude  # the "Experienced Hire" non-campus track
    assert cfg.prefilter_locations == ("US",)
    assert "new_grad" in cfg.prefilter_levels


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Quantitative Trader - New Grad", True),  # `trader` is deliberately in scope (D-097)
        ("Quantitative Researcher", True),
        ("Software Engineer, Core Trading Systems", True),
        # HRT's only public board is a campus/talent-community pool: the two placeholder entries
        # carry no role keyword, so Stage A drops them without a per-employer rule (D-097).
        ("HRT Talent Community", False),
        ("Campus Talent Community", False),
        ("FPGA Verification and Developer (Internships and Campus Full-time)", True),
        ("Sales Trader", False),  # excluded despite `trader`
        ("Compliance Analyst", False),
        ("Senior Software Engineer", False),
        # "Experienced Hire" is the industry's own label for the non-campus track
        ("Quantitative Researcher | Experienced Hire", False),
        ("C++ Developer | Trading Strategies | Experienced Hire", False),
    ],
)
def test_real_trading_scope_gate(title: str, expected: bool) -> None:
    """The trading Stage-A gate over real board titles — config only, no code path of its own."""
    assert in_scope(title, load_vertical_config("trading_software").scope) is expected


def _write(dir_: Path, key: str, body: str, *, resume: str | None = "r.md") -> None:
    (dir_ / f"{key}.yaml").write_text(body)
    if resume is not None:
        (dir_ / resume).write_text("resume text")


def test_missing_config_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no vertical config"):
        load_vertical_config("nope", config_dir=tmp_path)


_GOOD = """\
key: {key}
matching_profile: {{user_email: a, resume: {resume}}}
scope: {{role_include: [engineer]}}
"""


def test_key_mismatch_raises(tmp_path: Path) -> None:
    _write(tmp_path, "x", _GOOD.format(key="not_x", resume="r.md"))
    with pytest.raises(ConfigError, match="`key` must equal"):
        load_vertical_config("x", config_dir=tmp_path)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    _write(tmp_path, "x", "key: x\nmatching_profile: {user_email: a, resume: r.md}\n")  # no scope
    with pytest.raises(ConfigError, match="missing required field 'scope'"):
        load_vertical_config("x", config_dir=tmp_path)


def test_missing_resume_file_raises(tmp_path: Path) -> None:
    _write(tmp_path, "x", _GOOD.format(key="x", resume="missing.md"), resume=None)
    with pytest.raises(ConfigError, match="resume file not found"):
        load_vertical_config("x", config_dir=tmp_path)


def test_config_dir_honors_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`VJA_VERTICALS_DIR` overrides the repo-relative default.

    Regression for the container bug: the non-editable install moved `vja` into site-packages, so
    the `parents[2]` default resolved to a path with no configs and `available_verticals()` returned
    `[]` — silently skipping the nightly's Layer-2 pass. The env override is how the image points at
    the copied `/app/config/verticals`. Reload the module so the module-level `_CONFIG_DIR` re-reads
    the env (it is evaluated at import).
    """
    _write(tmp_path, "grid_power_software", _GOOD.format(key="grid_power_software", resume="r.md"))
    monkeypatch.setenv("VJA_VERTICALS_DIR", str(tmp_path))
    reloaded = importlib.reload(verticals_module)
    try:
        assert tmp_path == reloaded._CONFIG_DIR
        assert reloaded.available_verticals() == ["grid_power_software"]
    finally:
        # Restore the real module (default path) so later tests see the repo configs.
        monkeypatch.delenv("VJA_VERTICALS_DIR", raising=False)
        importlib.reload(verticals_module)
