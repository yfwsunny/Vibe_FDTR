import pytest
import numpy as np

pytestmark = pytest.mark.slow


def _make_iterfit_config(**overrides):
    """Minimal iterfit config dict for testing.

    Uses reduced point counts (offset=20, phase=20) to keep Jacobian
    computation fast — sufficient for functional and relative-order
    validation.
    """
    base = {
        "temperature": 296.0,
        "layer": [
            {"Sr": 140, "Sz": 140, "d": 7.3e-8, "rho_cp": 2.48e6},
            {"name": "TBC", "rho_cp": 0, "Sr": 9.3e7, "Sz": 9.3e7, "d": 1},
            {"Sr": 2387, "Sz": 4.4, "d": 1, "rho_cp": 1.58e6},
        ],
        "fit": {
            "strategy": "iterfit",
            "pipeline": "builtin:default",
            "spot_size": 2.86,
            "freq_offset": 1.194e6,
            "freq_spot": 5e7,
            "offset_points": 20,
            "phase_points": 20,
        },
        "uncertainty": {
            "known_params": {"d_0": 0.05, "Sr_0": 0.05, "Sz_0": 0.05},
            "max_iterations": 2,
            "tolerance": 0.05,
        },
    }
    # Apply overrides into the correct nested section
    for key, val in overrides.items():
        if key in ("offset_points", "phase_points", "spot_size",
                    "freq_offset", "freq_spot"):
            base["fit"][key] = val
        elif key == "known_params":
            base["uncertainty"]["known_params"] = val
        else:
            base[key] = val
    return base


def _run_uncertainty(config):
    from fdtr.analysis.uncertainty.engine import run_iterfit_uncertainty
    result, _history = run_iterfit_uncertainty(config)
    return result


# ---------------------------------------------------------------------------
# Shared fixtures — each calls run_iterfit_uncertainty once per module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def iterfit_uncertainty_result():
    """Default uncertainty with user-provided non-spot known parameters."""
    return _run_uncertainty(_make_iterfit_config())


@pytest.fixture(scope="module")
def iterfit_uncertainty_zero_spot():
    """Uncertainty with no user-provided spot uncertainty for comparison."""
    return _run_uncertainty(
        _make_iterfit_config(known_params={
            "d_0": 0.05, "Sr_0": 0.05, "Sz_0": 0.05,
        })
    )


@pytest.fixture(scope="module")
def iterfit_uncertainty_empty_known():
    """Uncertainty with empty known_params (auto-fill 5% defaults)."""
    return _run_uncertainty(_make_iterfit_config(known_params={}))


@pytest.fixture(scope="module")
def iterfit_uncertainty_high_d0():
    """Uncertainty with high d_0=50%."""
    return _run_uncertainty(_make_iterfit_config(known_params={"d_0": 0.50}))


@pytest.fixture(scope="module")
def iterfit_uncertainty_low_d0():
    """Uncertainty with low d_0=0.1%."""
    return _run_uncertainty(_make_iterfit_config(known_params={"d_0": 0.001}))


# ---------------------------------------------------------------------------
# Tests using shared fixtures (no extra run_iterfit_uncertainty calls)
# ---------------------------------------------------------------------------

def test_run_iterfit_uncertainty_returns_all_params(iterfit_uncertainty_result):
    result = iterfit_uncertainty_result
    assert "spot_size" in result
    assert "Sr_2" in result
    assert "Sz_2" in result
    assert "TBC_1" in result


def test_iterfit_uncertainty_positive(iterfit_uncertainty_result):
    for name, rel_unc in iterfit_uncertainty_result.items():
        assert rel_unc > 0, f"{name} has non-positive uncertainty"


def test_iterfit_uncertainty_reasonable_magnitude(iterfit_uncertainty_result):
    for name, rel_unc in iterfit_uncertainty_result.items():
        assert rel_unc < 1.0, f"{name} uncertainty {rel_unc:.2%} exceeds 100%"


def test_iterfit_uncertainty_spot_propagates_to_sr(
    iterfit_uncertainty_zero_spot, iterfit_uncertainty_result
):
    """Sr_2 uncertainty should be higher than if spot_size had zero uncertainty."""
    assert iterfit_uncertainty_result["Sr_2"] >= iterfit_uncertainty_zero_spot["Sr_2"] * 0.99


def test_spot_consolidation(iterfit_uncertainty_result):
    """spot_size should be present and positive after consolidation."""
    result = iterfit_uncertainty_result
    assert "spot_size" in result
    assert result["spot_size"] > 0


def test_iterfit_uncertainty_with_empty_known_params(iterfit_uncertainty_empty_known):
    """Iterfit uncertainty should produce results even with empty known_params (5% auto-fill)."""
    result = iterfit_uncertainty_empty_known
    assert len(result) > 0, "Should produce results with auto-filled 5% defaults"
    for name, rel_unc in result.items():
        assert rel_unc > 0, f"{name} should have positive uncertainty"


