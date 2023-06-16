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

"""
Module for 'S2L_Product' process with multiple 'S2L_Process'.
IMPORTANT : Note that multithreading can used, see 'ProductProcess'
"""
import importlib
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from core import S2L_config
from core.product_preparation import ProductPreparator
from core.products.product import S2L_Product
from core.S2L_config import config
from s2l_processes.S2L_Process import S2L_Process

logger = logging.getLogger('Sen2Like')


_PROCESS_INSTANCES = {} # for parallelization
_PROCESS_BLOCK_CLASSES = {}  # OPTIM


# list of the blocks that are available
_list_of_blocks = tuple(S2L_config.PROC_BLOCKS.keys())
# Add building blocks package to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "s2l_processes"))


def _get_processing_block(block_name: str) -> S2L_Process:
    """Get process class associated to block_name.
    If class does not have yet been imported, import it, save it and return it,
    otherwise, return class.

    Args:
        block_name (str): The name of the process block.

    Returns:
        S2L_Process: S2L_Process class
    """
    # import module and class
    _processing_block_class = _PROCESS_BLOCK_CLASSES.get(block_name)
    if _processing_block_class is None:
        module = importlib.import_module(block_name)
        _processing_block_class = getattr(module, block_name)
        _PROCESS_BLOCK_CLASSES[block_name] = _processing_block_class

    return _processing_block_class


# pylint: disable=too-few-public-methods
class ProductProcess:
    """
    Class to process a S2L product.
    The main function 'run' execute eligible processing blocks for the product
    based on the configuration and product context (see 'core.products.productProcessingContext').

    MultiThreading is used for parallelization if enabled. If parallelization is enabled,
    'S2L_Product' object to process and 'S2L_Process' instances are SHARED in memory.
    So 'S2L_Process' concrete classes MUST be coded in consequences.
    """

    def __init__(self,
        product: S2L_Product,
        product_preparator: ProductPreparator,
        parallelize_bands: bool,
        bands: list[str]):
        """Constructor.
        It initializes list of processing block with new instances of eligible concrete S2L_Process

        Args:
            product (S2L_Product): product to process
            product_preparator (ProductPreparator): product preparator service
            parallelize_bands (bool): band processing parallelization flag
            bands (List[str]): list of bands to process, None means all
        """
        self._product = product
        self._product_preparator = product_preparator
        self._parallelize_bands = parallelize_bands
        self._bands = bands
        self._working_dir = product.working_dir
        self._processing_block_list = self._init_block_list()

    def run(self):
        """Process a product:
        - prepare the product thanks to the product preparator service
        - run eligible processing block pre process
        - run eligible processing block process
        - run eligible processing block post process
        """

        # displays
        logger.info('=' * 50)
        logger.info("Process : %s %s", self._product.sensor, self._product.path)

        # Search and attach related product to product
        # only if S2L_Stitching activated, and extract product files
        self._product_preparator.prepare(self._product)

        # !! Pre processing !!
        # Run the preprocessing method of each block
        for proc_block in self._processing_block_list:
            proc_block.preprocess(self._product)

        # !! Processing !!
        bands = self._get_bands()

        bands_filenames = []
        if self._parallelize_bands:
            # concurrent band process
            bands_filenames = self._run_parallel(bands)
        else:
            # Band by band process
            for band in bands:
                # process the band through each block
                bands_filenames.append(self._process_band(band))  # Save image path

        if bands_filenames == [None] * len(bands_filenames):
            logger.error("No valid band provided for input product.")
            logger.error("Valids band for product_urls are: %s", str(list(self._product.bands)))
            return

        # !! Post processing !!
        # Run the postprocessing method of each block
        for proc_block in self._processing_block_list:
            proc_block.postprocess(self._product)

    def _init_block_list(self):
        """Instantiate eligible S2L_Process concrete class (processing bloc).
        A processing bloc is eligible if:
        - Its config param is set to True (doS2Lxxxx=True) in config file.
        - Not set to False in its attribute in product context
        - It is applicable to the product sensor, see `core.S2L_config.PROC_BLOCKS` definition.

        Returns:
            list[S2L_Process]: list of processing block object to run
        """
        processing_block = []
        for block_name in _list_of_blocks:
            _param = 'do' + block_name.split('_')[-1]

            # disable in conf and not override in context
            if not config.getboolean(_param) and not hasattr(self._product.context, _param):
                logger.debug("%s disable by configuration", block_name)
                continue

            # override in context and False
            if hasattr(self._product.context, _param) and not getattr(self._product.context, _param):
                logger.debug("%s disable by configuration", block_name)
                continue

            # check if block is applicable to the sensor (L8, L9 or S2)
            if self._product.sensor not in S2L_config.PROC_BLOCKS[block_name]['applicability']:
                logger.debug("%s not applicable to %s", block_name, self._product.sensor)
                continue

            proc_block_instance = _get_processing_block(block_name)()
            processing_block.append(proc_block_instance)

        return processing_block

    def _run_parallel(self, bands):
        # Concurrent call of _process_band for each band using Thread

        number_of_process = int(config.get('number_of_process', 1))

        bands_filenames = []
        with ThreadPoolExecutor(number_of_process) as executor:
            result = executor.map(self._process_band, bands)

        bands_filenames = list(result)
        return bands_filenames

    def _get_bands(self):

        bands = self._bands
        # For each band or a selection of bands:
        if bands is None:
            # get all bands
            bands = self._product.bands
        else:
            # get product bands corresponding to given S2 bands
            bands = [self._product.reverse_bands_mapping.get(band, band) for band in bands]

        return bands

    def _process_band(self, band: str) -> str|None:
        """Run all the blocks over one band of a product.

        Args:
            band (str): band to process

        Returns:
            str: Last file path of the image generated by the processing chain.
            None if no image for band
        """
        logger.info('--- Process band %s ---', band)

        # get band file path
        image = self._product.get_band_file(band)
        if image is None:
            return None

        # iterate on blocks
        for proc_block in self._processing_block_list:
            logger.info('----- Start %s for band %s -----', proc_block.__class__.__name__, band)
            image = proc_block.process(self._product, image, band)
            logger.info('----- Finish %s for band %s -----', proc_block.__class__.__name__, band)

        return image.filename
