"""TOML read/write and template generation for FDTR configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from fdtr.input.config._toml_utils import fmt as _fmt, fmt_list as _fmt_list
from fdtr.input.config.config_dataclass import (
    FitConfig,
    LayerSpec,
    SensitivitySpec,
    TargetSpec,
    UncertaintySpec,
    normalize_strategy,
)
from fdtr.model.layer import SYMMETRY_ISOTROPIC, SYMMETRY_TRANSVERSE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def from_toml(path: str | Path) -> FitConfig:
    """Load a :class:`FitConfig` from a TOML file."""
    path = Path(path).resolve()
    with path.open("rb") as f:
        data = tomllib.load(f)
    cfg = _from_dict(data)
    cfg.source_path = str(path)
    return cfg


def to_toml(config: FitConfig, path: str | Path, *, mode: str = "full") -> None:
    """Write *config* to a TOML file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml_string(config, mode=mode), encoding="utf-8")


# ---------------------------------------------------------------------------
# Internal: dict -> FitConfig
# ---------------------------------------------------------------------------


def _from_dict(data: dict) -> FitConfig:
    """Construct from a parsed TOML dictionary."""
    cfg = FitConfig()

    # Top-level scalars
    cfg.temperature = data.get("temperature", cfg.temperature)

    # Layers: [[layer]] array of tables
    _FIT_KEY_MAP = {
        "fit_S": "S", "fit_Sr": "Sr", "fit_Sz": "Sz", "fit_d": "d",
        "fit_rho_cp": "rho_cp", "fit_TBC": "TBC",
    }
    for ld in data.get("layer", []):
        # Parse fit_<prop> fields
        fit_fields: dict[str, tuple[float, float]] = {}
        for toml_key, prop_name in _FIT_KEY_MAP.items():
            if toml_key in ld:
                b = ld[toml_key]
                fit_fields[prop_name] = (float(b[0]), float(b[1]))
        # Track which property fields were explicitly set in TOML.
        explicit: set[str] = set()
        for prop in ("rho_cp", "Sr", "Sz", "S", "d"):
            if prop in ld:
                explicit.add(prop)

        has_s = "S" in ld
        has_sr = "Sr" in ld
        has_sz = "Sz" in ld
        has_rho_cp = "rho_cp" in ld
        is_tbc = ld.get("material") is None and has_rho_cp and float(ld["rho_cp"]) == 0.0

        label = ld.get("name") or ld.get("material") or "?"
        if has_s and (has_sr or has_sz):
            raise ValueError(f"Layer {label}: cannot specify both S and Sr/Sz.")
        if is_tbc and has_s:
            raise ValueError(f"TBC layer {label}: use fit_TBC/TBC_N, not S.")
        if has_s:
            s_val = float(ld["S"])
            sr_val = s_val
            sz_val = s_val
            symmetry = SYMMETRY_ISOTROPIC
            explicit.update({"Sr", "Sz"})
        elif has_sr and has_sz:
            sr_val = float(ld["Sr"])
            sz_val = float(ld["Sz"])
            symmetry = SYMMETRY_TRANSVERSE
        elif has_sr or has_sz:
            if ld.get("material") is None:
                raise ValueError(
                    f"Layer {label}: specify both Sr and Sz, or use a material "
                    "for partial conductivity overrides."
                )
            sr_val = float(ld.get("Sr", 1.0))
            sz_val = float(ld.get("Sz", 1.0))
            symmetry = SYMMETRY_TRANSVERSE
        else:
            sr_val = 1.0
            sz_val = 1.0
            symmetry = SYMMETRY_TRANSVERSE

        if has_s and ("Sr" in fit_fields or "Sz" in fit_fields):
            raise ValueError(f"Layer {label} uses S; use fit_S instead of fit_Sr/fit_Sz.")
        if (has_sr or has_sz) and "S" in fit_fields:
            raise ValueError(f"Layer {label} uses Sr/Sz; use fit_Sr/fit_Sz instead of fit_S.")
        if is_tbc and any(prop in fit_fields for prop in ("S", "Sr", "Sz", "d", "rho_cp")):
            raise ValueError(f"TBC layer {label}: use fit_TBC, not material fit fields.")
        cfg.layers.append(
            LayerSpec(
                name=ld.get("name", ""),
                material=ld.get("material", None),
                rho_cp=ld.get("rho_cp", 0.0),
                Sr=sr_val,
                Sz=sz_val,
                d=ld.get("d", 1.0),
                symmetry=symmetry,
                fit_fields=fit_fields,
                _explicit=frozenset(explicit),
            )
        )

    # Paths
    paths = data.get("paths", {})
    cfg.offset_dir = paths.get("offset_dir", None)
    cfg.phase_dir = paths.get("phase_dir", None)
    cfg.data_file = paths.get("data_file", None)
    cfg.data_file_y = paths.get("data_file_y", None)
    cfg.offset_dir_y = paths.get("offset_dir_y", None)
    cfg.offset_pattern = paths.get("offset_pattern", None)
    cfg.offset_pattern_y = paths.get("offset_pattern_y", None)
    cfg.phase_pattern = paths.get("phase_pattern", None)
    cfg.offset_files = paths.get("offset_files", None)
    cfg.offset_files_y = paths.get("offset_files_y", None)
    cfg.phase_files = paths.get("phase_files", None)
    cfg.output_dir = paths.get("output_dir", None)
    cfg.group_key = paths.get("group_key", None)

    # Fit section
    fit = data.get("fit", {})
    raw_strategy = fit.get("strategy", cfg.strategy)
    cfg.strategy = normalize_strategy(raw_strategy)
    cfg.spot_size = fit.get("spot_size", None)
    cfg.iterations = fit.get("iterations", cfg.iterations)
    cfg.freq_spot = fit.get("freq_spot", cfg.freq_spot)
    cfg.freq_offset = fit.get("freq_offset", cfg.freq_offset)
    cfg.offset_points = fit.get("offset_points", cfg.offset_points)
    cfg.phase_points = fit.get("phase_points", cfg.phase_points)
    cfg.average = fit.get("average", cfg.average)

    # Spot-size fit bounds (new-style)
    for attr, key in [("fit_spot_size", "fit_spot_size"),
                      ("fit_spot_x", "fit_spot_x"),
                      ("fit_spot_y", "fit_spot_y")]:
        val = fit.get(key, None)
        if val is not None:
            setattr(cfg, attr, (float(val[0]), float(val[1])))

    # Targets: [[fit.targets]]
    for td in fit.get("targets", []):
        bounds = tuple(td["bounds"])
        guess = td.get("guess", None)
        cfg.targets.append(
            TargetSpec(name=td["name"], bounds=bounds, guess=guess)
        )

    cfg.signal = fit.get("signal", cfg.signal)
    cfg.pipeline = fit.get("pipeline", None)

    fr_list = fit.get("freq_ranges", None)
    if fr_list is not None:
        cfg.freq_ranges = [(r[0], r[1]) for r in fr_list]

    or_list = fit.get("offset_ranges", None)
    if or_list is not None:
        cfg.offset_ranges = [(r[0], r[1]) for r in or_list]

    sens = data.get("sensitivity", None)
    if sens is not None:
        cfg.sensitivity = SensitivitySpec(
            parameters=list(sens.get("parameters", ["all"])),
            delta=float(sens.get("delta", 1e-4)),
            output_dir=sens.get("output_dir", None),
        )

    unc = data.get("uncertainty", None)
    if unc is not None:
        cfg.uncertainty = UncertaintySpec(
            known_params=dict(unc.get("known_params", {})),
            target_params=list(unc.get("target_params", [])),
            fit_result=unc.get("fit_result", None),
            full_output=bool(unc.get("full_output", False)),
        )

    return cfg


