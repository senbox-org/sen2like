"""Module dedicated to get search product URL"""
import logging
from typing import Dict, List, Tuple
from argparse import Namespace
from osgeo import gdal

from core.argparser import DateRange, Mode
from core.product_archive import tile_db
from core.product_archive.product_archive import InputProductArchive
from core.S2L_config import config


logger = logging.getLogger('Sen2Like')


def _read_polygon_from_json(json_file):
    dataset = gdal.OpenEx(json_file)
    layer = dataset.GetLayer()
    feature = layer.GetFeature(0)
    if feature is None:
        logging.error("No features in json file: %s", json_file)
        return None
    export = feature.GetGeometryRef().ExportToWkt()
    dataset = None
    return export


def _get_search_url(polygon, date_range: DateRange, tiles: List[str]) -> Dict[str, List[Tuple]]:
    """Get product search urls that intersect the polygon in date range for given mgrs tiles.
    - For local products, URL are directories that should contains products (tile or path/row folder),
        NOT the complete product path.
    - For remote product, URL are remote catalogue search URL.

    Args:
        polygon (_type_): _description_
        date_range (DateRange): date range criteria
        tiles (List[str]): list of tiles

    Returns:
        Dict[str, List[Tuple]]: dict of list of url,coverage tuple, indexed by tile.
        For local products, URL are directories that contains products (tile or path/row folder), NOT the complete product path
        URL are sorted by tile coverage desc in each tile list.
        example : 
        {
            '12SYH': [
                ('/data/Products/Sentinel2/12SYH', 1), 
                ('/data/Products/Landsat8/35/33', 0.7126961469055555), 
                ('/data/Products/Landsat9/35/33', 0.7126961469055555), 
                ('/data/Products/Landsat8/35/34', 0.46340014084620473), 
                ...
            ]
        }
    """
    archive = InputProductArchive(config, roi=polygon)
    search_urls = {tile: [url for url in archive.get_search_url_from_tile(
        tile, date_range.start_date, date_range.end_date)] for tile in tiles}
    return search_urls


def _geo_get_tiles(spatial_func, geojson_file_path):

    if not tile_db.is_spatialite_supported():
        raise AssertionError("Spatialite support is not available. Cannot determine MGRS tiles from ROI.")

    polygon = _read_polygon_from_json(geojson_file_path)
    if polygon is not None:
        tiles = spatial_func(polygon)
    else:
        tiles = []

    return polygon, tiles


def _get_single_tile_mode_search_url(args, date_range):
    tiles = [args.tile]
    search_urls = _get_search_url(None, date_range, tiles)
    return search_urls, tiles


def _get_multi_tile_mode_search_url(args, date_range):
    polygon, tiles = _geo_get_tiles(tile_db.tiles_intersect_roi, args.roi)
    search_urls = _get_search_url(polygon, date_range, tiles)
    return search_urls, tiles


# pylint: disable=unused-argument
def _get_product_mode_search_url(args, date_range):
    product_url = {args.tile: [(args.product, 1)]}
    tile = [args.tile]
    return product_url, tile


def _get_roi_based_mode_search_url(args, date_range):
    polygon, tiles = _geo_get_tiles(tile_db.tiles_contains_roi, args.roi)
    if args.tile:
        if args.tile in tiles:
            tiles = [args.tile]
        else:
            raise AssertionError(f"{args.tile} is not in founded MGRS tiles : {tiles}")
    else:
        if len(tiles) != 1:
            raise AssertionError(
                f"Found more than one MGRS tile containing the ROI without specifying --tile param : {tiles}")

    products = _get_search_url(polygon, date_range, tiles)
    return products, tiles


# dict to select function for tile and product selection depending mode
# function MUST have signature def _func_name(args: Namespace, date_range: DateRange)
_get_search_urls_function = {
    Mode.SINGLE_TILE: _get_single_tile_mode_search_url,
    Mode.MULTI_TILE: _get_multi_tile_mode_search_url,
    Mode.PRODUCT: _get_product_mode_search_url,
    Mode.ROI_BASED: _get_roi_based_mode_search_url,
}


def get_search_url(args: Namespace, date_range: DateRange) -> Dict[str, List[Tuple[str, float]]]:
    """Retrieve products search URL to process depending the selected mode.
    URLS are listed by tile coverage desc

    Args:
        args (Namespace): parsed program args, contains selected mode
        and other useful parameter for product and tile selection
        date_range (DateRange): date interval to search product for

    Returns:
        Dict[str, List[Tuple[str, float]]]: product indexed by tile 
        with value list of tuple that are product URL and tile coverage.
        - For local products, URL are directories that should contains products (tile or path/row folder),
          NOT the complete product path.
        - For remote products, URL are remote catalogue search URL.

        example : {'31TFJ': [('/data/PRODUCTS/Sentinel2/31TFJ', 100),
            ('/data/PRODUCTS/Landsat8/196/30', 0.7600012569702809),
            ('/data/PRODUCTS/Landsat9/196/30', 0.7600012569702809)]}
        None if no product found
    """
    func = _get_search_urls_function.get(args.operational_mode)
    _search_urls, tiles = func(args, date_range)
    if not _search_urls:
        logger.error("No product found. Exiting application...")
        return None
    # Filter on original tiles:
    return {tile: item for (tile, item) in _search_urls.items() if tile in tiles}

# def get_products_old(args: Namespace, date_range: DateRange):
#     """Retrieve products to process.

#     Args:
#         args (Namespace): parsed program args
#         date_range (DateRange): date interval to search product for

#     Returns:
#         _type_: tuple of :
#         - product as dict indexed by tile with value list of tuple that are product URL and tile coverage
#         example : {'31TFJ': [('/data/PRODUCTS/Sentinel2/31TFJ', 100),
#             ('/data/PRODUCTS/Landsat8/196/30', 0.7600012569702809),
#             ('/data/PRODUCTS/Landsat9/196/30', 0.7600012569702809)]}
#         - processing start date if not in *-tile-mode, or None
#         - processing end date if not in *-tile-mode, or None
#     """
#     # Are we in tile mode ?
#     if args.operational_mode in ['single-tile-mode', 'multi-tile-mode']:

#         if args.operational_mode == 'multi-tile-mode':
#             if not tile_db.is_spatialite_supported():
#                 logger.error("Spatialite support is not available. Cannot determine MGRS tiles from ROI.")
#                 return
#             json_file = args.roi
#             polygon = read_polygon_from_json(json_file)
#             if polygon is not None:
#                 tiles = tile_db.tiles_intersect_roi(polygon)
#             else:
#                 tiles = []
#         else:
#             polygon = None
#             tiles = [args.tile]

#         downloader = InputProductArchive(config, roi=polygon)
#         products = {tile: [url for url in downloader.get_search_url_from_tile(
#             tile, date_range.start_date, date_range.end_date)] for tile in tiles}
#         if not products:
#             logger.error("No product found. Exiting application...")
#             return
#     else:
#         products = {args.tile: [(args.product, 100)]}
#         tiles = [args.tile]

#     # Filter on original tiles:
#     products = {tile: item for (tile, item) in products.items() if tile in tiles}
#     return products
