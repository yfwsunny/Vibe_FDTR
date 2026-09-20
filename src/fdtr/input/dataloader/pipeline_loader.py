"""Pipeline-aware data loading for iterfit.

Inspects the pipeline steps to determine which data types (offset, freq, fwhm)
are needed, then loads only those from the paths specified in a :class:`FitConfig`.

Returns a ``datasets`` dict whose keys match the ``data_key`` fields in the
pipeline steps and whose values are ``(x_array, y_array)`` tuples ready for
:class:`~fdtr.fit.iterfit.PipelineRunner`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from fdtr.fit.iterfit.pipeline import PipelineSpec, resolve_pipeline_for_config
from fdtr.input.dataloader.cli_data_loader import _load_offset_scan_data, _load_freq_sweep_data
from fdtr.input.config.path_resolution import resolve_config_path


# Maximum points used when subsampling the offset-phase channel.
_MAX_PHASE_OFFSET_PTS = 50
_FREQ_MATCH_RTOL = 1e-6
_FREQ_MATCH_ATOL_HZ = 1e-3


def load_pipeline_datasets(
    config: "FitConfig",
    pipeline: Optional[PipelineSpec] = None,
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Inspect pipeline steps and load only the data types they require.

    Args:
        config: A :class:`FitConfig` providing data paths, frequencies, and
            data-selection settings.
        pipeline: Optional pre-loaded pipeline.  When *None*, the pipeline is
            resolved from ``config.pipeline`` (path string, ``"builtin:default"``,
            or ``None`` all fall back to the built-in default).

        Returns:
        Mapping of ``data_key -> (x_array, y_array)`` tuples:
          - ``"offset_x_amplitude"``: logical-X ``(sep_um, amp_at_freq_spot)``
          - ``"offset_x_phase"``: logical-X ``(sep_um_sub, phase_at_freq_offset)``
          - ``"offset_x_center_amp"``: logical-X ``(sep_um_sub, amp_at_freq_offset)``
          - ``"offset_y_amplitude"``: logical-Y ``(sep_um_y, amp_y_at_freq_spot)``
          - ``"offset_y_phase"``: logical-Y ``(sep_um_y_sub, phase_y_at_freq_offset)``
          - ``"offset_y_center_amp"``: logical-Y ``(sep_um_y_sub, amp_y_at_freq_offset)``
          - ``"freq_phase"``: ``(freq, phase)``
    """
    # --- Resolve pipeline ------------------------------------------------
    if pipeline is None:
        pipeline = _resolve_pipeline(config)

    # --- Collect needed fitter strategies --------------------------------
    needed = {step.fitter for step in pipeline.steps}  # e.g. {"fwhm","offset","freq"}

    datasets: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}

    has_offset_or_fwhm = ("offset" in needed) or ("fwhm" in needed)
    has_freq = "freq" in needed

    # --- Offset / FWHM data ---------------------------------------------
    if has_offset_or_fwhm:
        scan_data, direction, scan, scan_y, sep_um_y, amp_data_y = _load_offset(config)
        _ = (scan_data, direction, sep_um_y, amp_data_y)

        offset_steps = [step for step in pipeline.steps if step.fitter == "offset"]
        fwhm_steps = [step for step in pipeline.steps if step.fitter == "fwhm"]

        # Keep the historical companion spot-amplitude datasets available for
        # offset-only diagnostics unless an offset step explicitly owns the key.
        offset_step_keys = {step.data_key for step in offset_steps}
        if "offset_x_amplitude" not in offset_step_keys:
            _add_spot_dataset(datasets, "offset_x_amplitude", scan, config.freq_spot)
        if scan_y is not None and "offset_y_amplitude" not in offset_step_keys:
            _add_spot_dataset(datasets, "offset_y_amplitude", scan_y, config.freq_spot)

        for step in fwhm_steps:
            step_scan = _scan_for_data_key(step.data_key, scan, scan_y)
            if step_scan is not None:
                _add_spot_dataset(datasets, step.data_key, step_scan, config.freq_spot)

        for step in offset_steps:
            step_scan = _scan_for_data_key(step.data_key, scan, scan_y)
            if step_scan is not None:
                requested = step.freq_offset if step.freq_offset is not None else config.freq_offset
                _add_offset_dataset(datasets, step, step_scan, requested)

    # --- Freq-sweep data -------------------------------------------------
    if has_freq:
        phase_dir = resolve_config_path(config, config.phase_dir or config.data_file)
        if phase_dir is None:
            raise ValueError("No phase_dir or data_file specified for freq pipeline step.")
        freq_sweep, phase_sweep, _ = _load_freq_sweep_data(
            phase_dir,
            average=config.average,
            n_points=config.phase_points,
            pattern=config.phase_pattern,
            explicit_files=config.phase_files,
        )
        datasets["freq_phase"] = (freq_sweep, phase_sweep)

    return datasets


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_pipeline(config: "FitConfig") -> PipelineSpec:
    """Load the pipeline spec from config (or use the built-in default)."""
    return resolve_pipeline_for_config(config)


def _require_matching_frequency(
    frequencies: np.ndarray,
    requested: float | None,
    label: str,
) -> int:
    """Return the harmonic index matching *requested* within a tight tolerance."""
    if requested is None:
        raise ValueError(f"{label} is required for iterfit offset/fwhm data.")
    freq = np.asarray(frequencies, dtype=np.float64).ravel()
    matches = np.flatnonzero(
        np.isclose(freq, float(requested), rtol=_FREQ_MATCH_RTOL, atol=_FREQ_MATCH_ATOL_HZ)
    )
    if matches.size == 0:
        available = ", ".join(f"{float(f):.12g}" for f in freq)
        raise ValueError(
            f"{label}={float(requested):.12g} Hz does not match available "
            f"harmonics within rtol={_FREQ_MATCH_RTOL:g}, atol={_FREQ_MATCH_ATOL_HZ:g} Hz. "
            f"available: [{available}]"
        )
    closest = matches[np.argmin(np.abs(freq[matches] - float(requested)))]
    return int(closest)


