"""Vertical config loader — "a vertical is config" (D-004, docs/06).

A vertical = the employer rows in the seed CSV (filtered by `key`) + this YAML: the matching profile
(resume + domain vocabulary), the Stage-A `scope` keyword lists, and the Stage-B `prefilter` knobs.
Nothing vertical-specific lives in code; adding a vertical is a new YAML + resume + seed rows.

`vja-load-profiles` reads every `config/verticals/*.yaml` and upserts its matching profile.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from vja.db.engine import get_engine
from vja.db.profiles import upsert_profile
from vja.scope import ScopeConfig

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "verticals"


class ConfigError(Exception):
    """A vertical config file is missing or malformed (a config defect, not a runtime error)."""


@dataclass(frozen=True)
class VerticalConfig:
    key: str
    user_email: str
    resume_text: str
    domain_vocabulary: tuple[str, ...]
    scope: ScopeConfig
    prefilter_locations: tuple[str, ...]
    prefilter_levels: tuple[str, ...]


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise ConfigError(f"vertical config missing required field {key!r} in {where}")
    return mapping[key]


def load_vertical_config(key: str, *, config_dir: Path = _CONFIG_DIR) -> VerticalConfig:
    """Load and validate `config/verticals/<key>.yaml` into a `VerticalConfig`."""
    path = config_dir / f"{key}.yaml"
    if not path.exists():
        raise ConfigError(f"no vertical config at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"vertical config {path} is not a mapping")
    if data.get("key") != key:
        raise ConfigError(f"vertical config {path}: `key` must equal {key!r}")

    profile = _require(data, "matching_profile", key)
    scope = _require(data, "scope", key)
    prefilter = data.get("prefilter") or {}

    resume_rel = _require(profile, "resume", "matching_profile")
    resume_path = (config_dir / resume_rel).resolve()
    if not resume_path.exists():
        raise ConfigError(f"resume file not found: {resume_path}")

    return VerticalConfig(
        key=key,
        user_email=_require(profile, "user_email", "matching_profile"),
        resume_text=resume_path.read_text(encoding="utf-8"),
        domain_vocabulary=tuple(profile.get("domain_vocabulary") or ()),
        scope=ScopeConfig(
            role_include=tuple(_require(scope, "role_include", "scope")),
            exclude=tuple(scope.get("exclude") or ()),
        ),
        prefilter_locations=tuple(prefilter.get("locations") or ()),
        prefilter_levels=tuple(prefilter.get("levels") or ()),
    )


def available_verticals(config_dir: Path = _CONFIG_DIR) -> list[str]:
    """The vertical keys with a config file (the YAML stem), sorted."""
    return sorted(p.stem for p in config_dir.glob("*.yaml"))


def load_profiles_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-load-profiles` — upsert the matching profile for every configured vertical."""
    engine = get_engine()
    keys = available_verticals()
    if not keys:
        print(f"no vertical configs found in {_CONFIG_DIR}", file=sys.stderr)
        return 0
    for key in keys:
        cfg = load_vertical_config(key)
        profile_id = upsert_profile(
            engine,
            user_email=cfg.user_email,
            vertical=cfg.key,
            resume_text=cfg.resume_text,
            domain_vocabulary=cfg.domain_vocabulary,
        )
        print(f"[{cfg.key}] profile {profile_id} active for {cfg.user_email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(load_profiles_main())
