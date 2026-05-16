"""CLI argument definitions for the init-config subcommand."""

from __future__ import annotations

from pathlib import Path


def add_init_config_args(parser) -> None:
    """Register all init-config CLI arguments on *parser*, grouped by category."""

    mode = parser.add_argument_group("模式选择")
    mode.add_argument(
        "--analysis",
        type=str,
        choices=["none", "sensitivity", "uncertainty"],
        default="none",
        help=(
            "Analysis mode: 'none' = base fit config, "
            "'sensitivity' or 'uncertainty' = flat analysis TOML (default: none)"
        ),
    )

    mat = parser.add_argument_group("材料与层结构")
    mat.add_argument(
        "--transducer",
        type=str,
        default="Gold",
        help=(
            "Transducer material, optionally with thickness as Material:Thickness "
            "in meters (default: Gold; e.g. Gold:48e-9)"
        ),
    )
    mat.add_argument(
        "--substrate",
        type=str,
        default="Graphite",
        help="Substrate material name from library (default: Graphite)",
    )
    mat.add_argument(
        "--layer",
        type=str,
        action="append",
        default=None,
        help="Intermediate layer, optionally with thickness as Material:Thickness in meters (repeatable). TBC auto-inserted.",
    )
    mat.add_argument(
        "--temperature",
        type=float,
        default=295.15,
        help="Temperature in Kelvin (default: 295.15)",
    )
    mat.add_argument(
        "--spot-size",
        type=float,
        default=None,
        help="Beam 1/e2 radius in um (default: 3.0)",
    )

    strat = parser.add_argument_group("拟合方法与目标")
    strat.add_argument(
        "--strategy",
        type=str,
        default=None,
        choices=["freqfit", "offsetfit", "spotfit", "iterfit"],
        help=(
            "Fit method. freqfit/offsetfit/spotfit are single-strategy modes. "
            "iterfit is a pipeline framework that combines multiple strategies "
            "in sequence. Required for base config; for analysis mode, falls "
            "back to base-config value if not specified."
        ),
    )
    strat.add_argument(
        "--fit",
        type=str,
        action="append",
        default=None,
        help=(
            'Fit parameter as "Param_N=lo,hi" (repeatable). '
            'e.g. "Sr_2=100,10000" "TBC_1=5e6,5e8" "spot_x=0.3,30"'
        ),
    )

    paths = parser.add_argument_group("数据路径")
    paths.add_argument(
        "--paths-spec",
        type=Path,
        default=None,
        help=(
            "JSON or TOML path spec file. "
            "Accepts scan-data group detail output directly."
        ),
    )
    paths.add_argument(
        "--paths-json",
        type=str,
        default=None,
        help="Inline JSON path spec. Useful for small manual edits or agent-generated input.",
    )

    fit = parser.add_argument_group("拟合设置")
    fit.add_argument(
        "--freq-offset",
        type=float,
        default=None,
        help="Frequency for offset fitting in Hz (default: 1.194e6)",
    )
    fit.add_argument(
        "--freq-spot",
        type=float,
        default=None,
        help="Frequency for spot fitting in Hz (default: 5e7)",
    )
    fit.add_argument(
        "--signal",
        type=str,
        default=None,
        choices=["amplitude", "phase"],
        help="Fit signal type (default: phase)",
    )
    fit.add_argument(
        "--offset-points",
        type=int,
        default=None,
        help="Number of offset points (default: 100)",
    )
    fit.add_argument(
        "--phase-points",
        type=int,
        default=None,
        help="Number of phase points (default: 80)",
    )
    fit.add_argument(
        "--freq-range",
        type=str,
        action="append",
        default=None,
        help='Frequency range as "lo,hi" in Hz. Repeat to specify multiple ranges.',
    )
    fit.add_argument(
        "--offset-range",
        type=str,
        action="append",
        default=None,
        help='Offset range as "lo,hi" in um. Repeat to specify multiple ranges.',
    )

    pipe = parser.add_argument_group("Pipeline")
    pipe.add_argument(
        "--pipeline",
        type=str,
        default=None,
        help="Pipeline name or path (default: 'default' for iterfit)",
    )
    pipe.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Pipeline iterations (default: 6)",
    )

    out = parser.add_argument_group("输出")
    out.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: auto-generates under tasks/)",
    )
    out.add_argument(
        "--full-template",
        action="store_true",
        default=False,
        help="Emit full template with commented optional sections",
    )

    sens = parser.add_argument_group("分析配置 - Sensitivity (--analysis sensitivity)")
    sens.add_argument(
        "--base-config",
        type=str,
        default=None,
        help="Path to base FitConfig TOML (required when --analysis is not 'none')",
    )
    sens.add_argument(
        "--parameters",
        type=str,
        action="append",
        default=None,
        help="Parameter name for sensitivity (repeatable, or 'all')",
    )
    sens.add_argument(
        "--delta",
        type=float,
        default=None,
        help="Perturbation fraction for sensitivity (default: 1e-4)",
    )

    uncert = parser.add_argument_group("分析配置 - Uncertainty (--analysis uncertainty)")
    uncert.add_argument(
        "--fit-result",
        type=str,
        default=None,
        help="Path to fit result JSON (uncertainty mode)",
    )
    uncert.add_argument(
        "--target-params",
        type=str,
        action="append",
        default=None,
        help="Target parameter name for uncertainty (repeatable)",
    )
    uncert.add_argument(
        "--known-param",
        type=str,
        action="append",
        default=None,
        help='Known param as "key=rel_sigma" (repeatable)',
    )
    uncert.add_argument(
        "--full-output",
        action="store_true",
        default=None,
        help="Include full output (covariance matrix, contributions)",
    )
