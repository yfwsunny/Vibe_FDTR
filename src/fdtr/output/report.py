"""Markdown report generator for FDTR fitting results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from fdtr.input.config import FitConfig, LayerSpec, TargetSpec, collect_all_target_names, resolve_guess
from fdtr.model.layer import SYMMETRY_ISOTROPIC


def _embed_plot(path: Path) -> str:
    """Return a relative path string for a plot image."""
    return path.name


def _fmt(v: float) -> str:
    """Format a float for display in the report."""
    if v == 0.0:
        return "0"
    if abs(v) >= 1e6 or abs(v) < 0.01:
        return f"{v:.3e}"
    if abs(v) < 1.0:
        return f"{v:.4f}"
    return f"{v:.4g}"


class ReportGenerator:
    """Generate a markdown fit report from config + results.

    Args:
        config: The FitConfig used for the fitting run.
        result: The FitResult or IterationResult from the fitter.
        plot_paths: List of paths to plot PNG files (embedded as base64).
    """

    def __init__(
        self,
        config: FitConfig,
        result,
        plot_paths: Optional[Sequence[Path]] = None,
    ) -> None:
        self._config = config
        self._result = result
        self._plot_paths = list(plot_paths) if plot_paths else []
        self._is_iterative = hasattr(result, "history") and hasattr(result, "final_values")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> str:
        """Return the complete markdown report as a string."""
        sections: list[str] = []
        sections.append(self._build_header())
        sections.append(self._build_layer_table())
        sections.append(self._build_config_section())
        if self._is_iterative:
            sections.append(self._build_iteration_history())
        sections.append(self._build_final_results())
        sections.append(self._build_plots())
        return "\n\n".join(sections) + "\n"

    def save(self, path: str | Path) -> Path:
        """Write report to file and return the path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.generate(), encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_header(self) -> str:
        """Build the report header with date, strategy, temperature."""
        lines = [
            "# FDTR Fit Report",
            "",
            f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Strategy**: {self._config.strategy}",
            f"**Temperature**: {_fmt(self._config.temperature)} K",
        ]
        return "\n".join(lines)

    def _build_layer_table(self) -> str:
        """Build layer stack table with fitted params highlighted in bold."""
        fitted_names = collect_all_target_names(self._config)
        compact_isotropic_table = all(
            layer.is_tbc or layer.symmetry == SYMMETRY_ISOTROPIC
            for layer in self._config.layers
        )

        if compact_isotropic_table:
            lines = [
                "## Layer Stack",
                "",
                "| # | Name | rho_cp (J/m³K) | S / TBC | d (m) |",
                "|---|------|----------------|---------|-------|",
            ]
        else:
            lines = [
                "## Layer Stack",
                "",
                "| # | Name | rho_cp (J/m³K) | Sr (W/mK) | Sz (W/mK) | d (m) |",
                "|---|------|----------------|-----------|-----------|-------|",
            ]

        for i, layer in enumerate(self._config.layers):
            d_cell = self._layer_cell(layer.d, f"d_{i}", fitted_names)
            rho_cell = self._layer_cell(layer.rho_cp, f"rho_cp_{i}", fitted_names)

            if compact_isotropic_table:
                conductivity_name = f"TBC_{i}" if layer.is_tbc else f"S_{i}"
                conductivity_value = layer.Sr
                cond_cell = self._layer_cell(conductivity_value, conductivity_name, fitted_names)
                lines.append(f"| {i} | {layer.name} | {rho_cell} | {cond_cell} | {d_cell} |")
            else:
                if layer.symmetry == SYMMETRY_ISOTROPIC and not layer.is_tbc:
                    sr_cell = self._layer_cell(layer.Sr, f"S_{i}", fitted_names)
                    sz_cell = self._layer_cell(layer.Sz, f"S_{i}", fitted_names)
                elif layer.is_tbc:
                    sr_cell = self._layer_cell(layer.Sr, f"TBC_{i}", fitted_names)
                    sz_cell = self._layer_cell(layer.Sz, f"TBC_{i}", fitted_names)
                else:
                    sr_cell = self._layer_cell(layer.Sr, f"Sr_{i}", fitted_names)
                    sz_cell = self._layer_cell(layer.Sz, f"Sz_{i}", fitted_names)
                lines.append(
                    f"| {i} | {layer.name} | {rho_cell} | {sr_cell} | {sz_cell} | {d_cell} |"
                )

        return "\n".join(lines)

    def _build_config_section(self) -> str:
        """Build fit configuration section."""
        lines = [
            "## Fit Configuration",
            "",
        ]

        # Targets table
        if self._config.targets:
            lines.append("### Targets")
            lines.append("")
            lines.append("| Parameter | Bounds | Guess |")
            lines.append("|-----------|--------|-------|")
            for t in self._config.targets:
                guess_str = _fmt(resolve_guess(self._config, t)) if t.guess is not None else "auto"
                lines.append(
                    f"| {t.name} | [{_fmt(t.bounds[0])}, {_fmt(t.bounds[1])}] | {guess_str} |"
                )
            lines.append("")

        # Data settings table
        lines.append("### Data Settings")
        lines.append("")
        lines.append("| Setting | Value |")
        lines.append("|---------|-------|")
        lines.append(f"| freq_spot | {_fmt(self._config.freq_spot)} Hz |")
        lines.append(f"| freq_offset | {_fmt(self._config.freq_offset)} Hz |")
        if self._config.freq_ranges is not None:
            ranges_str = ", ".join(
                f"[{_fmt(r[0])}, {_fmt(r[1])}]" for r in self._config.freq_ranges
            )
            lines.append(f"| freq_ranges | {ranges_str} Hz |")
        if self._config.offset_ranges is not None:
            ranges_str = ", ".join(
                f"[{_fmt(r[0])}, {_fmt(r[1])}]" for r in self._config.offset_ranges
            )
            lines.append(f"| offset_ranges | {ranges_str} um |")
        lines.append(f"| offset_points | {self._config.offset_points} |")
        lines.append(f"| phase_points | {self._config.phase_points} |")
        lines.append(f"| average | {self._config.average} |")
        if self._config.spot_size is not None:
            lines.append(f"| spot_size | {_fmt(self._config.spot_size)} um |")

        return "\n".join(lines)

    def _build_iteration_history(self) -> str:
        """Build iteration history table for PipelineResult."""
        result = self._result
        if not result.history:
            return "## Iteration History\n\n_No iteration data available._"

        # Collect all parameter names across all iterations
        all_keys: list[str] = []
        seen: set[str] = set()
        for step in result.history:
            for k in step:
                if k not in seen:
                    all_keys.append(k)
                    seen.add(k)

        lines = [
            "## Iteration History",
            "",
            "| Iter | " + " | ".join(all_keys) + " | Residual |",
            "|------|" + "|".join(["------"] * (len(all_keys) + 1)) + "|",
        ]

        for i, step in enumerate(result.history):
            vals = []
            for k in all_keys:
                v = step.get(k)
                vals.append(_fmt(v) if v is not None else "-")
            # Derive residual from the last step's FitResult in this iteration
            if i < len(result.step_results) and result.step_results[i]:
                residual = result.step_results[i][-1].residual
            else:
                residual = float("nan")
            vals.append(_fmt(residual))
            lines.append(f"| {i + 1} | " + " | ".join(vals) + " |")

        return "\n".join(lines)

    def _build_final_results(self) -> str:
        """Build final results section."""
        lines = [
            "## Final Results",
            "",
        ]

        if self._is_iterative:
            result = self._result
            fitted = result.final_values
            success = result.success
            if result.step_results and result.step_results[-1]:
                residual = result.step_results[-1][-1].residual
            else:
                residual = float("nan")
            n_iterations = result.n_iterations
            message = result.message
        else:
            result = self._result
            fitted = result.fitted_values
            success = result.success
            residual = result.residual
            n_iterations = None
            message = getattr(result, "message", "")

        # Fitted values table
        lines.append("| Parameter | Value | Unit |")
        lines.append("|-----------|-------|------|")
        for name, value in fitted.items():
            unit = self._get_unit(name)
            lines.append(f"| {name} | {_fmt(value)} | {unit} |")
        lines.append("")

        # Summary
        lines.append(f"**Converged**: {'Yes' if success else 'No'}")
        lines.append(f"**Residual**: {_fmt(residual)}")
        if n_iterations is not None:
            lines.append(f"**Iterations**: {n_iterations}")
        nfev = getattr(result, "nfev", None)
        if nfev is not None:
            lines.append(f"**Function evaluations**: {nfev}")
        if message:
            lines.append(f"**Message**: {message}")

        return "\n".join(lines)

    def _build_plots(self) -> str:
        """Embed plot images as base64 data URIs."""
        if not self._plot_paths:
            return ""

        lines = ["## Fit Plots", ""]
        for i, p in enumerate(self._plot_paths):
            uri = _embed_plot(p)
            lines.append(f"![Plot {i + 1}]({uri})")
            lines.append("")

        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _layer_cell(self, value: float, param_name: str, fitted_names: set[str]) -> str:
        """Format a layer property cell, bold if it is a fitted parameter."""
        text = _fmt(value)
        if param_name in fitted_names:
            return f"**{text}**"
        return text

    @staticmethod
    def _get_unit(name: str) -> str:
        """Determine display unit for a parameter name."""
        if name in ("spot_size", "spot_x", "spot_y"):
            return "um"
        if name.startswith("TBC"):
            return "W/m²K"
        if name.startswith("rho_cp"):
            return "J/m³K"
        if name.startswith("d_"):
            return "m"
        return "W/mK"
