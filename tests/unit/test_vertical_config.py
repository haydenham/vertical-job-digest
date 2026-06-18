"""Unit tests for the vertical config loader (P5.1, D-004).

Loads the real `config/verticals/grid_power_software.yaml`; uses tmp configs for the error paths.
"""

from pathlib import Path

import pytest

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
