# src/fdtr/fit/run/__init__.py
"""Orchestration layer: one runner per CLI strategy.

Each ``run_*`` function accepts a :class:`~fdtr.input.config.FitConfig` and
optional CLI ``args``, then orchestrates the full workflow:
  config -> load data -> fit -> plot -> report -> save.
"""
from fdtr.fit.run.run_freqfit import run_freqfit
from fdtr.fit.run.run_offsetfit import run_offsetfit
from fdtr.fit.run.run_spotfit import run_spotfit
from fdtr.fit.run.run_iterfit import run_iterfit

__all__ = ["run_freqfit", "run_offsetfit", "run_spotfit", "run_iterfit"]
