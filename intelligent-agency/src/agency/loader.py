"""Build the whole hierarchy from a YAML config file.

The config is the single place you edit to add a new field (director) or a
new specialist (agent) -- no code changes required.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from .agent import Agent
from .director import Director
from .president import President

_DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config", "agency.yaml",
)


def load_config(path: str = _DEFAULT_CONFIG) -> Dict[str, Any]:
    import yaml
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_agency(path: str = _DEFAULT_CONFIG) -> President:
    """Construct a fully wired President from the config file."""
    cfg = load_config(path)
    pres_cfg = cfg.get("president", {})
    president = President(
        name=pres_cfg.get("name", "President"),
        description=pres_cfg.get("description", "Oversees all directors."),
    )

    for d in cfg.get("directors", []):
        director = Director(
            name=d["name"],
            description=d.get("description", ""),
            keywords=d.get("keywords", []),
            system_prompt=d.get("system_prompt", ""),
        )
        for a in d.get("agents", []):
            director.add_agent(Agent(
                name=a["name"],
                description=a.get("description", ""),
                keywords=a.get("keywords", []),
                system_prompt=a.get("system_prompt", ""),
            ))
        president.add_director(director)

    return president
