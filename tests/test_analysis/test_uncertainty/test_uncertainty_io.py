# tests/test_uncertainty_io.py
import pytest
import tempfile
import json
import numpy as np
from fdtr.analysis.uncertainty.engine import UncertaintyResult
from fdtr.analysis.uncertainty.prepare import load_fit_result, update_layers_from_params
from fdtr.analysis.uncertainty.output import format_result, save_result
from fdtr.input.config import FitConfig
from fdtr.input.config.config_io import _from_dict
from fdtr.analysis.uncertainty.prepare import resolve_uncertainty_params


class TestUncertaintyIO:
    def test_load_fit_result(self):
        """Test loading fit result from JSON file (optimal_params fallback)"""
        fit_result = {
            "strategy": "freqfit",
            "optimal_params": {
                "TBC_1": 10e7,
                "Sz_2": 5.46
            },
            "fixed_params": {
                "Sr_0": 140,
                "d_0": 73e-9,
                "spot_size": 2.84e-6
            },
            "x_data": [5e4, 1e5, 2e7],
            "layers": [
                {"Sr": 140, "Sz": 140, "d": 73e-9, "rho_cp": 2.49e6},
                {"rho_cp": 0, "Sr": 10e7, "Sz": 10e7, "d": 1},
                {"Sr": 1856, "Sz": 5.46, "d": 1, "rho_cp": 1.8e6}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(fit_result, f)
            filename = f.name

        try:
            config, x_data, fitted_values = load_fit_result(filename)

            assert config["uncertainty"]["target_params"] == ["TBC_1", "Sz_2"]
            assert x_data is None  # config-driven x_data
            assert fitted_values == {"TBC_1": 10e7, "Sz_2": 5.46}
            assert config["layer"] == []  # minimal config, layers from --config
        finally:
            import os
            os.unlink(filename)


class TestUncertaintyOutput:
    def test_format_result(self):
        """Test formatting result as human-readable string"""
        result = UncertaintyResult(
            target_params=["TBC_1", "Sz_2"],
            relative_uncertainties={"TBC_1": 0.15, "Sz_2": 0.08}
        )

        output = format_result(result)
        assert "TBC_1" in output
        assert "15.00%" in output
        assert "Sz_2" in output
        assert "8.00%" in output

    def test_save_result(self):
        """Test saving result to JSON file"""
        result = UncertaintyResult(
            target_params=["TBC_1", "Sz_2"],
            relative_uncertainties={"TBC_1": 0.15, "Sz_2": 0.08},
            covariance_matrix=np.array([[0.01, 0.002], [0.002, 0.005]])
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filename = f.name

        try:
            save_result(result, filename, include_full=True)

            import json
            with open(filename, 'r') as f:
                data = json.load(f)

            assert data["target_params"] == ["TBC_1", "Sz_2"]
            assert data["relative_uncertainties"]["TBC_1"] == 0.15
            assert data["relative_uncertainties"]["Sz_2"] == 0.08
            assert "covariance_matrix" in data
        finally:
            import os
            os.unlink(filename)


class TestUncertaintyParameters:
    def test_resolve_uncertainty_params(self):
        config_dict = {
            "uncertainty": {
                "target_params": ["TBC_1", "Sz_2"],
                "known_params": {
                    "Sr_0": 0.1,
                    "d_0": 0.05,
                    "spot_size": 0.03
                }
            },
            "layer": [
                {"Sr": 140, "Sz": 140, "d": 73e-9, "rho_cp": 2.49e6},
                {"rho_cp": 0, "Sr": 10e7, "Sz": 10e7, "d": 1},
                {"Sr": 1856, "Sz": 5.46, "d": 1, "rho_cp": 2.2e6}
            ],
            "fit": {"spot_size": 2.84},
        }

        fit_config = _from_dict(config_dict)
        uncertainty_config = config_dict["uncertainty"]

        target_params, known_params = resolve_uncertainty_params(fit_config, uncertainty_config)

        assert len(target_params) == 2
        assert target_params[0].raw_name == "TBC_1"
        assert target_params[1].raw_name == "Sz_2"

        assert len(known_params) == 7
        assert known_params["Sr_0"]["value"] == 140
        assert known_params["Sr_0"]["uncertainty"] == 0.1
        assert known_params["d_0"]["value"] == 73e-9
        assert known_params["d_0"]["uncertainty"] == 0.05
        assert known_params["spot_size"]["value"] == 2.84
        assert known_params["spot_size"]["uncertainty"] == 0.03

    def test_resolve_uncertainty_params_infers_targets_from_fit_fields(self):
        config_dict = {
            "uncertainty": {
                "known_params": {}
            },
            "layer": [
                {"Sr": 140, "Sz": 140, "d": 73e-9, "rho_cp": 2.49e6},
                {"rho_cp": 0, "Sr": 10e7, "Sz": 10e7, "d": 1, "fit_TBC": [1e6, 1e8]},
                {"Sr": 1856, "Sz": 5.46, "d": 1, "rho_cp": 2.2e6, "fit_Sz": [1.0, 20.0]},
            ],
            "fit": {"spot_size": 2.84},
        }

        fit_config = _from_dict(config_dict)

        target_params, _known_params = resolve_uncertainty_params(
            fit_config, config_dict["uncertainty"]
        )

        assert [param.raw_name for param in target_params] == ["TBC_1", "Sz_2"]

    def test_resolve_uncertainty_params_requires_scalar_spot_size(self):
        config_dict = {
            "uncertainty": {
                "target_params": ["Sz_2"],
                "known_params": {}
            },
            "layer": [
                {"Sr": 140, "Sz": 140, "d": 73e-9, "rho_cp": 2.49e6},
                {"rho_cp": 0, "Sr": 10e7, "Sz": 10e7, "d": 1},
                {"Sr": 1856, "Sz": 5.46, "d": 1, "rho_cp": 2.2e6}
            ],
            "fit": {"spot_x": 2.8, "spot_y": 3.2},
        }
        fit_config = _from_dict(config_dict)

        with pytest.raises(ValueError, match=r"uncertainty analysis requires \[fit\] spot_size"):
            resolve_uncertainty_params(fit_config, config_dict["uncertainty"])

    def test_resolve_uncertainty_params_warns_and_uses_one_spot_known(self):
        config_dict = {
            "uncertainty": {
                "target_params": ["Sz_2"],
                "known_params": {
                    "spot_size": 0.03,
                    "spot_x": 0.10,
                    "spot_y": 0.20,
                    "d_0": 0.05,
                },
            },
            "layer": [
                {"Sr": 140, "Sz": 140, "d": 73e-9, "rho_cp": 2.49e6},
                {"rho_cp": 0, "Sr": 10e7, "Sz": 10e7, "d": 1},
                {"Sr": 1856, "Sz": 5.46, "d": 1, "rho_cp": 2.2e6},
            ],
            "fit": {"spot_size": 2.84},
        }
        fit_config = _from_dict(config_dict)

        with pytest.warns(UserWarning, match=r"Multiple spot known_params"):
            _target_params, known_params = resolve_uncertainty_params(
                fit_config, config_dict["uncertainty"]
            )

        spot_known = {"spot_size", "spot_x", "spot_y"} & set(known_params)
        assert spot_known == {"spot_size"}
        assert known_params["spot_size"]["uncertainty"] == pytest.approx(0.03)

    def test_resolve_uncertainty_params_warns_and_excludes_spot_known_for_spot_target(self):
        config_dict = {
            "uncertainty": {
                "target_params": ["spot_size"],
                "known_params": {
                    "spot_size": 0.03,
                    "spot_x": 0.10,
                    "d_0": 0.05,
                },
            },
            "layer": [
                {"Sr": 140, "Sz": 140, "d": 73e-9, "rho_cp": 2.49e6},
                {"rho_cp": 0, "Sr": 10e7, "Sz": 10e7, "d": 1},
                {"Sr": 1856, "Sz": 5.46, "d": 1, "rho_cp": 2.2e6},
            ],
            "fit": {"spot_size": 2.84},
        }
        fit_config = _from_dict(config_dict)

        with pytest.warns(UserWarning, match=r"ignored.*spot.*target"):
            _target_params, known_params = resolve_uncertainty_params(
                fit_config, config_dict["uncertainty"]
            )

        assert {"spot_size", "spot_x", "spot_y"}.isdisjoint(known_params)

    def test_resolve_uncertainty_params_rejects_empty_targets(self):
        config_dict = {
            "uncertainty": {
                "known_params": {}
            },
            "layer": [
                {"Sr": 140, "Sz": 140, "d": 73e-9, "rho_cp": 2.49e6},
                {"Sr": 1856, "Sz": 5.46, "d": 1, "rho_cp": 2.2e6},
            ],
            "fit": {"spot_size": 2.84},
        }

        fit_config = _from_dict(config_dict)

        with pytest.raises(ValueError, match="target_params"):
            resolve_uncertainty_params(fit_config, config_dict["uncertainty"])


class TestUpdateLayers:
    def test_update_Sr_layer2(self):
        layers = [
            {"Sr": 140, "Sz": 140, "d": 7.3e-8, "rho_cp": 2.48e6},
            {"rho_cp": 0, "Sr": 5e7, "Sz": 5e7, "d": 1},
            {"Sr": 1728, "Sz": 5.8, "d": 1, "rho_cp": 1.58e6},
        ]
        update_layers_from_params(layers, {"Sr_2": 2387, "Sz_2": 4.4, "TBC_1": 9.3e7})
        assert layers[2]["Sr"] == 2387
        assert layers[2]["Sz"] == 4.4
        assert layers[1]["Sr"] == 9.3e7
        assert layers[1]["Sz"] == 9.3e7

    def test_spot_params_ignored(self):
        layers = [{"Sr": 100, "Sz": 100, "d": 1e-7, "rho_cp": 1e6}]
        update_layers_from_params(layers, {"spot_x": 2.8, "spot_size": 2.9})
        assert layers[0]["Sr"] == 100

    def test_d_and_rho_cp(self):
        layers = [
            {"Sr": 140, "Sz": 140, "d": 1e-7, "rho_cp": 2.48e6},
        ]
        update_layers_from_params(layers, {"d_0": 7.3e-8, "rho_cp_0": 2.5e6})
        assert layers[0]["d"] == 7.3e-8
        assert layers[0]["rho_cp"] == 2.5e6

    def test_out_of_range_index_ignored(self):
        layers = [{"Sr": 100, "Sz": 100, "d": 1, "rho_cp": 1e6}]
        update_layers_from_params(layers, {"Sr_5": 999})  # index 5 doesn't exist
        assert layers[0]["Sr"] == 100  # unchanged


class TestLoadIterfitResult:
    def test_load_iterfit_result(self):
        """Test loading iterfit-format fit_result.json — returns minimal config."""
        fit_result = {
            "strategy": "iterfit",
            "final_values": {"spot_x": 2.78, "Sr_2": 2387, "Sz_2": 4.4, "TBC_1": 9.3e7, "spot_size": 2.86},
            "history": [],
            "n_iterations": 6,
            "success": True,
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(fit_result, f)
            filename = f.name

        try:
            config, x_data, fitted_values = load_fit_result(filename)
            assert config.get("strategy") == "iterfit"
            assert x_data is None  # iterfit uses config-driven x_data
            assert fitted_values["Sr_2"] == 2387
            assert fitted_values["spot_x"] == 2.78
        finally:
            import os
            os.unlink(filename)

    def test_load_single_mode_still_works(self):
        """Original single-mode format still loads correctly."""
        fit_result = {
            "strategy": "freqfit",
            "optimal_params": {"TBC_1": 10e7, "Sz_2": 5.46},
            "fixed_params": {"Sr_0": 140, "d_0": 73e-9, "spot_size": 2.84e-6},
            "x_data": [5e4, 1e5, 2e7],
            "layers": [
                {"Sr": 140, "Sz": 140, "d": 73e-9, "rho_cp": 2.49e6},
                {"rho_cp": 0, "Sr": 10e7, "Sz": 10e7, "d": 1},
                {"Sr": 1856, "Sz": 5.46, "d": 1, "rho_cp": 1.8e6}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(fit_result, f)
            filename = f.name

        try:
            config, x_data, fitted_values = load_fit_result(filename)
            assert "TBC_1" in config["uncertainty"]["target_params"]
            assert fitted_values["TBC_1"] == 10e7
        finally:
            import os
            os.unlink(filename)

    def test_load_fitted_values_key(self):
        """New-format JSON uses fitted_values key."""
        fit_result = {
            "fitted_values": {"TBC_1": 10e7, "Sz_2": 5.46, "spot_size": 2.84},
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(fit_result, f)
            filename = f.name

        try:
            config, x_data, fitted_values = load_fit_result(filename)
            assert fitted_values["TBC_1"] == 10e7
            assert fitted_values["Sz_2"] == 5.46
            assert config["uncertainty"]["target_params"] == ["TBC_1", "Sz_2", "spot_size"]
        finally:
            import os
            os.unlink(filename)
