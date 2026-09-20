"""Cross-analysis summary report generator.

Scans a task directory for FDTR artifacts (fit results, sensitivity CSVs,
uncertainty JSONs, plots, configs) and assembles a unified Markdown report.
"""
from __future__ import annotations

import csv
import json
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from fdtr.input.config import collect_all_target_names, from_toml


@dataclass
class ScannedArtifacts:
    fit_results: list[Path] = field(default_factory=list)
    plots: list[Path] = field(default_factory=list)
    sensitivity_csvs: list[Path] = field(default_factory=list)
    sensitivity_plots: list[Path] = field(default_factory=list)
    uncertainty_results: list[Path] = field(default_factory=list)
    uncertainty_configs: list[Path] = field(default_factory=list)
    configs: list[Path] = field(default_factory=list)


def _fmt(v: float) -> str:
    if v == 0.0:
        return "0"
    if abs(v) >= 1e6 or abs(v) < 0.01:
        return f"{v:.3e}"
    if abs(v) < 1.0:
        return f"{v:.4f}"
    return f"{v:.4g}"


def _get_unit(name: str) -> str:
    if name in ("spot_size", "spot_x", "spot_y"):
        return "um"
    if name.startswith("TBC"):
        return "W/m²K"
    if name.startswith("rho_cp"):
        return "J/m³K"
    if name.startswith("d_"):
        return "m"
    return "W/mK"


def organize_files(task_dir: Path) -> None:
    """Move artifacts into inputs/ and results/ subdirectories."""
    inputs_dir = task_dir / "inputs"
    results_dir = task_dir / "results"
    inputs_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)

    inputs_patterns = ["config_*.toml", "scan_*.json", "scan_data_*.json", "scan_group_*.json", "scan_data_index.json"]
    for pat in inputs_patterns:
        for f in task_dir.glob(pat):
            f.rename(inputs_dir / f.name)

    results_patterns = [
        "*fit_*.png", "*_sensitivity.png",
        "*fit_*.csv", "*_sensitivity.csv",
        "fit_result_*.json", "uncertainty_result*.json",
    ]
    for pat in results_patterns:
        for f in task_dir.glob(pat):
            f.rename(results_dir / f.name)


