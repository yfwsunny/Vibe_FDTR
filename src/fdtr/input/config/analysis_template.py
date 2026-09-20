"""Build flat analysis TOML configs (sensitivity / uncertainty).

Unlike FitConfig TOML, analysis TOMLs are *flat*: all keys live at the
top level.  They reference a ``base_config`` path and contain only the
overrides and analysis-specific fields needed for the analysis run.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fdtr.input.config._toml_utils import fmt, fmt_list, parse_ranges


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_analysis_from_args(args: argparse.Namespace) -> dict:
    """Convert an argparse namespace (analysis mode) into a flat TOML dict.

    The caller is responsible for checking that ``args.analysis`` is not
    ``"none"`` before calling this function.
    """
    analysis = args.analysis
    d: dict = {}

    base_config = getattr(args, "base_config", None)
    if base_config is not None:
        d["base_config"] = str(Path(base_config).resolve())

    strategy = getattr(args, "strategy", None)
    if strategy is not None:
        d["strategy"] = strategy
    elif "base_config" in d:
        from fdtr.input.config import from_toml
        base_cfg = from_toml(d["base_config"])
        d["strategy"] = base_cfg.strategy

    signal = getattr(args, "signal", None)
    if signal is not None:
        d["signal"] = signal

    _maybe_ranges(d, args, "freq_range", "freq_ranges")
    _maybe_ranges(d, args, "offset_range", "offset_ranges")

    phase_points = getattr(args, "phase_points", None)
    if phase_points is not None:
        d["phase_points"] = phase_points

    offset_points = getattr(args, "offset_points", None)
    if offset_points is not None:
        d["offset_points"] = offset_points

    if analysis == "sensitivity":
        _apply_sensitivity_fields(d, args)

    if analysis == "uncertainty":
        _apply_uncertainty_fields(d, args)

    return d


def analysis_dict_to_toml_string(d: dict) -> str:
    """Render a flat analysis dict to a TOML string."""
    lines: list[str] = []

    if "base_config" in d:
        lines.append(f'base_config = {fmt(d["base_config"])}')
        lines.append("")

    if "strategy" in d:
        lines.append(f'strategy = {fmt(d["strategy"])}')

    if "signal" in d:
        lines.append(f'signal = {fmt(d["signal"])}')

    for key in ("freq_ranges", "offset_ranges"):
        if key in d:
            ranges_str = ", ".join(
                f"[{fmt(r[0])}, {fmt(r[1])}]" for r in d[key]
            )
            unit = "Hz" if key == "freq_ranges" else "um"
            lines.append(f"{key} = [{ranges_str}]  # {unit}")

    for key in ("phase_points", "offset_points"):
        if key in d:
            lines.append(f"{key} = {fmt(d[key])}")

    if "output_dir" in d:
        lines.append(f'output_dir = {fmt(d["output_dir"])}')

    if "parameters" in d:
        lines.append(f"parameters = {fmt_list(d['parameters'])}")
    if "delta" in d:
        lines.append(f"delta = {fmt(d['delta'])}")

    for key in ("fit_result",):
        if key in d:
            lines.append(f'{key} = {fmt(d[key])}')
    if "target_params" in d:
        lines.append(f"target_params = {fmt_list(d['target_params'])}")
    if "known_params" in d:
        items = ", ".join(
            f"{k} = {fmt(v)}" for k, v in d["known_params"].items()
        )
        lines.append(f"known_params = {{{items}}}")
    if "full_output" in d:
        lines.append(f"full_output = {fmt(d['full_output'])}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _maybe_ranges(
    d: dict,
    args: argparse.Namespace,
    arg_key: str,
    multi_key: str,
) -> None:
    val = getattr(args, arg_key, None)
    parsed = parse_ranges(val)
    if parsed is not None:
        d[multi_key] = parsed


def _apply_sensitivity_fields(d: dict, args: argparse.Namespace) -> None:
    parameters = getattr(args, "parameters", None)
    if parameters is not None:
        d["parameters"] = [p.strip() for entry in parameters for p in entry.split(",")]

    delta = getattr(args, "delta", None)
    if delta is not None:
        d["delta"] = delta


def _apply_uncertainty_fields(d: dict, args: argparse.Namespace) -> None:
    fit_result = getattr(args, "fit_result", None)
    if fit_result is not None:
        d["fit_result"] = str(Path(fit_result).resolve())

    target_params = getattr(args, "target_params", None)
    if target_params is not None:
        d["target_params"] = target_params
    elif fit_result is not None:
        d["target_params"] = _infer_target_params_from_fit_result(fit_result)
    elif "base_config" in d:
        d["target_params"] = _infer_target_params_from_base_config(d["base_config"])

    if not d.get("target_params"):
        raise ValueError(
            "uncertainty target_params is empty; provide --target-params, "
            "--fit-result, or fit_* targets in --base-config."
        )

    known_params_raw = getattr(args, "known_param", None)
    if known_params_raw:
        known_params = {}
        for item in known_params_raw:
            k, v = item.split("=", 1)
            known_params[k.strip()] = float(v.strip())
        d["known_params"] = known_params

    full_output = getattr(args, "full_output", None)
    if full_output is not None:
        d["full_output"] = full_output


def _infer_target_params_from_fit_result(fit_result_path: str) -> list[str]:
    """Read fitted parameter names from a fit-result JSON."""
    import json

    try:
        with open(fit_result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    fitted = data.get("fitted_values") or data.get("optimal_params", {})
    if fitted:
        return list(fitted.keys())

    # iterfit: read final_values
    final = data.get("final_values", {})
    return list(final.keys())


def _infer_target_params_from_base_config(base_config_path: str) -> list[str]:
    """Read target names from fit_* declarations in a base config."""
    from fdtr.input.config import from_toml, to_fit_targets

    cfg = from_toml(base_config_path)
    return [target.name for target in to_fit_targets(cfg)]
