"""Reference-designator drawings: read refdes positions, render pages on demand.

A CAM assembly drawing already carries every reference designator and its
position in the PDF vector text layer. Reading a drawing therefore needs nothing
else: no BOM, no placement coordinate file and no registration step.
"""

from app.backend.refdes.document import open_drawing
from app.backend.refdes.extraction import find_refs, locate_refs
from app.backend.refdes.render import PageRenderer, RenderedPage

__all__ = [
    "PageRenderer",
    "RenderedPage",
    "find_refs",
    "locate_refs",
    "open_drawing",
]
