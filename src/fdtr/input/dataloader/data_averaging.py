"""Multi-file interpolation and averaging for FDTR measurements."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from fdtr.input.dataloader.freq_dataloader import load_freq_sweep
from fdtr.input.dataloader.offset_dataloader import load_offset_scan

@dataclass
class AveragedOffsetScan:
    offset: np.ndarray
    frequencies: np.ndarray
    r: np.ndarray
    r_std: np.ndarray
    theta: np.ndarray
    theta_std: np.ndarray
    probe_rad: float | None = None
    pump_rad: float | None = None

@dataclass
class AveragedFreqSweep:
    frequency: np.ndarray
    amplitude: np.ndarray
    amplitude_std: np.ndarray
    phase: np.ndarray
    phase_std: np.ndarray

def average_offset_scans(filepaths: list, common_sep: np.ndarray) -> AveragedOffsetScan:
    if not filepaths:
        raise ValueError("filepaths must be non-empty")
    scans = [load_offset_scan(fp) for fp in filepaths]
    first = scans[0]
    n_harmonics = first.n_harmonics
    n_files = len(scans)
    n_grid = len(common_sep)
    r_interp = np.zeros((n_files, n_grid, n_harmonics))
    theta_interp = np.zeros((n_files, n_grid, n_harmonics))
    for i, scan in enumerate(scans):
        for h in range(n_harmonics):
            r_interp[i, :, h] = PchipInterpolator(scan.offset, scan.r[:, h])(common_sep)
            theta_interp[i, :, h] = PchipInterpolator(scan.offset, scan.theta[:, h])(common_sep)
    return AveragedOffsetScan(
        offset=common_sep.copy(), frequencies=first.frequencies.copy(),
        r=np.mean(r_interp, axis=0), r_std=np.std(r_interp, axis=0, ddof=0),
        theta=np.mean(theta_interp, axis=0), theta_std=np.std(theta_interp, axis=0, ddof=0),
        probe_rad=first.probe_rad, pump_rad=first.pump_rad,
    )

def average_freq_sweeps(filepaths: list, common_freq: np.ndarray) -> AveragedFreqSweep:
    if not filepaths:
        raise ValueError("filepaths must be non-empty")
    sweeps = [load_freq_sweep(fp) for fp in filepaths]
    n_files = len(sweeps)
    n_grid = len(common_freq)
    amp_interp = np.zeros((n_files, n_grid))
    phase_interp = np.zeros((n_files, n_grid))
    for i, sweep in enumerate(sweeps):
        amp_interp[i, :] = PchipInterpolator(sweep.frequency, sweep.amplitude)(common_freq)
        phase_interp[i, :] = PchipInterpolator(sweep.frequency, sweep.phase)(common_freq)
    return AveragedFreqSweep(
        frequency=common_freq.copy(),
        amplitude=np.mean(amp_interp, axis=0), amplitude_std=np.std(amp_interp, axis=0, ddof=0),
        phase=np.mean(phase_interp, axis=0), phase_std=np.std(phase_interp, axis=0, ddof=0),
    )
