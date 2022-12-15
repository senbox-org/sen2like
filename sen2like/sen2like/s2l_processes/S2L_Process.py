"""S2L_Process abstraction definition
"""
import os
from abc import ABC, abstractmethod

from core import S2L_config

from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product


class S2L_Process(ABC):
    """S2L_Process abstract class.
    Implementation MUST implements 'process' and SHOULD override 'preprocess' and 'postprocess'
    """

    def __init__(self):
        self.ext = S2L_config.PROC_BLOCKS.get(self.__class__.__name__, {}).get('extension')
        self.initialize()

    def initialize(self):
        return

    def preprocess(self, product: S2L_Product):
        """Do some preprocess on / for the product

        Args:
            product (S2L_Product): product to preprocess
        """
        # deliberately empty

    @abstractmethod
    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        """Process the product/image/band

        Args:
            pd (S2L_Product): product to process
            image (S2L_ImageFile): image to use to process or to process
            band (str): band to process

        Returns:
            S2L_ImageFile: processing result image
        """
        return None

    def postprocess(self, product: S2L_Product):
        """Do some post process on / for the product.
        This is also a good place to set process metadata.qi params

        Args:
            product (S2L_Product): product to post process
        """
        # deliberately empty

    def output_file(self, product, band, extension=None):
        if extension is None:
            extension = self.ext
        return os.path.join(S2L_config.config.get('wd'), product.name,
                            product.get_band_file(band).rootname + extension)
