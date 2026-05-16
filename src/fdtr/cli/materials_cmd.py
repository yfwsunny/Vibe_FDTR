"""CLI subcommands for material library inspection."""

from __future__ import annotations

import argparse
import warnings


def run_list_materials(args: argparse.Namespace) -> None:
    """List all available materials with temperature ranges and data point counts."""
    from fdtr.materials.loader import _BUILTIN_DATA_DIR, load_materials_dir

    mats = load_materials_dir(_BUILTIN_DATA_DIR)
    if not mats:
        print("No materials found.")
        return

    print(f"{'Material':<22s} {'Symmetry':<22s} {'T range (K)':>16s}  {'Points':>7s}  Source")
    print("-" * 94)
    for name, mat in sorted(mats.items()):
        source = mat.metadata.source if mat.metadata else ""
        if len(source) > 35:
            source = source[:32] + "..."
        print(
            f"{name:<22s} {mat.symmetry:<22s} "
            f"{mat.T_min:>7.0f}-{mat.T_max:<7.0f}  {mat.n_points:>7d}  {source}"
        )


def run_show_material(args: argparse.Namespace) -> None:
    """Show detailed material properties at a given temperature."""
    from fdtr.materials.loader import resolve_material

    mat = resolve_material(args.name)
    T = args.temperature

    print(f"Material: {mat.name}")
    print(f"  Symmetry: {mat.symmetry}")
    if mat.metadata:
        if mat.metadata.source:
            print(f"  Source: {mat.metadata.source}")
        if mat.metadata.author:
            print(f"  Author: {mat.metadata.author}")
    print(f"  T range: {mat.T_min:.1f} - {mat.T_max:.1f} K ({mat.n_points} points)")
    print()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rho_cp = mat.get_property_at_T(T, "rho_cp")
        Sz = mat.get_property_at_T(T, "Sz")
        Sr = mat.get_property_at_T(T, "Sr")

    print(f"  At T = {T:.1f} K:")
    print(f"    rho_cp = {rho_cp:.4e} J/m^3K")
    if mat.symmetry == "isotropic":
        print(f"    S      = {Sr:.4f} W/mK")
    else:
        print(f"    Sz     = {Sz:.4f} W/mK  (cross-plane)")
        print(f"    Sr     = {Sr:.4f} W/mK  (in-plane)")

    if mat.n_points < 5:
        print(f"\n  WARNING: Only {mat.n_points} data point(s). Values may be unreliable.")
    if T < mat.T_min or T > mat.T_max:
        print(f"\n  WARNING: T={T} K is outside data range [{mat.T_min:.0f}, {mat.T_max:.0f}] K.")
