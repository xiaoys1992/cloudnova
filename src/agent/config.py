"""Load config.yaml (agent section) + path resolution with env overrides.

No business constants or column names live here or anywhere in agent code;
they come from the cleaned schema.json and specs/metrics_spec.md at runtime.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTS = {
    "model": "claude-sonnet-5-5",
    "max_rows": 1000,
    "query_timeout_s": 10,
    "few_shots_path": "src/agent/few_shots.yaml",
}


@dataclass(frozen=True)
class Config:
    model: str
    max_rows: int
    query_timeout_s: int
    few_shots_path: Path
    clean_dir: Path
    metrics_spec_path: Path

    @property
    def parquet_path(self) -> Path:
        return self.clean_dir / "cleaned.parquet"

    @property
    def schema_path(self) -> Path:
        return self.clean_dir / "schema.json"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as fh:
        return yaml.safe_load(fh) or {}


def load_config(config_path: Path | None = None) -> Config:
    """Read config.yaml; CLEAN_DIR env var overrides paths.clean_dir."""
    cfg = _load_yaml(config_path or (REPO_ROOT / "config.yaml"))
    agent = {**_DEFAULTS, **(cfg.get("agent") or {})}
    paths = cfg.get("paths") or {}

    clean_dir = os.getenv("CLEAN_DIR") or paths.get("clean_dir", "data/clean")
    clean_dir_path = Path(clean_dir)
    if not clean_dir_path.is_absolute():
        clean_dir_path = REPO_ROOT / clean_dir_path

    few_shots = Path(agent["few_shots_path"])
    if not few_shots.is_absolute():
        few_shots = REPO_ROOT / few_shots

    return Config(
        model=str(agent["model"]),
        max_rows=int(agent["max_rows"]),
        query_timeout_s=int(agent["query_timeout_s"]),
        few_shots_path=few_shots,
        clean_dir=clean_dir_path,
        metrics_spec_path=REPO_ROOT / "specs" / "metrics_spec.md",
    )
