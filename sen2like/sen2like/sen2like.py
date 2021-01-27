#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

""" Main entry point for the sen2like application."""

import datetime
import importlib
import json
import logging
import os
import shutil
import subprocess
import sys
from argparse import ArgumentParser
from multiprocessing import Pool

from core import S2L_config, log
from core.QI_MTD.mtd import metadata
from core.S2L_config import config

try:
    from sen2like import BINDIR
except ImportError:
    BINDIR = os.path.dirname(__file__)

import core.products  # Todo: Try to get rid of that
from core.product_archive.product_archive import InputProductArchive, is_spatialite_supported, read_polygon_from_json
from version import __version__

# Add building blocks to Python path
sys.path.append(os.path.join(BINDIR, "s2l_processes"))

logger = logging.getLogger('Sen2Like')

PROCESS_INSTANCES = {}  # OPTIM


def get_module(blockname):
    """Get process class associated to blockname.

    :param blockname: The name of the process to instanciate.
    :return: The instanciated process
    """
    # import module and class
    class_instance = PROCESS_INSTANCES.get(blockname)
    if class_instance is None:
        module = importlib.import_module(blockname)
        class_instance = getattr(module, blockname)()
        PROCESS_INSTANCES[blockname] = class_instance

    return class_instance


def generic_process_step(blockname, pd, process_step):
    """From the name of the block, import the module, get the class,
    create object from class, run the process step method of object.
    This supposes that there all the names are the same (e.g. S2L_GeometryKLT)

    :param blockname: The block to process
    :param pd:
    :param process_step: The step to process
    :return:
    """

    # check if block is switch ON
    if not config.getboolean('do' + blockname.split('_')[-1]):
        return

    # check if block is applicable to the sensor (L8 or S2)
    if pd.sensor not in S2L_config.PROC_BLOCKS[blockname]['applicability']:
        return

    class_instance = get_module(blockname)

    # create object and run preprocess if method exists!
    processus = getattr(class_instance, process_step, None)
    if processus is not None:
        return processus(pd)


def generic_process_band(blockname, pd, image, band):
    """
    from the name of the block, import the module, get the class,
    create object from class, run the main method of object.
    This supposes that there all the names are the same (e.g. S2L_GeometryKLT)
    """

    # check if block is switch ON
    logger.debug(config.getboolean('do' + blockname.split('_')[-1]))
    if not config.getboolean('do' + blockname.split('_')[-1]):
        return image

    # check if block is applicable to the sensor (L8 or S2)
    if pd.sensor not in S2L_config.PROC_BLOCKS[blockname]['applicability']:
        return image

    class_instance = get_module(blockname)

    # create object and run it!
    return class_instance.process(pd, image, band)


def process_band(pd, band, list_of_blocks):
    """Function for running all the blocks over one band."""

    # get band file path
    image = pd.get_band_file(band)
    if image is None:
        return None

    # iterate on blocks
    for block_name in list_of_blocks:
        image = generic_process_band(block_name, pd, image, band)

    # return output
    return image.filename


def update_configuration(args, tile=None):
    # init S2L_config and save to wd
    if not config.initialize(args.S2L_configfile):
        return

    if args.confParams is not None:
        config.overload(args.confParams)
    config.set('wd', os.path.join(args.wd, str(os.getpid())))
    references_map_file = config.get('references_map')
    if args.refImage:
        config.set('refImage', args.refImage)
    elif references_map_file and tile:
        # load dataset
        with open(references_map_file) as j:
            references_map = json.load(j)
        config.set('refImage', references_map.get(tile))
    else:
        config.set('refImage', None)
    config.set('hlsplus', config.getboolean('doPackager') or config.getboolean('doPackagerL2F'))
    config.set('debug', args.debug)
    config.set('generate_intermediate_products', args.generate_intermediate_products)
    if hasattr(args, 'l2a'):
        config.set('s2_processing_level', 'LEVEL2A' if args.l2a else "LEVEL1C")


