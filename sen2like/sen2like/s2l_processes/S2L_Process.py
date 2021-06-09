import os
from abc import ABC, abstractmethod

from core import S2L_config


class S2L_Process(ABC):
    def __init__(self):
        self.ext = S2L_config.PROC_BLOCKS.get(self.__class__.__name__, {}).get('extension')
        self.initialize()

    def initialize(self):
        return

    @abstractmethod
    def process(self, pd, image, band: str):
        return None

    def output_file(self, product, band, extension=None):
        if extension is None:
            extension = self.ext
        return os.path.join(S2L_config.config.get('wd'), product.name,
                            product.get_band_file(band).rootname + extension)
