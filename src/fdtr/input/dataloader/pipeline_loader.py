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
          - ``"offset_y_amplitude"``: logical-Y ``(sep_um_y, amp_y_at_freq_spot)``
          - ``"offset_y_phase"``: logical-Y ``(sep_um_y_sub, phase_y_at_freq_offset)``
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

        freq_spot = config.freq_spot
        freq_offset = config.freq_offset

        # FWHM channel: amplitude at freq_spot
        freq_idx_spot = int(np.argmin(np.abs(scan.frequencies - freq_spot)))
        sep_um = scan.offset
        amp_data = scan.r[:, freq_idx_spot]
        datasets["offset_x_amplitude"] = (sep_um, amp_data)

        # Offset-phase channel: phase at freq_offset (subsampled)
        freq_idx_offset = int(np.argmin(np.abs(scan.frequencies - freq_offset)))
        phase_offset_data = scan.theta[:, freq_idx_offset]
        if len(sep_um) > _MAX_PHASE_OFFSET_PTS:
            idx = np.linspace(0, len(sep_um) - 1, _MAX_PHASE_OFFSET_PTS, dtype=int)
            datasets["offset_x_phase"] = (sep_um[idx], phase_offset_data[idx])
        else:
            datasets["offset_x_phase"] = (sep_um, phase_offset_data)

        # Y-direction data (if available)
        if scan_y is not None and sep_um_y is not None and amp_data_y is not None:
            datasets["offset_y_amplitude"] = (sep_um_y, amp_data_y)

            # Y-direction offset-phase channel: phase at freq_offset (subsampled)
            freq_idx_offset_y = int(np.argmin(np.abs(scan_y.frequencies - freq_offset)))
            phase_offset_data_y = scan_y.theta[:, freq_idx_offset_y]
            if len(sep_um_y) > _MAX_PHASE_OFFSET_PTS:
                idx_y = np.linspace(0, len(sep_um_y) - 1, _MAX_PHASE_OFFSET_PTS, dtype=int)
                datasets["offset_y_phase"] = (sep_um_y[idx_y], phase_offset_data_y[idx_y])
            else:
                datasets["offset_y_phase"] = (sep_um_y, phase_offset_data_y)

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
    y_dir = resolve_config_path(config, config.offset_dir_y)
    if y_dir and y_dir.is_dir() and "Y" not in scan_data:
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
        freq_idx_spot_y = int(np.argmin(np.abs(scan_y.frequencies - config.freq_spot)))
        sep_um_y = scan_y.offset
        amp_data_y = scan_y.r[:, freq_idx_spot_y]

    return scan_data, direction, scan, scan_y, sep_um_y, amp_data_y