class SummaryGenerator:
    """Scan a task directory and generate a unified Markdown report."""

    def __init__(self, task_dir: Path) -> None:
        self._task_dir = Path(task_dir).resolve()
        self._artifacts = ScannedArtifacts()

    def scan(self) -> ScannedArtifacts:
        """Scan task_dir (and inputs/results subdirs if present) for artifacts."""
        search_dirs = [self._task_dir]
        for sub in ("inputs", "results"):
            p = self._task_dir / sub
            if p.is_dir():
                search_dirs.append(p)

        for d in search_dirs:
            self._artifacts.fit_results.extend(sorted(d.glob("fit_result_*.json")))
            self._artifacts.plots.extend(sorted(d.glob("*fit_*.png")))
            self._artifacts.sensitivity_csvs.extend(sorted(d.glob("*_sensitivity.csv")))
            self._artifacts.sensitivity_plots.extend(sorted(d.glob("*_sensitivity.png")))
            self._artifacts.uncertainty_results.extend(sorted(d.glob("uncertainty_result*.json")))
            self._artifacts.uncertainty_configs.extend(sorted(d.glob("uncertainty*.toml")))
            self._artifacts.configs.extend(sorted(d.glob("config_*.toml")))

        # Deduplicate (same file found in task_dir and results/)
        for attr in ("fit_results", "plots", "sensitivity_csvs", "sensitivity_plots",
                     "uncertainty_results", "uncertainty_configs", "configs"):
            seen = set()
            unique = []
            for p in getattr(self._artifacts, attr):
                if p.name not in seen:
                    seen.add(p.name)
                    unique.append(p)
            setattr(self._artifacts, attr, unique)

        return self._artifacts

    def generate(self) -> str:
        sections = [
            self._build_header(),
            self._build_config_section(),
            self._build_fit_results(),
            self._build_fit_plots(),
            self._build_uncertainty_section(),
            self._build_sensitivity_section(),
        ]
        return "\n\n".join(s for s in sections if s) + "\n"

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.generate(), encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_header(self) -> str:
        return (
            "# FDTR Analysis Summary\n\n"
            f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"**Directory**: `{self._task_dir}`"
        )

    def _build_config_section(self) -> str:
        if not self._artifacts.configs:
            return ""
        config_path = self._artifacts.configs[0]
        try:
            raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return ""

        lines = ["## Configuration"]

        # Layer stack
        layers = raw.get("layer", [])
        if layers:
            lines.append("\n### Layer Stack\n")
            lines.append("| # | Name | rho_cp (J/m³K) | Sr (W/mK) | Sz (W/mK) | d (m) |")
            lines.append("|---|------|----------------|-----------|-----------|-------|")
            try:
                fit_targets = collect_all_target_names(from_toml(config_path))
            except Exception:
                fit = raw.get("fit", {})
                fit_targets = {t["name"] for t in fit.get("targets", [])}
            for i, layer in enumerate(layers):
                name = layer.get("material") or layer.get("name", "")
                rho_cp = layer.get("rho_cp", 0.0)
                if "S" in layer:
                    sr = layer["S"]
                    sz = layer["S"]
                else:
                    sr = layer.get("Sr", 1.0)
                    sz = layer.get("Sz", 1.0)
                d = layer.get("d", 1.0)
                rho_cell = f"**{_fmt(rho_cp)}**" if f"rho_cp_{i}" in fit_targets else _fmt(rho_cp)
                if "S" in layer:
                    sr_cell = f"**{_fmt(sr)}**" if f"S_{i}" in fit_targets else _fmt(sr)
                    sz_cell = f"**{_fmt(sz)}**" if f"S_{i}" in fit_targets else _fmt(sz)
                else:
                    sr_cell = f"**{_fmt(sr)}**" if f"Sr_{i}" in fit_targets else _fmt(sr)
                    sz_cell = f"**{_fmt(sz)}**" if f"Sz_{i}" in fit_targets else _fmt(sz)
                d_cell = f"**{_fmt(d)}**" if f"d_{i}" in fit_targets else _fmt(d)
                lines.append(f"| {i} | {name} | {rho_cell} | {sr_cell} | {sz_cell} | {d_cell} |")

        # Fit settings
        fit = raw.get("fit", {})
        if fit:
            lines.append("\n### Fit Settings\n")
            lines.append("| Setting | Value |")
            lines.append("|---------|-------|")
            for key in ("strategy", "spot_size", "freq_spot", "freq_offset", "offset_points", "phase_points", "average", "signal"):
                val = fit.get(key)
                if val is not None:
                    lines.append(f"| {key} | {val} |")
            for range_key in ("freq_ranges", "offset_ranges"):
                val = fit.get(range_key)
                if val is not None:
                    lines.append(f"| {range_key} | {val} |")

        return "\n".join(lines)

    def _build_fit_results(self) -> str:
        if not self._artifacts.fit_results:
            return ""

        from fdtr.output.result_io import load_result
        lines = ["## Fit Results"]

        for fr_path in self._artifacts.fit_results:
            try:
                result = load_result(fr_path)
            except Exception:
                continue

            is_iter = hasattr(result, "history") and hasattr(result, "final_values")

            if is_iter:
                fitted = result.final_values
                success = result.success
                residual = result.step_results[-1][-1].residual if result.step_results else float("nan")
                n_iterations = result.n_iterations
            else:
                fitted = result.fitted_values
                success = result.success
                residual = result.residual
                n_iterations = None

            # Load uncertainty for merging
            unc_data = self._load_uncertainty_data()
            rel_unc = unc_data.get("relative_uncertainties") or unc_data.get("iterfit_uncertainty", {})

            # Fitted values + uncertainty table
            lines.append("\n### Fitted Values + Uncertainty\n")
            lines.append("| Parameter | Value | Unit | Rel. Unc. (%) |")
            lines.append("|-----------|-------|------|---------------|")
            for name, value in fitted.items():
                unit = _get_unit(name)
                unc_str = f"{rel_unc.get(name, 0) * 100:.2f}" if name in rel_unc else "-"
                lines.append(f"| {name} | {_fmt(value)} | {unit} | {unc_str} |")

            # Iteration history
            if is_iter and result.history:
                all_keys: list[str] = []
                seen: set[str] = set()
                for step in result.history:
                    for k in step:
                        if k not in seen:
                            all_keys.append(k)
                            seen.add(k)

                lines.append("\n### Iteration History\n")
                lines.append("| Iter | " + " | ".join(all_keys) + " | Residual |")
                lines.append("|------|" + "|".join(["------"] * (len(all_keys) + 1)) + "|")
                for i, step in enumerate(result.history):
                    vals = []
                    for k in all_keys:
                        v = step.get(k)
                        vals.append(_fmt(v) if v is not None else "-")
                    if i < len(result.step_results) and result.step_results[i]:
                        res = result.step_results[i][-1].residual
                    else:
                        res = float("nan")
                    vals.append(_fmt(res))
                    lines.append(f"| {i + 1} | " + " | ".join(vals) + " |")

            # Convergence
            lines.append("\n### Convergence\n")
            lines.append(f"**Converged**: {'Yes' if success else 'No'}")
            lines.append(f"**Residual**: {_fmt(residual)}")
            if n_iterations is not None:
                lines.append(f"**Iterations**: {n_iterations}")

        return "\n".join(lines)

    def _build_fit_plots(self) -> str:
        if not self._artifacts.plots:
            return ""
        lines = ["## Fit Plots", ""]
        for p in self._artifacts.plots:
            rel = self._relative_path(p)
            lines.append(f"![{p.stem}]({rel})")
            lines.append("")
        return "\n".join(lines).rstrip()

    def _build_uncertainty_section(self) -> str:
        unc_data = self._load_uncertainty_data()
        if not unc_data:
            return ""

        lines = ["## Uncertainty Analysis"]

        # Known parameters: from JSON (non-iterfit) or inferred from config (iterfit)
        known = unc_data.get("known_params")
        if not known and "iterfit_uncertainty" in unc_data:
            known = self._infer_known_params_iterfit(
                set(unc_data["iterfit_uncertainty"].keys()),
            )
        if known:
            lines.append("\n### Known Parameters\n")
            lines.append("| Parameter | Value | Rel. σ | Source |")
            lines.append("|-----------|-------|---------|--------|")
            for param_name, info in known.items():
                if isinstance(info, dict):
                    val = info.get("value", 0)
                    sigma = info.get("uncertainty", 0.05)
                    source = info.get("source", "config" if sigma != 0.05 else "default")
                else:
                    val = info
                    sigma = 0.05
                    source = "default"
                lines.append(f"| {param_name} | {_fmt(val)} | {sigma * 100:.1f}% | {source} |")

        # Parameter contributions (full output only)
        contribs = unc_data.get("parameter_contributions")
        if contribs:
            lines.append("\n### Parameter Contributions\n")
            for target, params in contribs.items():
                lines.append(f"\n**{target}**:")
                sorted_params = sorted(params.items(), key=lambda x: x[1], reverse=True)
                for param, pct in sorted_params:
                    lines.append(f"- {param}: {pct:.2f}%")

        return "\n".join(lines)

    def _build_sensitivity_section(self) -> str:
        if not self._artifacts.sensitivity_csvs:
            return ""

        lines = ["## Sensitivity Analysis"]

        for csv_path in self._artifacts.sensitivity_csvs:
            try:
                with csv_path.open("r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader)
                    rows = list(reader)
            except Exception:
                continue

            if len(header) < 2 or not rows:
                continue

            axis_name = header[0]
            param_names = header[1:]
            axis_values = [float(r[0]) for r in rows]
            curves = {name: [float(r[i + 1]) for r in rows] for i, name in enumerate(param_names)}

            # Ranking by max |S|
            ranking = []
            for name, vals in curves.items():
                abs_vals = [abs(v) for v in vals]
                max_s = max(abs_vals)
                if max_s == 0:
                    continue
                # Sensitive range: where |S| > 50% of max
                threshold = 0.5 * max_s
                above = [(axis_values[i], abs_vals[i]) for i in range(len(abs_vals)) if abs_vals[i] > threshold]
                if above:
                    range_str = f"{_fmt(above[0][0])} – {_fmt(above[-1][0])}"
                else:
                    range_str = "-"
                ranking.append((name, max_s, range_str))

            ranking.sort(key=lambda x: x[1], reverse=True)

            lines.append("\n### Parameter Sensitivity Ranking\n")
            lines.append(f"**Axis**: {axis_name}")
            lines.append("")
            lines.append("| Rank | Parameter | Max |S| | Sensitive Range |")
            lines.append("|------|-----------|---------|-----------------|")
            for i, (name, max_s, range_str) in enumerate(ranking, 1):
                lines.append(f"| {i} | {name} | {max_s:.4f} | {range_str} |")

        # Sensitivity plots
        if self._artifacts.sensitivity_plots:
            lines.append("\n### Sensitivity Curves")
            for p in self._artifacts.sensitivity_plots:
                rel = self._relative_path(p)
                lines.append(f"\n![{p.stem}]({rel})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _relative_path(self, p: Path) -> str:
        """Return path relative to task_dir for Markdown embedding."""
        try:
            return str(p.relative_to(self._task_dir)).replace("\\", "/")
        except ValueError:
            return p.name

    def _load_uncertainty_data(self) -> dict:
        """Load the first uncertainty result JSON, if any."""
        if not self._artifacts.uncertainty_results:
            return {}
        try:
            return json.loads(self._artifacts.uncertainty_results[0].read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _load_first_fit_result_data(self) -> dict | None:
        if not self._artifacts.fit_results:
            return None
        try:
            return json.loads(self._artifacts.fit_results[0].read_text(encoding="utf-8"))
        except Exception:
            return None

    def _load_config_layers(self) -> list[dict]:
        if not self._artifacts.configs:
            return []
        try:
            raw = tomllib.loads(self._artifacts.configs[0].read_text(encoding="utf-8"))
        except Exception:
            return []
        layers = raw.get("layer", [])
        for i, layer in enumerate(layers):
            layer["_index"] = i
        return layers

    def _load_uncertainty_overrides(self) -> dict:
        """Load user-specified known_params overrides from uncertainty config."""
        for cfg_path in self._artifacts.uncertainty_configs:
            try:
                raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            # uncertainty config may have [uncertainty] section or flat structure
            unc = raw.get("uncertainty", raw)
            overrides = unc.get("known_params", {})
            if overrides:
                return overrides
        return {}

    def _infer_known_params_iterfit(self, fitted_targets: set[str]) -> dict:
        """Infer known_params from base config for iterfit uncertainty.

        Same logic as engine: all physical layer params minus fitted targets,
        5% default uncertainty, user overrides from uncertainty config applied.
        """
        _DEFAULT_REL = 0.05
        layers = self._load_config_layers()
        if not layers:
            return {}

        user_overrides = self._load_uncertainty_overrides()

        # Build physical param names + values (same logic as default_parameter_names)
        all_params: dict[str, float] = {}
        for idx, layer in enumerate(layers):
            if layer.get("rho_cp", 1.0) == 0.0:
                # TBC layer
                all_params[f"TBC_{idx}"] = layer.get("Sr", 0.0)
                continue
            if "S" in layer:
                all_params[f"S_{idx}"] = layer.get("S", 0.0)
            else:
                for prop in ("Sr", "Sz"):
                    all_params[f"{prop}_{idx}"] = layer.get(prop, 0.0)
            all_params[f"rho_cp_{idx}"] = layer.get("rho_cp", 0.0)
            d = layer.get("d", 1.0)
            if d != 1.0:
                all_params[f"d_{idx}"] = d

        excluded_targets = set(fitted_targets)
        for target in fitted_targets:
            if target.startswith("S_") and target[2:].isdigit():
                idx = target[2:]
                excluded_targets.add(f"Sr_{idx}")
                excluded_targets.add(f"Sz_{idx}")
        # Exclude fitted targets, build known_params
        known = {}
        for name, val in all_params.items():
            if name in excluded_targets:
                continue
            rel = user_overrides.get(name, _DEFAULT_REL)
            source = "config" if name in user_overrides else "default"
            known[name] = {"value": val, "uncertainty": rel, "source": source}

        return known