def _scan_for_data_key(data_key: str, scan: Any, scan_y: Optional[Any]) -> Optional[Any]:
    """Return the logical scan selected by an iterfit offset/fwhm data key."""
    if data_key.startswith("offset_y_"):
        return scan_y
    return scan


def _add_spot_dataset(
    datasets: Dict[str, Tuple[np.ndarray, np.ndarray]],
    data_key: str,
    scan: Any,
    requested_freq: float | None,
) -> None:
    """Add an amplitude dataset at freq_spot for an FWHM/spot diagnostic step."""
    freq_idx = _require_matching_frequency(scan.frequencies, requested_freq, "freq_spot")
    _store_dataset(datasets, data_key, (scan.offset, scan.r[:, freq_idx]))


def _add_offset_dataset(
    datasets: Dict[str, Tuple[np.ndarray, np.ndarray]],
    step,
    scan: Any,
    requested_freq: float | None,
) -> None:
    """Add an offset step dataset and its phase-centering amplitude companion."""
    label = f"{step.name}.freq_offset" if step.freq_offset is not None else "freq_offset"
    freq_idx = _require_matching_frequency(scan.frequencies, requested_freq, label)
    sep_um = scan.offset
    signal = step.signal or "phase"
    if signal == "amplitude":
        signal_data = scan.r[:, freq_idx]
        _store_dataset(datasets, step.data_key, (sep_um, signal_data))
        return

    signal_data = scan.theta[:, freq_idx]
    center_amp_data = scan.r[:, freq_idx]
    if len(sep_um) > _MAX_PHASE_OFFSET_PTS:
        idx = np.linspace(0, len(sep_um) - 1, _MAX_PHASE_OFFSET_PTS, dtype=int)
        sep_out = sep_um[idx]
        signal_out = signal_data[idx]
        center_amp_out = center_amp_data[idx]
    else:
        sep_out = sep_um
        signal_out = signal_data
        center_amp_out = center_amp_data
    _store_dataset(datasets, step.data_key, (sep_out, signal_out))
    if step.data_key.endswith("_phase"):
        center_key = f"{step.data_key[:-len('_phase')]}_center_amp"
        _store_dataset(datasets, center_key, (sep_out, center_amp_out))


def _store_dataset(
    datasets: Dict[str, Tuple[np.ndarray, np.ndarray]],
    data_key: str,
    value: Tuple[np.ndarray, np.ndarray],
) -> None:
    """Store one dataset, rejecting ambiguous duplicate keys."""
    if data_key in datasets:
        existing_x, existing_y = datasets[data_key]
        new_x, new_y = value
        if np.array_equal(existing_x, new_x) and np.array_equal(existing_y, new_y):
            return
        raise ValueError(f"Pipeline data_key '{data_key}' is requested with conflicting data.")
    datasets[data_key] = value


def _load_offset(
    config: "FitConfig",
) -> Tuple[dict, str, Any, Optional[Any], Optional[np.ndarray], Optional[np.ndarray]]:
    """Load offset scan data from config paths.

    Returns:
        (scan_data, direction, scan, scan_y, sep_um_y, amp_data_y)
    """
    offset_dir = resolve_config_path(config, config.offset_dir or config.data_file)
    if offset_dir is None:
        raise ValueError("No offset_dir or data_file specified for offset/fwhm pipeline step.")

    scan_data = _load_offset_scan_data(
        offset_dir,
        average=config.average,
        n_points=config.offset_points,
        pattern=config.offset_pattern,
        explicit_files=config.offset_files,
        pattern_y=config.offset_pattern_y,
        explicit_files_y=config.offset_files_y,
    )

    # Load Y-direction data if configured
    y_dir = resolve_config_path(config, config.offset_dir_y or config.data_file_y)
    if y_dir and y_dir.exists() and "Y" not in scan_data:
        y_scan_data = _load_offset_scan_data(
            y_dir,
            average=config.average,
            n_points=config.offset_points,
            pattern=config.offset_pattern_y,
            explicit_files=config.offset_files_y,
        )
        if "Y" in y_scan_data:
            scan_data["Y"] = y_scan_data["Y"]
        elif y_scan_data:
            scan_data["Y"] = list(y_scan_data.values())[0]

    # Select logical X, falling back only when the configured logical-X bucket
    # is absent. The X/Y labels here are fitting axes, not filename axes.
    if "X" in scan_data:
        direction = "X"
    elif "Y" in scan_data:
        direction = "Y"
    else:
        direction = list(scan_data.keys())[0]

    scan = scan_data[direction]

    # Load the companion logical-Y data if available in scan_data.
    other_dir = "Y" if direction == "X" else "X"
    scan_y = None
    sep_um_y = None
    amp_data_y = None
    if other_dir in scan_data:
        scan_y = scan_data[other_dir]
        freq_idx_spot_y = _require_matching_frequency(scan_y.frequencies, config.freq_spot, "freq_spot")
        sep_um_y = scan_y.offset
        amp_data_y = scan_y.r[:, freq_idx_spot_y]

    return scan_data, direction, scan, scan_y, sep_um_y, amp_data_y
