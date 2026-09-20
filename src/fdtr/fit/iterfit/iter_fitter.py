"""PipelineRunner — orchestrates iterative fitting via a TOML-defined pipeline.

Each iteration walks through the pipeline steps, creates the appropriate fitter
for each step, runs the sub-fit, and updates the parameter dict. The stack is
rebuilt after each step so subsequent steps see the latest parameter values.

Spot size handling:
    The pipeline tracks ``spot_x`` and ``spot_y`` independently. Each step
    specifies a ``spot_key`` policy (``"spot_x"``, ``"spot_y"``,
    ``"spot_size"``, or ``"none"``) that determines which spot size the runner
    passes to the fitter. ``spot_size`` is the average of ``spot_x`` and
    ``spot_y``. When Y-direction data is absent, ``spot_y`` defaults to
    ``spot_x``. For backward compatibility, a ``spot_size`` target is
    automatically aliased to both ``spot_x`` and ``spot_y``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from fdtr.model.layer import MultilayerStack
from fdtr.common_types import FitResult, FitTarget, SignalType
from fdtr.fit.freq_fitter import FreqFitter
from fdtr.fit.fwhm_fitter import FWHMFitter
from fdtr.fit.offset_fitter import OffsetFitter
from fdtr.fit.offsetcenter_cal import center_amp_key_for_offset_data, resolve_center_amp
from fdtr.model.param import apply_params, validate_targets

from .pipeline import PipelineSpec, StepSpec, validate_pipeline

# Spot-related parameter names that should NOT be applied to layer properties.
_SPOT_PARAM_NAMES = frozenset({"spot_size", "spot_x", "spot_y"})


@dataclass
class PipelineResult:
    """Outcome of a pipeline execution.

    Attributes:
        final_values: Mapping of parameter name -> fitted physical value.
        history: Per-iteration snapshot of all parameter values.
        step_results: Per-iteration, per-step list of FitResult objects.
        n_iterations: Number of iterations actually executed.
        success: True if every sub-fit in every iteration converged.
        message: Human-readable summary.
    """

    final_values: Dict[str, float]
    history: List[Dict[str, float]]
    step_results: List[List[FitResult]]
    n_iterations: int
    success: bool
    message: str = ""

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict."""
        d = {
            "strategy": "iterfit",
            "final_values": dict(self.final_values),
            "history": [dict(h) for h in self.history],
            "n_iterations": self.n_iterations,
            "success": self.success,
        }
        if self.step_results:
            d["step_results"] = [
                [sr.to_dict() for sr in step] for step in self.step_results
            ]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineResult":
        """Reconstruct from a dict produced by :meth:`to_dict`."""
        from fdtr.common_types import FitResult as _FitResult
        step_results = [
            [_FitResult.from_dict(sr) for sr in step]
            for step in d.get("step_results", [])
        ]
        return cls(
            final_values=d["final_values"],
            history=d["history"],
            step_results=step_results,
            n_iterations=d["n_iterations"],
            success=d["success"],
        )


