#!/usr/bin/env python3
"""Shared configuration helpers for benchmark runners and reports."""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_CONFIG = Path(__file__).with_name("benchmark_config.json")


class ConfigError(RuntimeError):
    pass


class PartialFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def load_config(path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    config_path = Path(path or os.environ.get("RPQBENCH_CONFIG", DEFAULT_CONFIG)).expanduser().resolve()
    try:
        with config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot load config {config_path}: {error}") from error

    if config.get("version") != 1:
        raise ConfigError(f"unsupported config version in {config_path}")
    for key in ("defaults", "semantics", "datasets", "competitors"):
        if not isinstance(config.get(key), dict):
            raise ConfigError(f"config field '{key}' must be an object")
    return config, config_path


def format_template(value: Any, context: Mapping[str, Any], *, strict: bool = True) -> str:
    text = str(value)
    rendered = text
    for _ in range(len(context) + 2):
        try:
            next_value = rendered.format_map(context if strict else PartialFormatDict(context))
        except KeyError as error:
            raise ConfigError(f"unknown template variable {error.args[0]!r} in {text!r}") from error
        if next_value == rendered:
            break
        rendered = next_value
    if strict:
        unresolved = re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", rendered)
        if unresolved:
            raise ConfigError(f"unresolved template variable {unresolved.group(0)} in {text!r}")
    return rendered


def _env_name(key: str) -> str:
    return "RPQBENCH_" + re.sub(r"[^A-Za-z0-9]", "_", key).upper()


def parse_overrides(values: Iterable[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ConfigError(f"override must have NAME=VALUE form: {value!r}")
        key, override = value.split("=", 1)
        if not key:
            raise ConfigError(f"override name is empty: {value!r}")
        overrides[key] = override
    return overrides


def build_context(
    config: Mapping[str, Any],
    dataset_name: str,
    root: Path,
    *,
    runs: int | None = None,
    warmup_runs: int | None = None,
    overrides: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    try:
        dataset = config["datasets"][dataset_name]
    except KeyError as error:
        available = ", ".join(config["datasets"])
        raise ConfigError(f"unknown dataset {dataset_name!r}; available: {available}") from error

    defaults = config["defaults"]
    context: dict[str, Any] = {
        "root": str(root.resolve()),
        "dataset": dataset_name,
        "runs": runs if runs is not None else int(os.environ.get("RPQBENCH_RUNS", defaults.get("runs", 1))),
        "warmup_runs": (
            warmup_runs
            if warmup_runs is not None
            else int(os.environ.get("RPQBENCH_WARMUP_RUNS", defaults.get("warmup_runs", 0)))
        ),
        "n_predicates": int(
            os.environ.get(
                "RPQBENCH_N_PREDICATES",
                os.environ.get("RPQBENCH_N_PREDS", dataset.get("n_predicates", 0)),
            )
        ),
        "n_triples": int(os.environ.get("RPQBENCH_N_TRIPLES", dataset.get("n_triples", 0))),
    }
    if context["runs"] < 1:
        raise ConfigError("runs must be a positive integer")
    if context["warmup_runs"] < 0:
        raise ConfigError("warmup_runs must be a non-negative integer")
    context["total_runs"] = context["runs"] + context["warmup_runs"]

    shared_variables = config.get("variables", {})
    variables = dataset.get("variables", {})
    if not isinstance(shared_variables, dict):
        raise ConfigError("config field 'variables' must be an object")
    if not isinstance(variables, dict):
        raise ConfigError(f"dataset {dataset_name!r} variables must be an object")
    for key, value in {**shared_variables, **variables}.items():
        context[key] = os.environ.get(_env_name(key), value)
    context.update(overrides or {})

    # Dataset variables may reference each other. Preserve runtime placeholders
    # such as semantic and query_set until a concrete benchmark is selected.
    for _ in range(len(context) + 1):
        changed = False
        for key, value in list(context.items()):
            if not isinstance(value, str):
                continue
            rendered = format_template(value, context, strict=False)
            if rendered != value:
                context[key] = rendered
                changed = True
        if not changed:
            break

    return context, dataset


def semantic_names(config: Mapping[str, Any], selector: str) -> list[str]:
    semantics = config["semantics"]
    if selector in ("", "all"):
        return list(semantics)
    if selector in semantics:
        return [selector]
    for name, aliases in semantics.items():
        if selector in aliases:
            return [name]
    choices = ", ".join(semantics)
    raise ConfigError(f"unknown semantic {selector!r}; use all or one of: {choices}")


def natural_key(value: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def discover_query_sets(catalog_template: str) -> list[str]:
    token = "{query_set}"
    if catalog_template.count(token) != 1:
        raise ConfigError("query_catalog must contain exactly one {query_set} placeholder")
    prefix, suffix = catalog_template.split(token)
    pattern = re.compile("^" + re.escape(prefix) + "(.+?)" + re.escape(suffix) + "$")
    values = []
    for path in glob.glob(prefix + "*" + suffix):
        match = pattern.match(path)
        if match:
            values.append(match.group(1))
    return sorted(set(values), key=natural_key)


def selected_competitors(
    config: Mapping[str, Any], dataset: Mapping[str, Any], selectors: Iterable[str]
) -> list[tuple[str, Mapping[str, Any]]]:
    requested: list[str] = []
    for selector in selectors:
        requested.extend(part for part in selector.split(",") if part)
    if not requested or "all" in requested:
        requested = list(dataset.get("competitors", config["competitors"].keys()))

    selected = []
    for name in dict.fromkeys(requested):
        try:
            selected.append((name, config["competitors"][name]))
        except KeyError as error:
            available = ", ".join(config["competitors"])
            raise ConfigError(f"unknown competitor {name!r}; available: {available}") from error
    return selected


def repository_root(config_path: Path, explicit_root: str | None = None) -> Path:
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()
    if config_path.parent.name == "Scripts":
        return config_path.parent.parent.resolve()
    return Path(__file__).resolve().parents[1]
