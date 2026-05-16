"""Core physics engine: H2D thermal model and layer definitions."""

from fdtr.model.h2d import h2d
from fdtr.model.layer import Layer, MultilayerStack

__all__ = ["Layer", "MultilayerStack", "h2d"]