class PipelineRunner:
    """Execute an iterative fitting pipeline defined by a :class:`PipelineSpec`.

    Args:
        pipeline: The pipeline specification (step order, fitter types, etc.).
        config: A :class:`FitConfig` providing layer specs, targets, and
            frequency / spot-size settings.
        datasets: Mapping of ``data_key -> (x_array, y_array)`` providing
            the measured data for each step.  For ``"fwhm"`` steps the tuple
            is ``(sep_um, amp_data)``; for ``"freq"`` steps it is
            ``(freq_hz, phase_or_amp)``; for ``"offset"`` steps it is
            ``(sep_um, phase_or_amp)``.
    """

    def __init__(
        self,
        pipeline: PipelineSpec,
        config: "FitConfig",
        datasets: Dict[str, Tuple[np.ndarray, np.ndarray]],
    ) -> None:
        self._pipeline = pipeline
        self._config = config
        self._datasets = datasets

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, n_iterations: int = 6) -> PipelineResult:
        """Execute the pipeline for *n_iterations*.

        Returns:
            A :class:`PipelineResult` with the full iteration history.
        """
        config = self._config
        from fdtr.input.config import to_stack as _to_stack
        stack = _to_stack(config)
        default_spot = config.spot_size or config.spot_x or config.spot_y or 3.0

        # Validate pipeline before running
        errors = validate_pipeline(self._pipeline, self._datasets, stack)
        if errors:
            raise ValueError(
                "Pipeline validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        params: Dict[str, float] = self._initial_spot_params(default_spot)
        history: List[Dict[str, float]] = []
        step_results: List[List[FitResult]] = []
        all_success = True

        for iteration in range(n_iterations):
            iter_step_results: List[FitResult] = []

            for step in self._pipeline.steps:
                targets = self._build_targets(step, params, stack)

                if step.fitter == "fwhm":
                    result = self._run_fwhm(step, stack, targets)
                elif step.fitter == "freq":
                    effective_spot = self._resolve_effective_spot(
                        params, step.spot_key, default_spot
                    )
                    result = self._run_freq(step, stack, targets, effective_spot)
                elif step.fitter == "offset":
                    effective_spot = self._resolve_effective_spot(
                        params, step.spot_key, default_spot
                    )
                    result = self._run_offset(step, stack, targets, effective_spot)
                else:
                    raise ValueError(
                        f"Unknown fitter type '{step.fitter}' in step '{step.name}'."
                    )

                iter_step_results.append(result)
                all_success = all_success and result.success

                # Update params and rebuild stack for subsequent steps
                params.update(result.fitted_values)
                self._alias_spot_params(params, result.fitted_values)
                stack, _ = self._rebuild_stack(stack, default_spot, params)

            # End of iteration: compute spot_size (average of spot_x and spot_y).
            # If Y-direction data is unavailable, spot_y defaults to spot_x.
            spot_x = params.get("spot_x", params.get("spot_size", default_spot))
            has_y_data = "offset_y_amplitude" in self._datasets
            if not has_y_data and self._config.spot_y is None:
                params["spot_y"] = spot_x
            spot_y = params.get("spot_y", spot_x)
            params["spot_size"] = (spot_x + spot_y) / 2.0

            history.append(dict(params))
            step_results.append(iter_step_results)

        return PipelineResult(
            final_values=dict(params),
            history=history,
            step_results=step_results,
            n_iterations=n_iterations,
            success=all_success,
            message="Pipeline completed successfully."
            if all_success
            else "Pipeline completed with some steps not converged.",
        )

    # ------------------------------------------------------------------
    # Internal: spot size management
    # ------------------------------------------------------------------

    def _initial_spot_params(self, default_spot: float) -> Dict[str, float]:
        """Seed fixed spot-axis values before the first pipeline step."""
        cfg = self._config
        spot_x = cfg.spot_x if cfg.spot_x is not None else default_spot
        spot_y = cfg.spot_y if cfg.spot_y is not None else spot_x
        return {
            "spot_x": float(spot_x),
            "spot_y": float(spot_y),
            "spot_size": float((spot_x + spot_y) / 2.0),
        }

    @staticmethod
    def _resolve_effective_spot(
        params: Dict[str, float],
        spot_key: str,
        default_spot: float,
    ) -> float:
        """Compute the effective spot size from the ``spot_key`` policy."""
        spot_x = params.get("spot_x", params.get("spot_size", default_spot))
        spot_y = params.get("spot_y", spot_x)

        if spot_key == "spot_x":
            return spot_x
        elif spot_key == "spot_y":
            return spot_y
        elif spot_key in ("spot_avg", "spot_size"):
            return (spot_x + spot_y) / 2.0
        elif spot_key == "none":
            return default_spot
        else:
            # Unknown key — fall back to average
            return (spot_x + spot_y) / 2.0

    @staticmethod
    def _alias_spot_params(
        params: Dict[str, float],
        fitted_values: Dict[str, float],
    ) -> None:
        """Backward-compatibility: alias spot_size to spot_x/spot_y.

        When ``spot_size`` is fitted (old-style target), update both
        ``spot_x`` and ``spot_y`` so downstream logic sees them.
        """
        if "spot_size" in fitted_values:
            val = fitted_values["spot_size"]
            params["spot_x"] = val
            params["spot_y"] = val

    # ------------------------------------------------------------------
    # Internal: target construction
    # ------------------------------------------------------------------

    def _build_targets(
        self,
        step: StepSpec,
        current_params: Dict[str, float],
        stack: MultilayerStack,
    ) -> List[FitTarget]:
        """Build FitTarget list for a step from config targets + current params.

        Supports spot-size aliasing: if the pipeline step requests ``spot_x``
        or ``spot_y`` but the config only defines a ``spot_size`` target, a
        matching target is created automatically from the ``spot_size`` bounds.
        """
        from fdtr.input.config import TargetSpec, resolve_guess

        # Build the full target spec list (includes layer fit_fields + spot)
        all_specs = self._collect_target_specs()

        targets = []
        missing_specs: list[str] = []
        for step_name in step.target_names:
            # Direct match first
            matched = [s for s in all_specs if s.name == step_name]

            # Alias: spot_x/spot_y from spot_size
            if not matched and step_name in ("spot_x", "spot_y"):
                matched = [s for s in all_specs if s.name == "spot_size"]
                if matched:
                    src = matched[0]
                    matched = [TargetSpec(name=step_name, bounds=src.bounds, guess=src.guess)]

            if not matched:
                missing_specs.append(step_name)
                continue

            tspec = matched[0]
            lb, ub = tspec.bounds

            if step_name in current_params:
                guess = current_params[step_name]
            elif tspec.name in current_params:
                guess = current_params[tspec.name]
            else:
                guess = resolve_guess(self._config, tspec)
                # If we aliased spot_x/spot_y from spot_size, use the same guess
                if step_name != tspec.name and step_name in current_params:
                    guess = current_params[step_name]

            targets.append(
                FitTarget(
                    name=step_name,
                    initial_guess=guess,
                    bounds=(lb, ub),
                )
            )

        if missing_specs:
            raise ValueError(
                f"Pipeline step '{step.name}' is missing target spec(s) in config: "
                f"{', '.join(missing_specs)}. "
                "Define fit bounds for every pipeline target in the config."
            )
        return targets

    def _collect_target_specs(self) -> list:
        """Collect all TargetSpec from layer fit_fields + spot fields + legacy targets."""
        from fdtr.input.config import TargetSpec
        specs: list[TargetSpec] = []
        # Layer fit_fields
        for i, layer in enumerate(self._config.layers):
            specs.extend(layer.to_targets(i))
        # Spot fit fields
        cfg = self._config
        if cfg.fit_spot_size is not None:
            specs.append(TargetSpec(name="spot_size", bounds=cfg.fit_spot_size, guess=cfg.spot_size))
        if cfg.fit_spot_x is not None:
            specs.append(TargetSpec(name="spot_x", bounds=cfg.fit_spot_x, guess=cfg.spot_x or cfg.spot_size))
        if cfg.fit_spot_y is not None:
            specs.append(TargetSpec(name="spot_y", bounds=cfg.fit_spot_y, guess=cfg.spot_y or cfg.spot_x or cfg.spot_size))
        # Legacy [[fit.targets]]
        existing = {s.name for s in specs}
        for t in cfg.targets:
            if t.name not in existing:
                specs.append(t)
        return specs

    # ------------------------------------------------------------------
    # Internal: fitter invocation
    # ------------------------------------------------------------------

    def _run_fwhm(
        self,
        step: StepSpec,
        stack: MultilayerStack,
        targets: List[FitTarget],
    ) -> FitResult:
        """Run FWHMFitter for a step."""
        x_data, y_data = self._datasets[step.data_key]
        sep_um = np.asarray(x_data, dtype=np.float64)
        amp_data = np.asarray(y_data, dtype=np.float64)
        freq = self._config.freq_spot
        fitter = FWHMFitter(
            stack=stack,
            freq=freq,
            sep_um=sep_um,
        )
        return fitter.fit(amp_data, targets)

    def _run_freq(
        self,
        step: StepSpec,
        stack: MultilayerStack,
        targets: List[FitTarget],
        spot_size_um: float,
    ) -> FitResult:
        """Run FreqFitter for a step."""
        x_data, y_data = self._datasets[step.data_key]
        freq_data = np.asarray(x_data, dtype=np.float64)
        signal_data = np.asarray(y_data, dtype=np.float64)
        signal = self._resolve_signal(step)

        # 优先级：step.freq_ranges > config.freq_ranges > 全数据范围
        if step.freq_ranges is not None:
            freq_ranges = step.freq_ranges
        elif self._config.freq_ranges is not None:
            freq_ranges = self._config.freq_ranges
        else:
            fmin = float(freq_data.min())
            fmax = float(freq_data.max())
            freq_ranges = [(fmin, fmax)]

        fitter = FreqFitter(
            stack=stack,
            signal=signal,
            spot_size_um=spot_size_um,
            freq_ranges=freq_ranges,
            n_points=self._config.phase_points,
        )
        return fitter.fit(freq_data, signal_data, targets)

    def _run_offset(
        self,
        step: StepSpec,
        stack: MultilayerStack,
        targets: List[FitTarget],
        spot_size_um: float,
    ) -> FitResult:
        """Run OffsetFitter for a step."""
        x_data, y_data = self._datasets[step.data_key]
        offset_data = np.asarray(x_data, dtype=np.float64)
        signal_data = np.asarray(y_data, dtype=np.float64)
        signal = self._resolve_signal(step)
        center_amp_data = self._resolve_center_amp_data(step, offset_data, signal_data, signal)

        # 优先级：step.offset_ranges > config.offset_ranges > 全数据范围
        if step.offset_ranges is not None:
            offset_ranges = step.offset_ranges
        elif self._config.offset_ranges is not None:
            offset_ranges = self._config.offset_ranges
        else:
            offset_min = float(offset_data.min())
            offset_max = float(offset_data.max())
            offset_ranges = [(offset_min, offset_max)]

        freq = step.freq_offset if step.freq_offset is not None else self._config.freq_offset

        fitter = OffsetFitter(
            stack=stack,
            signal=signal,
            freq=freq,
            spot_size_um=spot_size_um,
            offset_ranges=offset_ranges,
            n_points=self._config.offset_points,
        )
        return fitter.fit(offset_data, signal_data, targets, center_amp_data=center_amp_data)

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_signal(step: StepSpec) -> SignalType:
        """Convert step.signal string to a SignalType enum value."""
        if step.signal == "amplitude":
            return SignalType.AMPLITUDE
        return SignalType.PHASE

    def _resolve_center_amp_data(
        self,
        step: StepSpec,
        offset_data: np.ndarray,
        signal_data: np.ndarray,
        signal: SignalType,
    ) -> np.ndarray:
        """Resolve center amplitude for an offset step on the step grid."""
        if signal is SignalType.AMPLITUDE:
            return signal_data

        center_amp_key = center_amp_key_for_offset_data(step.data_key)
        if center_amp_key and center_amp_key in self._datasets:
            center_offset_data, raw_center_amp = self._datasets[center_amp_key]
            return resolve_center_amp(
                offset_data,
                signal_data,
                center_offset_data=center_offset_data,
                center_amp_data=raw_center_amp,
            )
        return signal_data

    @staticmethod
    def _rebuild_stack(
        stack: MultilayerStack,
        spot_size_um: float,
        params: Dict[str, float],
    ) -> Tuple[MultilayerStack, Optional[float]]:
        """Rebuild the stack with current fitted values via param_resolver."""
        stack_params = {
            k: v for k, v in params.items()
            if k not in _SPOT_PARAM_NAMES
        }
        if not stack_params:
            return stack, None
        dummy_targets = [
            FitTarget(name=k, initial_guess=1.0, bounds=(0.1, 10.0))
            for k in stack_params
        ]
        resolved = validate_targets(dummy_targets, stack, allow_spot=True)
        new_stack, new_spot = apply_params(stack, spot_size_um, stack_params, resolved)
        return new_stack, new_spot