def configure_sen2like(args):
    """Initialize application configuration.

    :param args: The application parameters.
    :return: The product to process
    """
    update_configuration(args)

    # Are we in tile mode ?
    if args.operational_mode in ['single-tile-mode', 'multi-tile-mode']:
        start_date = datetime.datetime.strptime(args.start_date, "%Y-%m-%d") if args.start_date else args.start_date
        end_date = datetime.datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else args.end_date

        if args.operational_mode == 'multi-tile-mode':
            if not is_spatialite_supported():
                logger.error("Spatialite support is not available. Cannot determine MGRS tiles from ROI.")
                return
            json_file = args.roi
            polygon = read_polygon_from_json(json_file)
            if polygon is not None:
                tiles = InputProductArchive.roi_to_tiles(polygon)
            else:
                tiles = []
        else:
            polygon = None
            tiles = [args.tile]

        downloader = InputProductArchive(config, roi=polygon)
        products = {tile: [url for url in downloader.get_products_url_from_tile(tile, start_date, end_date)] for tile in
                    tiles}
        if not products:
            logger.error("No product found. Exiting application...")
            return
    else:
        start_date = end_date = None
        products = {args.tile: [(args.product, 100)]}
        tiles = [args.tile]

    # Filter on original tiles:
    products = {tile: item for (tile, item) in products.items() if tile in tiles}
    return products, start_date, end_date


def start_process(tile, products, args, start_date, end_date):
    update_configuration(args, tile)
    config.set('tile', tile)
    logger.debug("Processing tile {}".format(tile))
    downloader = InputProductArchive(config)
    _products = downloader.get_products_from_urls(products, start_date, end_date,
                                                  product_mode=args.operational_mode == 'product-mode')
    if args.no_run:
        logger.info("Tile: %s" % tile)
        if not _products:
            logger.info("No products found.")
        for product in _products:
            tile_message = f'[ Tile coverage = {product.tile_coverage:6.0f}% ]' if product.tile_coverage is not None else ''
            cloud_message = f'[ Cloud coverage = {product.cloud_cover:6.0f}% ]' if product.cloud_cover is not None else ''
            logger.info("%s %s %s" % (tile_message, cloud_message, product.path))
        return

    for product in _products:
        _product = None

        if config.getboolean('use_sen2cor'):
            # Disable Atmospheric correction
            config.overload('doAtmcor=False')

            # Run sen2core
            logger.debug("<<< RUNNING SEN2CORE... >>>")
            sen2cor_command = os.path.abspath(config.get('sen2cor_path'))
            sen2cor_output_dir = os.path.join(config.get('wd'), 'sen2cor', os.path.basename(product.path))
            if not os.path.exists(sen2cor_output_dir):
                os.makedirs(sen2cor_output_dir)
            try:
                subprocess.run(['python', sen2cor_command, product.path, "--output_dir", sen2cor_output_dir,
                                "--work_dir", sen2cor_output_dir,
                                "--sc_only"], check=True)
            except subprocess.CalledProcessError as run_error:
                logger.error("An error occurred during the run of sen2cor")
                logger.error(run_error)
                continue
            # Read output product
            generated_product = next(os.walk(sen2cor_output_dir))[1]
            if len(generated_product) != 1:
                logger.error("Sen2Cor error: Cannot get output product")
                continue
            _product = product.reader(os.path.join(sen2cor_output_dir, generated_product[0]))

        if _product is None:
            _product = product.reader(product.path)

        # Update processing configuration
        config.set('productName', _product.name)
        config.set('sensor', _product.sensor)
        config.set('observation_date', _product.mtl.observation_date)
        config.set('relative_orbit', _product.mtl.relative_orbit)
        config.set('absolute_orbit', _product.mtl.absolute_orbit)
        config.set('mission', _product.mtl.mission)

        # Disable Atmospheric correction for Level-2A products
        atmcor = config.get('doAtmcor')
        if _product.mtl.data_type in ('Level-2A', 'L2TP'):
            config.overload('s2_processing_level=LEVEL2A')
            logger.info("Processing Level-2A product: Atmospheric correction is disabled.")
            config.overload('doAtmcor=False')
        else:
            config.overload('s2_processing_level=LEVEL1C')

        process(_product, args.bands)

        # Restore atmcor status
        config.overload(f'doAtmcor={atmcor}')
        del _product
    if len(_products) == 0:
        logger.error('No product for tile %s' % tile)


