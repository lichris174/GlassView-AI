"""Blur the whole screen, every time.

Perfect recall and a 100% false-blur rate by construction. It anchors one end
of the privacy-vs-usefulness trade-off: any useful system must keep most of
this recall while blurring far less.
"""

from __future__ import annotations

from PIL import Image

from ..labels import Box


class BlockAll:
    name = "block_all"
    config: dict = {}

    def predict(self, image: Image.Image) -> list[Box]:
        # The class is irrelevant: privacy metrics ignore predicted classes.
        return [Box("credential", 0, 0, image.width, image.height)]
