"""CLI command for uncertainty calculation — thin dispatcher."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def load_raw_config(path: str | Path) -> dict:
    """Load raw TOML config as dict (for merge logic)."""
    path = Path(path)
    with path.open("rb") as f:
        return tomllib.load(f)


def _is_flat_analysis_config(path: str | Path) -> bool:
    """Return True if the TOML has a top-level ``base_config`` key."""
    path = Path(path)
    with path.open("rb") as f:
        data = tomllib.load(f)
    return "base_config" in data


def _resolve_uncertainty_output_dir(args, config_dict):
    """Resolve output directory for uncertainty results.

    Priority:
      1. --fit-result given -> use its parent directory
      2. TOML [paths] output_dir -> resolve relative to config
      3. Auto-generate with material names suffix
    """
    from fdtr.output import resolve_output_dir, get_material_names_from_dict

    # Use fit result's parent directory when available
    if getattr(args, "fit_result", None):
        return Path(args.fit_result).resolve().parent

    config_path = Path(args.config) if getattr(args, "config", None) else None

    # Check TOML [paths] output_dir
    if config_dict.get("paths", {}).get("output_dir"):
        return resolve_output_dir(
            config_dict["paths"]["output_dir"],
            config_path=config_path,
            material_names=get_material_names_from_dict(config_dict),
        )

    material_names = get_material_names_from_dict(config_dict)
    return resolve_output_dir(None, config_path=config_path, material_names=material_names)


def _apply_fitted_values(config: dict, fitted_values: dict) -> None:
    """Apply fitted parameter values to config layers and fit settings."""
    from fdtr.analysis.uncertainty.prepare import (
        update_layers_from_params,
        validate_fitted_values_against_layer_schema,
    )

    validate_fitted_values_against_layer_schema(config, fitted_values)
    update_layers_from_params(config.setdefault("layer", []), fitted_values)

    for spot_key in ("spot_size", "spot_x", "spot_y"):
        if spot_key in fitted_values:
            config.setdefault("fit", {})[spot_key] = fitted_values[spot_key]


def _merge_uncertainty(base: dict, override: dict) -> dict:
    """Merge two uncertainty dicts, preserving non-empty target_params."""
    merged = {**base, **override}
    if not override.get("target_params") and base.get("target_params"):
        merged["target_params"] = base["target_params"]
    return merged


def run_uncertainty(args) -> None:
    """Calculate parameter uncertainties for FDTR measurements."""
    from fdtr.input.config import FitConfig
    from fdtr.analysis.uncertainty.run_uncertainty import run_uncertainty as run_engine
    from fdtr.analysis.uncertainty.prepare import load_fit_result
    from fdtr.analysis.uncertainty.engine import run_iterfit_uncertainty
    from fdtr.analysis.uncertainty.output import format_result, save_result
    from fdtr.output.paths import (
        OutputPaths,
        derive_group_slug_from_artifact,
        derive_group_slug_from_config,
    )

    # Determine if flat analysis config
    config_path = getattr(args, "config", None)
    use_flat = config_path and _is_flat_analysis_config(config_path)

    # Load config
    if getattr(args, "fit_result", None):
        # Post-fit mode via --fit-result flag
        base_config, x_data, fitted_values = load_fit_result(args.fit_result)
        is_iterfit = base_config.get("strategy") == "iterfit" or base_config.get("fit", {}).get("strategy") == "iterfit"

        if config_path:
            if use_flat:
                from fdtr.input.config.analysis_config import load_analysis_config
                flat_cfg = load_analysis_config(config_path, "uncertainty")
                if flat_cfg.uncertainty:
                    flat_cfg.uncertainty.fit_result = args.fit_result
                flat_dict = _fitconfig_to_uncertainty_dict(flat_cfg)
                base_config["uncertainty"] = _merge_uncertainty(base_config.get("uncertainty", {}), flat_dict.get("uncertainty", {}))
                base_config.update({k: v for k, v in flat_dict.items() if k != "uncertainty"})
            else:
                user_config = load_raw_config(config_path)
                base_config["uncertainty"] = _merge_uncertainty(base_config.get("uncertainty", {}), user_config.get("uncertainty", {}))
                base_config.update({k: v for k, v in user_config.items() if k != "uncertainty"})
        elif not config_path:
            print("Error: --config is required when using --fit-result.", file=sys.stderr)
            sys.exit(1)

        _apply_fitted_values(base_config, fitted_values)
        config = base_config
    elif config_path:
        if use_flat:
            from fdtr.input.config.analysis_config import load_analysis_config
            cfg = load_analysis_config(config_path, "uncertainty")

            # --fit-result CLI override for flat config
            cli_fit_result = getattr(args, "fit_result", None)
            if cli_fit_result and cfg.uncertainty:
                cfg.uncertainty.fit_result = cli_fit_result

            # Fallback: read fit_result from uncertainty spec
            if cfg.uncertainty and cfg.uncertainty.fit_result:
                fr_path = Path(config_path).resolve().parent / cfg.uncertainty.fit_result
                if fr_path.exists():
                    args.fit_result = str(fr_path)
                    base_config, x_data, fitted_values = load_fit_result(str(fr_path))
                    flat_dict = _fitconfig_to_uncertainty_dict(cfg)
                    base_config["uncertainty"] = _merge_uncertainty(base_config.get("uncertainty", {}), flat_dict.get("uncertainty", {}))
                    base_config.update({k: v for k, v in flat_dict.items() if k != "uncertainty"})
                    _apply_fitted_values(base_config, fitted_values)
                    config = base_config
                else:
                    x_data = None
                    config = _fitconfig_to_uncertainty_dict(cfg)
            else:
                x_data = None
                config = _fitconfig_to_uncertainty_dict(cfg)
        else:
            config = load_raw_config(config_path)
            x_data = None
            # Fallback: read fit_result from TOML [uncertainty] section
            config_fit_result = config.get("uncertainty", {}).get("fit_result")
            if config_fit_result and config_fit_result.strip():
                fr_path = Path(config_path).resolve().parent / config_fit_result
                if fr_path.exists():
                    args.fit_result = str(fr_path)
                    base_config, x_data, fitted_values = load_fit_result(str(fr_path))
                    base_config["uncertainty"] = _merge_uncertainty(base_config.get("uncertainty", {}), config.get("uncertainty", {}))
                    base_config.update({k: v for k, v in config.items() if k != "uncertainty"})
                    _apply_fitted_values(base_config, fitted_values)
                    config = base_config
    else:
        print("Error: Either --config or --fit-result must be provided.", file=sys.stderr)
        sys.exit(1)

    # Resolve output directory
    output_dir = _resolve_uncertainty_output_dir(args, config)

    # Detect iterfit strategy
    strategy = config.get("strategy") or config.get("fit", {}).get("strategy", "")
    group_slug = (
        derive_group_slug_from_config(Path(config_path))
        if config_path
        else derive_group_slug_from_artifact(Path(getattr(args, "fit_result", "")) if getattr(args, "fit_result", None) else None)
    )
    command = {
        "freqfit": "freq",
        "offsetfit": "offset",
        "spotfit": "spot",
        "iterfit": "iter",
    }.get(strategy, "iter")
    paths = OutputPaths(base=output_dir, command=command, suffix=group_slug)

    if strategy == "iterfit":
        sigma_dict, history = run_iterfit_uncertainty(config)

        print("Iterfit Uncertainty (Stepwise Propagation)")
        print("=" * 45)
        for name, rel_unc in sorted(sigma_dict.items()):
            print(f"  {name:20s} = {rel_unc * 100:.2f}%")
        print("=" * 45)

        if output_dir:
            import json as _json
            out_path = str(paths.next_uncertainty_result_path())
            with open(out_path, "w") as f:
                _json.dump({"iterfit_uncertainty": sigma_dict, "history": history}, f, indent=2)
            print(f"\nResult saved to {out_path}")

    else:
        config.setdefault("uncertainty", {})
        cli_full_output = getattr(args, "full_output", None)
        if cli_full_output is not None:
            config["uncertainty"]["full_output"] = cli_full_output
        include_full = bool(config["uncertainty"].get("full_output", False))
        result = run_engine(config, x_data=x_data)
        print(format_result(result))

        if output_dir:
            out_path = str(paths.next_uncertainty_result_path())
            save_result(result, out_path, include_full=include_full)
            print(f"\nResult saved to {out_path}")


def _fitconfig_to_uncertainty_dict(cfg: FitConfig) -> dict:
    """Convert a FitConfig to a raw dict compatible with the uncertainty CLI flow.

    This bridges the gap between the flat-analysis-config loader (which returns
    a FitConfig) and the uncertainty CLI's dict-based merge logic.
    """
    from fdtr.input.config.config_io import _to_toml_string
    import tomllib

    # Serialize FitConfig to TOML string, then parse back to dict
    toml_str = _to_toml_string(cfg, mode="lean")
    return tomllib.loads(toml_str)
