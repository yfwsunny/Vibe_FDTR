"""Material database: loading, interpolation, and data management."""

from fdtr.materials.schema import Material, MaterialMetadata
from fdtr.materials.loader import load_material, load_materials_dir, resolve_material, try_resolve_material

__all__ = ["Material", "MaterialMetadata", "load_material", "load_materials_dir", "resolve_material", "try_resolve_material"]