# ---------------------------------------------------------------------------
# Internal: FitConfig -> TOML string
# ---------------------------------------------------------------------------

_STRATEGY_SKIP: dict[str, frozenset[str]] = {
    "freqfit":   frozenset({"pipeline", "iterations", "freq_spot", "freq_offset", "offset_points"}),
    "offsetfit": frozenset({"pipeline", "iterations", "freq_spot", "phase_points"}),
    "spotfit":   frozenset({"pipeline", "iterations", "signal", "freq_offset", "phase_points"}),
}


def _to_toml_string(config: FitConfig, *, mode: str = "full") -> str:
    """Produce a TOML document string from *config* with unit annotations."""
    lines: list[str] = []

    # Temperature
    lines.append(f"temperature = {_fmt(config.temperature)}              # K — 温度")
    lines.append("")

    # Layers
    _PROP_TOML_KEY = {"S": "fit_S", "Sr": "fit_Sr", "Sz": "fit_Sz", "d": "fit_d",
                      "rho_cp": "fit_rho_cp", "TBC": "fit_TBC"}
    for layer in config.layers:
        lines.append("[[layer]]")
        if layer.material is not None:
            lines.append(f'material = {_fmt(layer.material)}            # 从材料库自动查找')
        elif layer.name:
            lines.append(f'name = {_fmt(layer.name)}')
        if layer.is_tbc:
            lines.append(f"rho_cp = {_fmt(layer.rho_cp)}                  # J/m³K — 0.0 标识 TBC 界面层")
            lines.append(f"Sr = {_fmt(layer.Sr)}                    # W/m²K")
            lines.append(f"Sz = {_fmt(layer.Sz)}                    # W/m²K")
        else:
            lines.append(f"rho_cp = {_fmt(layer.rho_cp)}              # J/m³K")
            if layer.symmetry == SYMMETRY_ISOTROPIC:
                lines.append(f"S = {_fmt(layer.Sr)}                     # W/mK")
            else:
                lines.append(f"Sr = {_fmt(layer.Sr)}                    # W/mK")
                lines.append(f"Sz = {_fmt(layer.Sz)}                    # W/mK")
        lines.append(f"d = {_fmt(layer.d)}                     # m")
        # fit_<prop> bounds
        for prop, bounds in layer.fit_fields.items():
            toml_key = _PROP_TOML_KEY.get(prop, f"fit_{prop}")
            if prop == "TBC":
                lines.append(f"{toml_key} = [{_fmt(bounds[0])}, {_fmt(bounds[1])}]      # W/m²K — TBC 拟合 bounds")
            elif prop == "S":
                lines.append(f"{toml_key} = [{_fmt(bounds[0])}, {_fmt(bounds[1])}]      # W/mK — 各向同性 S 拟合 bounds（Sr/Sz 同步）")
            elif prop == "Sr":
                lines.append(f"{toml_key} = [{_fmt(bounds[0])}, {_fmt(bounds[1])}]     # W/mK — Sr 拟合 bounds")
            elif prop == "Sz":
                lines.append(f"{toml_key} = [{_fmt(bounds[0])}, {_fmt(bounds[1])}]      # W/mK — Sz 拟合 bounds")
            else:
                lines.append(f"{toml_key} = [{_fmt(bounds[0])}, {_fmt(bounds[1])}]")
        lines.append("")

    # Paths -- always emit strategy-aware comments
    strategy = normalize_strategy(config.strategy)
    has_paths = any(
        v is not None
        for v in (config.offset_dir, config.phase_dir, config.data_file, config.data_file_y,
                 config.offset_dir_y,
                 config.offset_pattern, config.offset_pattern_y,
                 config.phase_pattern, config.offset_files, config.offset_files_y,
                 config.phase_files, config.output_dir, config.group_key)
    )

    if mode == "full":
        lines.append("")
        lines.append("# ── 数据路径（取消注释并填入实际路径） ──────────────────────────")
        if has_paths:
            lines.append("[paths]")
        else:
            lines.append("# [paths]")

        if config.offset_dir is not None:
            lines.append(f"offset_dir = {_fmt(config.offset_dir)}")
        elif strategy in ("iterfit", "offsetfit"):
            lines.append('# offset_dir = "path/to/offset/data"     # offset 扫描数据目录')

        if config.phase_dir is not None:
            lines.append(f"phase_dir = {_fmt(config.phase_dir)}")
        elif strategy in ("iterfit", "freqfit"):
            lines.append('# phase_dir = "path/to/phase/data"       # 频率扫描数据目录')

        if config.data_file is not None:
            lines.append(f"data_file = {_fmt(config.data_file)}")
        elif strategy == "offsetfit":
            lines.append('# data_file = "path/to/offset.txt"       # 单文件（备选）')
        elif strategy == "spotfit":
            lines.append('# data_file = "path/to/offset_scan.txt"  # offset 扫描数据文件')

        if config.data_file_y is not None:
            lines.append(f"data_file_y = {_fmt(config.data_file_y)}")

        if config.offset_dir_y is not None:
            lines.append(f"offset_dir_y = {_fmt(config.offset_dir_y)}")

        if config.offset_pattern is not None:
            lines.append(f"offset_pattern = {_fmt(config.offset_pattern)}")
        elif config.offset_dir is None:
            lines.append('# offset_pattern = "*xscan*"    # 通配符选择 offset 文件（优先）')

        if config.offset_pattern_y is not None:
            lines.append(f"offset_pattern_y = {_fmt(config.offset_pattern_y)}")

        if config.phase_pattern is not None:
            lines.append(f"phase_pattern = {_fmt(config.phase_pattern)}")
        elif config.phase_dir is None:
            lines.append('# phase_pattern = "*image*"      # 通配符选择 phase 文件')

        if config.offset_files is not None:
            lines.append(f"offset_files = {_fmt_list(config.offset_files)}")
        elif config.offset_dir is None:
            lines.append('# offset_files = ["file1.txt", "file2.txt"]  # 显式文件列表（次之）')

        if config.offset_files_y is not None:
            lines.append(f"offset_files_y = {_fmt_list(config.offset_files_y)}")

        if config.phase_files is not None:
            lines.append(f"phase_files = {_fmt_list(config.phase_files)}")
        elif config.phase_dir is None:
            lines.append('# phase_files = ["file3.txt"]')

        if config.output_dir is not None:
            lines.append(f"output_dir = {_fmt(config.output_dir)}")
        else:
            lines.append('# output_dir = "."    # 输出到 config 所在目录（默认留空即可）')

        if config.group_key is not None:
            lines.append(f"group_key = {_fmt(config.group_key)}")
    else:
        # lean mode: only emit [paths] if has_paths
        if has_paths:
            lines.append("")
            lines.append("[paths]")
            if config.offset_dir is not None:
                lines.append(f"offset_dir = {_fmt(config.offset_dir)}")
            if config.phase_dir is not None:
                lines.append(f"phase_dir = {_fmt(config.phase_dir)}")
            if config.data_file is not None:
                lines.append(f"data_file = {_fmt(config.data_file)}")
            if config.data_file_y is not None:
                lines.append(f"data_file_y = {_fmt(config.data_file_y)}")
            if config.offset_dir_y is not None:
                lines.append(f"offset_dir_y = {_fmt(config.offset_dir_y)}")
            if config.offset_pattern is not None:
                lines.append(f"offset_pattern = {_fmt(config.offset_pattern)}")
            if config.offset_pattern_y is not None:
                lines.append(f"offset_pattern_y = {_fmt(config.offset_pattern_y)}")
            if config.phase_pattern is not None:
                lines.append(f"phase_pattern = {_fmt(config.phase_pattern)}")
            if config.offset_files is not None:
                lines.append(f"offset_files = {_fmt_list(config.offset_files)}")
            if config.offset_files_y is not None:
                lines.append(f"offset_files_y = {_fmt_list(config.offset_files_y)}")
            if config.phase_files is not None:
                lines.append(f"phase_files = {_fmt_list(config.phase_files)}")
            if config.output_dir is not None:
                lines.append(f"output_dir = {_fmt(config.output_dir)}")
            if config.group_key is not None:
                lines.append(f"group_key = {_fmt(config.group_key)}")

    # Fit section
    skip = _STRATEGY_SKIP.get(config.strategy, frozenset())
    lines.append("[fit]")
    lines.append(f"strategy = {_fmt(config.strategy)}")
    if config.pipeline is not None and "pipeline" not in skip:
        lines.append(f"pipeline = {_fmt(config.pipeline)}           # pipeline 名称（default 或自定义 .toml 路径）")
    if config.spot_size is not None:
        lines.append(f"spot_size = {_fmt(config.spot_size)}               # um — 光束 1/e² 半径（值 = 拟合初始猜测）")
    # Spot-size fit bounds (new-style)
    if config.fit_spot_size is not None:
        lines.append(
            f"fit_spot_size = [{_fmt(config.fit_spot_size[0])}, {_fmt(config.fit_spot_size[1])}]  # um — 光斑拟合 bounds"
        )
    if config.fit_spot_x is not None:
        lines.append(
            f"fit_spot_x = [{_fmt(config.fit_spot_x[0])}, {_fmt(config.fit_spot_x[1])}]      # um — X 方向光斑拟合 bounds"
        )
    if config.fit_spot_y is not None:
        lines.append(
            f"fit_spot_y = [{_fmt(config.fit_spot_y[0])}, {_fmt(config.fit_spot_y[1])}]      # um — Y 方向光斑拟合 bounds"
        )
        if config.fit_spot_x is not None and config.fit_spot_y is not None:
            if mode == "full":
                lines.append("# 若不需分别拟合，可用 fit_spot_size 替代上面两行")
    if "iterations" not in skip:
        lines.append(f"iterations = {_fmt(config.iterations)}")
    if "freq_spot" not in skip:
        lines.append(f"freq_spot = {_fmt(config.freq_spot)}             # Hz — 光斑拟合用频率（最高频）")
    if "freq_offset" not in skip:
        lines.append(f"freq_offset = {_fmt(config.freq_offset)}           # Hz — Sr 拟合用频率")
    if "offset_points" not in skip:
        lines.append(f"offset_points = {_fmt(config.offset_points)}")
    if "phase_points" not in skip:
        lines.append(f"phase_points = {_fmt(config.phase_points)}")
    lines.append(f"average = {_fmt(config.average)}              # 多文件取平均拟合（设为 false 使用单文件）")
    if config.signal != "phase" and "signal" not in skip:
        lines.append(f"signal = {_fmt(config.signal)}")
    # Range examples
    has_any_range = (config.freq_ranges is not None or config.offset_ranges is not None)
    if not has_any_range and mode == "full":
        lines.append("# 范围示例（单区间也写成单元素列表）")
        lines.append("# freq_ranges = [[5e4, 2e7]]              # 频率范围 (Hz)")
        lines.append("# offset_ranges = [[-15, 15]]             # 偏移范围 (um)")
    if config.freq_ranges is not None:
        ranges_str = ", ".join(
            f"[{_fmt(r[0])}, {_fmt(r[1])}]" for r in config.freq_ranges
        )
        lines.append(f"freq_ranges = [{ranges_str}]  # Hz")
    if config.offset_ranges is not None:
        ranges_str = ", ".join(
            f"[{_fmt(r[0])}, {_fmt(r[1])}]" for r in config.offset_ranges
        )
        lines.append(f"offset_ranges = [{ranges_str}]  # um")

    # Targets
    for target in config.targets:
        lines.append("")
        lines.append("[[fit.targets]]")
        lines.append(f"name = {_fmt(target.name)}")
        lines.append(
            f"bounds = [{_fmt(target.bounds[0])}, {_fmt(target.bounds[1])}]"
        )
        if target.guess is not None:
            lines.append(f"guess = {_fmt(target.guess)}")

    if config.sensitivity is not None:
        lines.append("")
        lines.append("[sensitivity]")
        lines.append(f"parameters = {_fmt_list(config.sensitivity.parameters)}")
        lines.append(f"delta = {_fmt(config.sensitivity.delta)}")
        if config.sensitivity.output_dir is not None:
            lines.append(f"output_dir = {_fmt(config.sensitivity.output_dir)}")

    if config.uncertainty is not None:
        lines.append("")
        lines.append("[uncertainty]")
        lines.append(f"target_params = {_fmt_list(config.uncertainty.target_params)}")
        if config.uncertainty.known_params:
            items = ", ".join(f"{k} = {_fmt(v)}" for k, v in config.uncertainty.known_params.items())
            lines.append(f"known_params = {{{items}}}")
        else:
            lines.append("known_params = {}")
        if config.uncertainty.fit_result is not None:
            lines.append(f"fit_result = {_fmt(config.uncertainty.fit_result)}")
        lines.append(f"full_output = {_fmt(config.uncertainty.full_output)}")

    lines = _normalize_toml_layout(lines)
    lines.append("")  # trailing newline
    return "\n".join(lines)


def _normalize_toml_layout(lines: list[str]) -> list[str]:
    """Normalize blank lines so adjacent TOML sections have exactly one spacer."""
    normalized: list[str] = []
    previous_blank = False

    for line in lines:
        is_blank = not line.strip()
        if is_blank:
            if not previous_blank:
                normalized.append("")
            previous_blank = True
            continue

        if line.startswith("[") and normalized and normalized[-1] != "":
            normalized.append("")
        normalized.append(line)
        previous_blank = False

    while normalized and normalized[-1] == "":
        normalized.pop()
    return normalized
