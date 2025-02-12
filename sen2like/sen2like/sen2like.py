#! /usr/bin/env python
# -*- coding: utf-8 -*-
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


"""Main entry point for the sen2like application."""

import datetime
import logging
import os
import sys
from argparse import Namespace
from multiprocessing import Pool

from core import log
from core.argparser import Mode, S2LArgumentParser
from core.product_archive import product_selector
from core.product_archive.product_archive import InputProduct, InputProductArchive
from core.product_preparation import ProductPreparator
from core.product_process import ProductProcess
from core.products.product import ProcessingContext, S2L_Product
from core.reference_image import get_ref_image
from core.S2L_config import config
from core.sen2cor_client.sen2cor_client import Sen2corClient, Sen2corError
from version import __version__

logger = logging.getLogger('Sen2Like')


def filter_product(product: S2L_Product):
    """ Filter on product after created them base on cloud cover
    :param product: a core.product.S2L_Product
    :return: bool
    """
    cloud_cover = config.getfloat('cloud_cover')
    if float(product.mtl.cloud_cover) > cloud_cover:
        logger.warning('cloud cover > %s : %s', cloud_cover, product.mtl.cloud_cover)
        return False
    return True


def pre_process_atmcor(s2l_product: S2L_Product, tile) -> S2L_Product|None:
    """
    Adapt processing parameters for atmo corr processing to use.
    THIS FUNCTION MODIFY SOME `s2l_product.context` PARAMETERS (use_sen2cor, doAtmcor, doStitching, doInterCalibration)
    Run sen2cor if configured for (doAtmcor=True activated and use_sen2cor=True) and if product is compatible.
    Otherwise, configures exec parameters to use smac if product is compatible in case doAtmcor is activated
    Args:
        s2l_product (S2L_Product): s2l_product to check atmo corr compatibility and run sen2cor on
        tile (str): tile name for sen2cor

    Returns:
        s2l_product after sen2cor if executed or provided s2l_product, or None if sen2cor fail
    """
    use_sen2cor = s2l_product.context.doAtmcor and s2l_product.context.use_sen2cor

    # Avoid sen2cor for very old LS products (not collection product)
    if 'L8' in s2l_product.sensor and not s2l_product.mtl.collection_number.isdigit():
        # can only use SMAC for these product_urls, so force SMAC in case doAtmcor=True
        use_sen2cor = False
        s2l_product.context.use_sen2cor = use_sen2cor
        logger.info("For Landsat 8-9, apply sen2cor only on collection 1 & 2 product_urls")

    if use_sen2cor:
        logger.info("Use sen2cor instead of Atmcor SMAC")

        do_sen2cor_topo_corr = (
            s2l_product.context.doTopographicCorrection and
            s2l_product.context.sen2cor_topographic_correction
        )

        sen2cor = Sen2corClient(
            os.path.abspath(config.get('sen2cor_path')),
            tile,
            do_sen2cor_topo_corr
        )

        # Disable SMAC Atmospheric correction
        s2l_product.context.doAtmcor = False

        # For now, do not enable stitching when sen2cor is used
        s2l_product.context.doStitching = False

        # Should be done before atmospheric correction
        # and only for S2B with baseline before 4, so disable it.
        # since collection 1 S2A and S2B are intercalibrated
        # we should keep it disabled
        s2l_product.context.doInterCalibration = False

        # Disable sen2like topographic correction processing block if enabled in sen2cor
        if (s2l_product.context.doTopographicCorrection and
            s2l_product.context.sen2cor_topographic_correction):
            logger.info(
                "Disable sen2like topographic correction processing block because done with sen2cor"
            )
            s2l_product.context.doTopographicCorrection = False

        try:
            orig_processing_sw = s2l_product.mtl.processing_sw

            # run sen2cor on product and instantiate a new one from result
            s2l_product = s2l_product.__class__(
                sen2cor.run(s2l_product),
                s2l_product.context
            )

            # restore L1 "orig" processing version (processing baseline for S2)
            # because sen2cor sets by default the processing baseline to 99.99
            # however L1 "orig" processing version information could be needed for future processing block.
            # example: for intercalibration to know if S2B intercalibration was already applied, not to apply it twice
            s2l_product.mtl.processing_sw = orig_processing_sw

            # set AC QI param
            s2l_product.metadata.qi["AC_PROCESSOR"] = "SEN2COR"

        except Sen2corError:
            logger.warning("sen2cor raises an error", exc_info=True)
            return None
    else:
        logger.info("sen2cor disabled")

    return s2l_product


