#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

"""Main entry point for the sen2like application."""

import datetime
import hashlib
import importlib
import json
import logging
import os
import shutil
import subprocess
import sys
import glob
from argparse import ArgumentParser
from multiprocessing import Pool

from core import S2L_config, log
from core.QI_MTD import mtd
from core.S2L_config import config
from core.sen2cor_client.sen2cor_client import Sen2corClient, Sen2corError

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


def get_scl_map(scl_dir, product):
    scl_map = None
    tilecode = product.mtl.mgrs
    
    if product.sensor == 'S2':
        acqdate = datetime.datetime.strftime(product.dt_sensing_start, '%Y%m%dT%H%M%S')        
    else:
        acqdate = datetime.datetime.strftime(product.acqdate, '%Y%m%dT%H%M%S')

    result = glob.glob(os.path.join(scl_dir, tilecode, f"T{tilecode}_{acqdate}_SCL_60m.tif"))
    if result:
        scl_map = result[0]
    
    if scl_map is not None:
        logger.info('Auxiliary scene classification map found: {}'.format(scl_map))
    else:
        logger.info('Auxiliary scene classification map NOT found.')
    
    return scl_map 
    

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

    # check if block is applicable to the sensor (L8, L9 or S2)
    if pd.sensor not in S2L_config.PROC_BLOCKS[blockname]['applicability']:
        return

    class_instance = get_module(blockname)

    # create object and run process if method exists!
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
        return image, None

    # check if block is applicable to the sensor (L8, L9 or S2)
    if pd.sensor not in S2L_config.PROC_BLOCKS[blockname]['applicability']:
        return image, None

    class_instance = get_module(blockname)

    # create object and run it!
    return class_instance.process(pd, image, band), class_instance


def process_band(pd, band, list_of_blocks, _config, _metadata, _processus=None):
    """Function for running all the blocks over one band.""";
    logger.info(f'--- Process band {band} ---')
    if S2L_config.config.parser is None:
        S2L_config.config = _config
        globals()['config'] = _config

    mtd.metadata.update(_metadata)
    if _processus is not None:
        global PROCESS_INSTANCES
        PROCESS_INSTANCES = _processus

    # get band file path
    image = pd.get_band_file(band)
    if image is None:
        return None, None, None, None

    # iterate on blocks
    packager_images = {}
    for block_name in list_of_blocks:
        image, block = generic_process_band(block_name, pd, image, band)

        # Special case for packager as we need to keep self.images
        if '_Packager' in block_name and block is not None:
            packager_images[block_name] = block.images

    # return output
    return image.filename, packager_images, config, mtd.metadata


def compute_config_hash(args, _config):
    """Compute hash from arguments and configuration.

    :param args: Tool arguments.
    :param _config: Configuration
    :return: Hexdigest of the hash.
    """

    # debug
    import copy
    exclude_list = ['parallelize_bands']
    dc = copy.deepcopy(args.__dict__)
    for exc in exclude_list:
        dc.pop(exc)
    dc = str(dc)

    # Prod
    # dc = str(args.__dict__)

    # Configuration hash
    if _config.parser.config_file is not None:
        with open(_config.parser.config_file) as file:
            file_content = file.read()
    _hash = hashlib.md5(file_content.encode())
    _hash.update(dc.encode())
    return _hash.hexdigest()


def update_configuration(args, tile=None):
    # init S2L_config and save to wd
    if not config.initialize(args.S2L_configfile):
        return

    if args.confParams is not None:
        config.overload(args.confParams)

    use_pid = False
    if use_pid:
        output_folder = str(os.getpid())
    else:
        date_now = datetime.datetime.now().strftime('%Y%m%dT_%H%M%S')
        output_folder = f'{"" if args.no_log_date else f"{date_now}_"}{compute_config_hash(args, config)}'
    config.set('wd', os.path.join(args.wd, output_folder))
    references_map_file = config.get('references_map')
    if args.refImage:
        config.set('refImage', args.refImage)
    elif references_map_file and tile:
        if os.path.isfile(references_map_file):
            # load dataset
            with open(references_map_file) as j:
                references_map = json.load(j)
            config.set('refImage', references_map.get(tile))
        else:
            logger.warning(f"The reference path {references_map_file} doesn't exist. So it is considered as None.")
            config.set('refImage', None)
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


def filter_product(product):
    """ Filter on product after creat them
    :param product: a core.product.S2L_Product
    :return: bool
    """
    cloud_cover = config.getfloat('cloud_cover')
    if float(product.mtl.cloud_cover) > cloud_cover:
        logger.info(f'cloud cover > {cloud_cover}')
        return False
    return True