def process(product, bands):
    """Launch process on product."""

    # create working directory and save conf (traceability)
    if not os.path.exists(os.path.join(config.get("wd"), product.name)):
        os.makedirs(os.path.join(config.get("wd"), product.name))

    # displays
    logger.debug("{} {}".format(product.sensor, product.path))

    # list of the blocks that are available
    list_of_blocks = S2L_config.PROC_BLOCKS.keys()

    # copy MTL files in wd
    wd = os.path.join(config.get("wd"), product.name)
    # copy MTL files in final product
    shutil.copyfile(product.mtl.mtl_file_name, os.path.join(wd, os.path.basename(product.mtl.mtl_file_name)))
    if product.mtl.tile_metadata:
        shutil.copyfile(product.mtl.tile_metadata, os.path.join(wd, os.path.basename(product.mtl.tile_metadata)))

    # Angles extraction
    product.mtl.get_angle_images(os.path.join(config.get("wd"), product.name, 'tie_points.tif'))
    product.mtl.get_valid_pixel_mask(os.path.join(config.get("wd"), product.name, 'valid_pixel_mask.tif'))

    # !! Initialization of each block
    for block_name in list_of_blocks:
        get_module(block_name).initialize()

    # !! Pre processing !!
    # Run the preprocessing method of each block
    for block_name in list_of_blocks:
        generic_process_step(block_name, product, "preprocess")

    # !! Processing !!
    # save S2L_config file in wd
    config.savetofile(os.path.join(config.get('wd'), product.name, 'processing_start.cfg'))

    # For each band or a selection of bands:
    if bands is None:
        # get all bands
        bands = product.bands
    elif product.sensor != 'S2':
        bands = [product.reverse_bands_mapping.get(band) for band in bands]

    bands_filenames = []
    for band in bands:
        # process the band through each block
        bands_filenames.append(process_band(product, band, list_of_blocks))  # save image path
    if bands_filenames == [None] * len(bands_filenames):
        logger.error("No valid band provided for input product.")
        logger.error("Valids band for products are: %s" % str(list(product.bands)))
        return
    # !! Post processing !!
    # Run the postprocessing method of each block
    for block_name in list_of_blocks:
        generic_process_step(block_name, product, "postprocess")


    # Clear metadata
    metadata.clear()

    # save S2L_config file in wd
    config.savetofile(os.path.join(config.get('wd'), product.name, 'processing_end.cfg'))


def add_common_arguments(parser):
    parser.add_argument('--version', '-v', action='version', version='%(prog)s ' + __version__)
    parser.add_argument("--refImage", dest="refImage", type=str,
                        help="Reference image (use as geometric reference)", metavar="PATH", default=None)
    # parser.add_argument("--roi", dest="roi", type=str,
    #                    help="region of interest (Json or Shapefile) [optional]", metavar="PATH", default=None)
    parser.add_argument("--wd", dest="wd", type=str,
                        help="Working directory (default : /data/production/wd)", metavar="PATH",
                        default='/data/production/wd')
    parser.add_argument("--conf", dest="S2L_configfile", type=str,
                        help="S2L_configuration file (Default: SEN2LIKE_DIR/conf/S2L_config.ini)", metavar="PATH",
                        default=os.path.join(BINDIR, '..', 'conf', 'config.ini'))
    parser.add_argument("--confParams", dest="confParams", type=str,
                        help="Overload parameter values (Default: None). Given as a \"key=value\" comma-separated list."
                             "Example: --confParams \"doNbar=False,doSbaf=False\"",
                        metavar="STRLIST", default=None)
    parser.add_argument("--bands", dest="bands", type=str,
                        help="S2 bands to process as coma separated list (Default: ALL bands)", metavar="STRLIST",
                        default=None)
    parser.add_argument("--no-run", dest="no_run", action="store_true",
                        help="Do not start process and only list products (default: False)")
    parser.add_argument("--intermediate-products", dest="generate_intermediate_products", action="store_true",
                        help="Generate intermediate products (default: False)")
    debug_group = parser.add_argument_group('Debug arguments')
    debug_group.add_argument("--debug", "-d", dest="debug", action="store_true",
                             help="Enable Debug mode (default: False)")
    debug_group.add_argument("--no-log-date", dest="no_log_date", action="store_true",
                             help="Do no store date in log (default: False)")
    return parser