def process_no_run(tile: str, input_products: list[InputProduct]):
    """no run execution

    Args:
        tile (str): tile name
        input_products (List[InputProduct]): list of product that should be processed
    """
    logger.info("Tile: %s", tile)
    if not input_products:
        logger.info("No product_urls found.")
    for product in input_products:
        tile_message = f'[ Tile coverage = {100*product.tile_coverage:6.0f}% ]' \
            if product.tile_coverage is not None else ''
        cloud_message = f'[ Cloud coverage = {product.cloud_cover:6.0f}% ]' \
            if product.cloud_cover is not None else ''
        logger.info("%s %s %s", tile_message, cloud_message, product.path)


def process_an_input_product(tile, input_product, conf, args, tile_ref_image):

    processing_context = ProcessingContext(conf, tile)

    # instantiate S2L_Product
    s2l_product = input_product.s2l_product_class(
        input_product.path,
        processing_context
    )

    product_name = s2l_product.name

    # cloud cover condition not fulfilled
    if not filter_product(s2l_product):
        logger.info("Skip product %s", product_name)
        return

    # TODO: find a way to do it in ProcessingContext
    # Problem is that we do not have the product when ProcessingContext is instantiated
    # and the product is not supposed to update the context.
    # if processing_context.doAtmcor and s2l_product.mtl.data_type in ["Level-2A", "L2A"]:
    #     logger.warning("L2A product, force disabling Atmo Corr")
    #     processing_context.doAtmcor = False

    if processing_context.doAtmcor:
        # run sen2cor if any and update s2l_product.context
        s2l_product = pre_process_atmcor(s2l_product, tile)

        # sen2cor fail
        if not s2l_product:
            logger.info("Skip product %s due to sen2cor failure", product_name)
            return

        # cloud cover condition not fulfilled for sen2cor output product
        if not filter_product(s2l_product):
            logger.info("Skip product %s", s2l_product.path)
            return

    # product is sen2cor preprocessed
    # mainly for S2 L2A as input, but also match LS L2A from sen2cor
    if s2l_product.mtl.l2a_qi_report_path:
        s2l_product.metadata.qi["AC_PROCESSOR"] = "SEN2COR"

    # Configure a product preparator
    product_preparator = ProductPreparator(conf, args, tile_ref_image)

    # execute processing block on product
    process = ProductProcess(
        s2l_product, product_preparator, args.parallelize_bands, args.bands)
    process.run()

    # clean process
    if s2l_product.related_product is not None:
        del s2l_product.related_product
    del s2l_product