def test_iterfit_uncertainty_user_known_overrides_default(
    iterfit_uncertainty_high_d0, iterfit_uncertainty_low_d0
):
    """User-specified known_params should override the 5% default."""
    assert iterfit_uncertainty_high_d0["Sz_2"] > iterfit_uncertainty_low_d0["Sz_2"]


# ---------------------------------------------------------------------------
# Tests that need their own independent call (mocking or special logic)
# ---------------------------------------------------------------------------

def test_single_spot_param_in_known():
    """Non-FWHM steps should include at most one spot parameter in known."""
    from fdtr.analysis.uncertainty.engine import run_iterfit_uncertainty
    import fdtr.analysis.uncertainty.engine as eng
    from unittest.mock import patch

    config = _make_iterfit_config()
    spot_counts = []

    original_compute = eng.compute_jacobian
    original_fwhm = eng.compute_fwhm_jacobian

    def track_jacobian(config, params, x_data, analysis_kind_or_freq, delta=0.01):
        param_names = [p.raw_name for p in params]
        spot_count = sum(1 for n in param_names if n in ("spot_size", "spot_x", "spot_y"))
        spot_counts.append(spot_count)
        if isinstance(analysis_kind_or_freq, str) and analysis_kind_or_freq in ("freq", "offset"):
            return original_compute(config, params, x_data, analysis_kind_or_freq, delta)
        return original_fwhm(config, params, x_data, analysis_kind_or_freq, delta)

    with patch.object(eng, "compute_jacobian", side_effect=track_jacobian):
        with patch.object(eng, "compute_fwhm_jacobian", side_effect=track_jacobian):
            run_iterfit_uncertainty(config)

    for count in spot_counts:
        assert count <= 1, f"Found {count} spot params in Jacobian — should be at most 1"


def test_iterfit_uncertainty_uses_step_spot_key(monkeypatch):
    """Each iterfit uncertainty step should use the same spot policy as fitting."""
    import fdtr.analysis.uncertainty.engine as eng

    config = _make_iterfit_config(spot_size=3.0)
    config["fit"]["spot_x"] = 2.0
    config["fit"]["spot_y"] = 4.0
    config["uncertainty"]["known_params"] = {"d_0": 0.05}
    config["uncertainty"]["max_iterations"] = 1

    calls = []

    def fake_jacobian(config, params, x_data, analysis_kind_or_freq, delta=0.01):
        names = tuple(p.raw_name for p in params)
        calls.append((analysis_kind_or_freq, names, config.spot_size))
        x = np.arange(1, len(x_data) + 1, dtype=float)
        return np.column_stack([x ** (i + 1) for i in range(len(params))])

    monkeypatch.setattr(eng, "compute_fwhm_jacobian", fake_jacobian)
    monkeypatch.setattr(eng, "compute_jacobian", fake_jacobian)

    eng.run_iterfit_uncertainty(config)

    fwhm_freq = config["fit"]["freq_spot"]
    assert ("spot_x", 2.0) in {
        (names[0], spot) for kind, names, spot in calls if kind == fwhm_freq and names
    }
    assert ("spot_y", 4.0) in {
        (names[0], spot) for kind, names, spot in calls if kind == fwhm_freq and names
    }
    assert ("Sr_2", 2.0) in {
        (names[0], spot) for kind, names, spot in calls if kind == "offset" and names
    }
    assert (("Sz_2", "TBC_1"), 3.0) in {
        (names, spot) for kind, names, spot in calls if kind == "freq"
    }


def test_iterfit_ignores_user_spot_known_when_spot_is_fitted():
    """User spot known params must not override forward-propagated spot uncertainty."""
    config_without_user_spot = _make_iterfit_config(
        known_params={"d_0": 0.05, "Sr_0": 0.05, "Sz_0": 0.05},
    )
    config_with_user_spot = _make_iterfit_config(
        known_params={
            "d_0": 0.05,
            "Sr_0": 0.05,
            "Sz_0": 0.05,
            "spot_size": 0.50,
            "spot_x": 0.50,
        },
    )

    baseline = _run_uncertainty(config_without_user_spot)
    with pytest.warns(UserWarning) as warning_records:
        with_user_spot = _run_uncertainty(config_with_user_spot)
    warning_messages = [str(record.message) for record in warning_records]
    assert any("Multiple spot known_params" in message for message in warning_messages)
    assert any(
        "ignored" in message and "spot is fitted" in message
        for message in warning_messages
    )

    for name in baseline:
        assert with_user_spot[name] == pytest.approx(baseline[name])
