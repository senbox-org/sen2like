# Copyright (c) 2023 ESA.
#
# This file is part of sen2like.
# See https://github.com/senbox-org/sen2like for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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

    def __init__(self, generate_intermediate_products: bool = False):
        """Default constructor.

        Args:
            generate_intermediate_products (bool, optional): flag to generate or not intermediate image products.
            Concrete implementation is responsible to use it and generate the intermediate image.
            Defaults to False.
        """
        self.generate_intermediate_products = generate_intermediate_products
        self.ext = S2L_config.PROC_BLOCKS.get(self.__class__.__name__, {}).get(
            "extension"
        )

    def preprocess(self, product: S2L_Product):
        """Do some preprocess on / for the product

        Args:
            product (S2L_Product): product to preprocess
        """
        # deliberately empty

    @abstractmethod
    def process(
        self, product: S2L_Product, image: S2L_ImageFile, band: str
    ) -> S2L_ImageFile:
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
        return os.path.join(
            product.working_dir,
            product.get_band_file(band).rootname + extension,
        )