def process_tile(tile: str, search_urls: list[tuple], args: Namespace, start_date: datetime.datetime,
                  end_date: datetime.datetime):
    """
    Process products on the tile for a period
    All products are not processed, only the one on the period, see InputProductArchive.search_product
    Args:
        tile (str): tile name
        search_urls (list(tuple)): list of products search urls.
        args (argparse.Namespace): program arguments
        start_date (datetime.datetime): start date period to process
        end_date (datetime.datetime): end date to process (include)

    Returns:

    """
    logger.info("Processing tile %s", tile)
    # Get input product list
    archive = InputProductArchive(config)
    input_products_list = archive.search_product(
        search_urls, tile, start_date, end_date,
        product_mode=args.operational_mode == Mode.PRODUCT
    )

    logger.debug("Selected products: %s", [p.path for p in input_products_list])

    if args.no_run:
        process_no_run(tile, input_products_list)
        return

    if len(input_products_list) == 0:
        logger.error('No product for tile %s', tile)
        return

    # get ref image for tile
    _tile_ref_image = get_ref_image(args.refImage, config.get('references_map'), tile)

    # Avoid atmocor for L2A in product mode because this mode does not have --l2a option
    # TODO: need refactor to better handles this case by having another way to process product-mode
    # instead of use the current function and also avoid to have to use InputProductArchive.search_product
    # for product-mode (no sense)
    if args.operational_mode == Mode.PRODUCT and "L2" in input_products_list[0].path: # first should be S2 product
        logger.warning('%s with a L2A product, force s2_processing_level to LEVEL2A', Mode.PRODUCT)
        config.set('s2_processing_level', 'LEVEL2A')

    # group products by instrument to process them by instrument
    # BE CAREFULL, it assumes that input_products_list is well sorted
    # (S2 first and then by acquisition date)
    grouped_by_instrument = {}
    for input_product in input_products_list:
        if input_product.instrument not in grouped_by_instrument:
            grouped_by_instrument[input_product.instrument] = [input_product]
        else:
            grouped_by_instrument[input_product.instrument].append(input_product)

    logger.debug("Products groupby instrument: %s", grouped_by_instrument)

    # Process by instrumenbt, by this way be sure to have complete S2_L2H/F
    # for fuion before starting process other instrument/mission when band parell process is enabled
    for instrument, input_products in grouped_by_instrument.items():

        logger.info("Start to process %s products", instrument)
        for input_product in input_products:
            # log here because process_an_input_product can skip the product
            logger.info("Start to process input product %s", input_product.path)
            process_an_input_product(tile, input_product, config, args, _tile_ref_image)
            logger.info("End process for input product %s", input_product.path)

        logger.info("Process of %s products finish", instrument)


def process_concurrent_multi_tile(args, date_range, search_urls):
    """
    Process each tile in a separate (concurrent) process.
    Number of process depends of `number_of_process` config param and `jobs` argument
    The lower is kept for safety
    """

    number_of_process = int(config.get("number_of_process", 1))
    if args.jobs > number_of_process:
        logger.warning(
            "Number of jobs (%s) higher than `number_of_process` config param (%s), reduce it to (%s)",
            args.jobs,
            number_of_process,
            number_of_process
        )
    else:
        number_of_process = args.jobs

    logger.info("Use multi processing (%s concurrent)", number_of_process)

    params = [(tile, _search_url, args, date_range.start_date, date_range.end_date)
                for tile, _search_url in search_urls.items()]
    with Pool(number_of_process) as pool:
        pool.starmap(process_tile, params)


def main(args):
    """Sen2like entry point function"""

    start = datetime.datetime.now(datetime.UTC)
    parser = S2LArgumentParser(os.path.dirname(__file__))
    args = parser.parse_args(args)

    if args.operational_mode is None:
        print(f"Sen2like {__version__} with Python {sys.version}")
        parser.print_help()
        return 1

    log.configure_loggers(logger, log_path=args.wd, is_debug=args.debug, without_date=args.no_log_date)
    logger.info("Run Sen2like %s with Python %s", __version__, sys.version)

    # get product search urls
    config.update_with_args(args)
    date_range = parser.get_date_range()
    search_urls = product_selector.get_search_url(args, date_range)

    if search_urls is None:
        return 1

    if args.operational_mode == Mode.MULTI_TILE and args.jobs > 1 and not args.no_run:
        process_concurrent_multi_tile(args, date_range, search_urls)
    else:
        if args.no_run:
            logger.info("No-run mode: Products will only be listed")
        for tile, _search_url in search_urls.items():
            process_tile(tile, _search_url, args, date_range.start_date, date_range.end_date)

    if not args.no_run:
        logger.info("total processing time : %s", str(datetime.datetime.now(datetime.UTC) - start))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