def configure_arguments():
    """S2L_configure arguments parser

    :return: The S2L_configured arguments parser.
    """

    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest='operational_mode', help="Operational mode")
    add_common_arguments(parser)

    # Product mode arguments
    sp_product = subparsers.add_parser("product-mode", help="Process a single product")
    sp_product.add_argument('product', help="Landsat8 L1 product path / or Sentinel2 L1C product path")
    add_common_arguments(sp_product)
    sp_product.add_argument("--tile", help="Id of the MGRS tile to process", required=True)

    # Single tile mode arguments
    sp_single_tile_mode = subparsers.add_parser('single-tile-mode', help='Process all products on a MGRS tile')
    sp_single_tile_mode.add_argument("tile", help="Id of the MGRS tile to process")
    sp_single_tile_mode.add_argument("--start-date", dest="start_date", help="Beginning of period (format YYYY-MM-DD)",
                                     default='')
    sp_single_tile_mode.add_argument("--end-date", dest="end_date", help="End of period (format YYYY-MM-DD)",
                                     default='')
    sp_single_tile_mode.add_argument("--l2a", help="Processing level Level-2A for S2 products if set (default: L1C)",
                                     action='store_true')
    add_common_arguments(sp_single_tile_mode)

    # Multi tile mode arguments
    sp_multi_tile_mode = subparsers.add_parser('multi-tile-mode', help='Process all products on a ROI')
    sp_multi_tile_mode.add_argument("roi", help="Json file containing the ROI to process")
    sp_multi_tile_mode.add_argument("--start-date", dest="start_date", help="Beginning of period (format YYYY-MM-DD)",
                                    default='')
    sp_multi_tile_mode.add_argument("--end-date", dest="end_date", help="End of period (format YYYY-MM-DD)",
                                    default='')
    sp_multi_tile_mode.add_argument("--jobs", "-j", dest="jobs", help="Number of tile to process in parallel",
                                    default=None)
    sp_multi_tile_mode.add_argument("--l2a", help="Processing level Level-2A for S2 products if set (default: L1C)",
                                    action='store_true')
    add_common_arguments(sp_multi_tile_mode)

    return parser


def main(with_multiprocess_support=False):
    parser = configure_arguments()
    args = parser.parse_args()

    log.configure_loggers(log_path=args.wd, is_debug=args.debug, without_date=args.no_log_date)

    if args.operational_mode is None:
        parser.print_help()
        return 1

    # convert list of bands if provided
    if args.bands is not None:
        args.bands = args.bands.split(',')

    products, start_date, end_date = configure_sen2like(args)

    if products is None:
        return 1
    if args.operational_mode == 'multi-tile-mode' and with_multiprocess_support and not args.no_run:
        number_of_process = args.jobs
        if number_of_process is None:
            number_of_process = config.get('number_of_process', 1)
        params = [(tile, _products, args, start_date, end_date) for tile, _products in products.items()]
        with Pool(int(number_of_process)) as pool:
            pool.starmap(start_process, params)
    else:
        if args.no_run:
            logger.info("No-run mode: Products will only be listed")
        for tile, _products in products.items():
            start_process(tile, _products, args, start_date, end_date)
    return 0


if __name__ == "__main__":
    sys.exit(main(with_multiprocess_support=True))