def start_process(tile, products, args, start_date, end_date):
    update_configuration(args, tile)
    config.set('tile', tile)
    logger.info("Processing tile {}".format(tile))
    downloader = InputProductArchive(config)
    _products = downloader.get_products_from_urls(products, start_date, end_date,
                                                  product_mode=args.operational_mode == 'product-mode')
    if args.no_run:
        logger.info("Tile: %s" % tile)
        if not _products:
            logger.info("No products found.")
        for product in _products:
            tile_message = f'[ Tile coverage = {product.tile_coverage:6.0f}% ]' \
                if product.tile_coverage is not None else ''
            cloud_message = f'[ Cloud coverage = {product.cloud_cover:6.0f}% ]' \
                if product.cloud_cover is not None else ''
            logger.info("%s %s %s" % (tile_message, cloud_message, product.path))
        return

    for product in _products:
        _product = product.reader(product.path)
        atmcor = config.get('doAtmcor')
        stitch = config.get('doStitching')
        intercalibration = config.get('doInterCalibration')

        use_sen2cor = config.getboolean('use_sen2cor')
        # only landsat collection 1
        if 'L8' in _product.sensor:
            if not _product.mtl.collection_number.isdigit() or int(_product.collection_number) > 1:
                use_sen2cor = False
                logger.info("For landsat 8, apply sen2cor only on collection 01 products")
        if use_sen2cor:
            # Disable Atmospheric correction
            config.overload('doAtmcor=False')
            config.overload('doStitching=False')
            config.overload('doInterCalibration=False')

            sen2cor = Sen2corClient(os.path.abspath(config.get('sen2cor_path')), tile)

            try:
                _product = product.reader(sen2cor.run(_product))
            except Sen2corError:
                continue

        if _product is None:
            _product = product.reader(product.path)

        if not filter_product(_product):
            continue

        # Update processing configuration
        config.set('productName', _product.name)
        config.set('sensor', _product.sensor)
        config.set('observation_date', _product.mtl.observation_date)
        config.set('relative_orbit', _product.mtl.relative_orbit)
        config.set('absolute_orbit', _product.mtl.absolute_orbit)
        config.set('mission', _product.mtl.mission)
        config.set('none_S2_product_for_fusion', False)

        # Disable Atmospheric correction for Level-2A products
        if _product.mtl.data_type in ('Level-2A', 'L2TP', 'L2A'):
            config.overload('s2_processing_level=LEVEL2A')
            logger.info("Processing Level-2A product: Atmospheric correction is disabled.")
            config.overload('doAtmcor=False')
            config.overload('doInterCalibration=False')
        else:
            config.overload('s2_processing_level=LEVEL1C')

        process(_product, args)

        # Restore atmcor status
        config.overload(f'doAtmcor={atmcor}')
        config.overload(f'doStitching={stitch}')
        config.overload(f'doInterCalibration={intercalibration}')
        del _product
    if len(_products) == 0:
        logger.error('No product for tile %s' % tile)


def process(product, args):
    """Launch process on product."""
    bands = args.bands
    # create working directory and save conf (traceability)
    if not os.path.exists(os.path.join(config.get("wd"), product.name)):
        os.makedirs(os.path.join(config.get("wd"), product.name))

    # displays
    logger.info('='*50)
    logger.info("Process : {} {}".format(product.sensor, product.path))

    # list of the blocks that are available
    list_of_blocks = tuple(S2L_config.PROC_BLOCKS.keys())

    # copy MTL files in wd
    wd = os.path.join(config.get("wd"), product.name)
    # copy MTL files in final product
    shutil.copyfile(product.mtl.mtl_file_name, os.path.join(wd, os.path.basename(product.mtl.mtl_file_name)))
    if product.mtl.tile_metadata:
        shutil.copyfile(product.mtl.tile_metadata, os.path.join(wd, os.path.basename(product.mtl.tile_metadata)))

    # Get scl map for valid pixel mask
    scl_dir = config.get("scl_dir")
    if scl_dir and (not config.getboolean('use_sen2cor')) and product.mtl.data_type != 'Level-2A':
        product.mtl.scene_classif_band = get_scl_map(scl_dir, product)

    # Angles extraction
    product.mtl.get_angle_images(os.path.join(config.get("wd"), product.name, 'tie_points.tif'))
    product.mtl.get_valid_pixel_mask(os.path.join(config.get("wd"), product.name, 'valid_pixel_mask.tif'))
    if S2L_config.config.get('nbar_methode') == 'VJB':
        product.get_ndvi_image(os.path.join(config.get("wd"), product.name, 'ndvi.tif'))

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
        bands = [product.reverse_bands_mapping.get(band, band) for band in bands]

    if args.parallelize_bands:
        # Multi processus
        params = [(product, band, list_of_blocks, config, mtd.metadata, PROCESS_INSTANCES) for band in bands]
        with Pool() as pool:
            results = pool.starmap(process_band, params)

        bands_filenames, packager_files, configs, updated_metadatas = zip(*results)
        if configs and configs[0].parser is not None:
            S2L_config.config = configs[0]
        if updated_metadatas:
            for updated_metadata in updated_metadatas:
                mtd.metadata.update(updated_metadata)
        for packager_file in packager_files:
            for process_instance in packager_file:
                PROCESS_INSTANCES[process_instance].images.update(packager_file[process_instance])
                for band, filename in PROCESS_INSTANCES[process_instance].images.items():
                    S2L_config.config.set('imageout_dir', os.path.dirname(filename))
                    S2L_config.config.set('imageout_' + band, os.path.basename(filename))

    else:
        # Single processus
        bands_filenames = []
        for band in bands:
            # process the band through each block
            bands_filenames.append(process_band(product, band, list_of_blocks, config, mtd.metadata))  # Save image path

    if bands_filenames == [None] * len(bands_filenames):
        logger.error("No valid band provided for input product.")
        logger.error("Valids band for products are: %s" % str(list(product.bands)))
        return
    # !! Post processing !!
    # Run the postprocessing method of each block
    for block_name in list_of_blocks:
        generic_process_step(block_name, product, "postprocess")

    # Clear metadata
    mtd.metadata.clear()

    # save S2L_config file in wd
    S2L_config.config.savetofile(os.path.join(S2L_config.config.get('wd'), product.name, 'processing_end.cfg'))


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
    parser.add_argument("--parallelize-bands", action="store_true",
                        help="Process bands in parallel (default: False)")
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
