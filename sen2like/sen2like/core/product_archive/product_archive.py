import datetime
import json
import logging
import os
import re
import sqlite3
import time
import urllib
from collections import defaultdict
from urllib.request import urlopen

from osgeo import gdal, ogr

from core.products import get_product

logger = logging.getLogger("Sen2Like")

s2_date_regexp = re.compile(r"S2._.+?_(\d{8}T\d{6})_.*")
s2_date_regexp_long_name = re.compile(r"S2._.+?_\d{8}T\d{6}_R\d{3}_V(\d{8}T\d{6})_\d{8}T\d{6}.*")
l8_date_regexp = re.compile(r"L[CTOEM]0[8-9]_.{4}_\d+_(\d+)_.*")
l8_date_regexp_old_format = re.compile(r"L[CTOEM][8-9]\d{6}(\d{7}).*")
l8_date_regexp_sc_format = re.compile(r"L[CTOEM]0[8-9]\d{6}(\d{8}).*")


class InputProduct:
    def __init__(self, path=None, tile_coverage=None, date=None, reader=None):
        self.path = path
        self.reader = reader
        self.cloud_cover = None
        self.tile_coverage = tile_coverage
        self.date = date
        self.gml_geometry = None

    def __eq__(self, other):
        return self.path == other.path and self.instrument == other.instrument and self.date == other.date

    @property
    def instrument(self):
        return self.reader.sensor if self.reader is not None else None

    @property
    def short_date(self):
        return datetime.datetime(self.date.year, self.date.month, self.date.day) if self.date else None


def read_polygon_from_json(json_file):
    ds = gdal.OpenEx(json_file)
    layer = ds.GetLayer()
    feature = layer.GetFeature(0)
    if feature is None:
        logging.error("No features in json file: {}".format(json_file))
        return None
    export = feature.GetGeometryRef().ExportToWkt()
    ds = None
    return export


def database_path(database_name):
    if database_name == 's2grid.db':
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "grids", database_name)
    else:
        return os.path.join(os.path.dirname(__file__), "data", database_name)


def is_spatialite_supported():
    if os.environ.get("SPATIALITE_DIR") is None:
        logger.warning("SPATIALITE_DIR environment variable not set.")
    else:
        os.environ["PATH"] = ";".join([os.environ["SPATIALITE_DIR"], os.environ["PATH"]])
    with sqlite3.connect(":memory:") as conn:
        conn.enable_load_extension(True)
        try:
            conn.load_extension("mod_spatialite")
        except sqlite3.OperationalError:
            return False
    return True


class InputProductArchive:

    def __init__(self, configuration, roi=None):
        self.configuration = configuration
        self.roi = roi

    def construct_url(self, mission, tile=None, start_date=None, end_date=None, path=None, row=None, cloud_cover=None):
        base_url = self.configuration.get('base_url')
        # Special formatting for date
        if start_date:
            start_date = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_date:
            end_date = end_date.strftime("%Y-%m-%dT23:59:59")
        parameter = self.configuration.get(f'url_parameters_pattern_{mission}')
        if parameter is None:
            parameter = self.configuration.get(f'url_parameters_pattern')
        s2_processing_level = self.configuration.get(f's2_processing_level')
        # Get location parameter depending on mission
        location = self.configuration.get(f'location_{mission}', "").format(**locals())
        if cloud_cover is None:
            cloud_cover = self.configuration.get('cloud_cover', 10)
        url = parameter.format(**locals())
        logging.debug(url)
        return url

    @staticmethod
    def mgrs_to_wrs(mgrs_tile, coverage=None):
        if coverage is None:
            logger.warning(
                "No minimum coverage defined in configuration, using {:.0%} as default coverage.".format(0.1))
            coverage = 0.1
        else:
            logging.debug("Using {:.0%} coverage.".format(coverage))
        # Open db
        with sqlite3.connect(database_path("l8_s2_coverage.db")) as connection:
            logging.debug(mgrs_tile)
            cur = connection.execute(
                "SELECT TILE_ID, WRS_ID, Coverage from l8_s2_coverage WHERE TILE_ID = ? and Coverage >= ?",
                (mgrs_tile, coverage * 100))
            data = cur.fetchall()
            # Sort by coverage
            data = sorted(data, key=lambda t: t[2], reverse=True)
            result = [([int(i) for i in entry[1].split('_')], entry[2]) for entry in data]
        return result

    @staticmethod
    def wrs_to_mgrs(wrs_path, coverage=None):
        if coverage is None:
            logger.warning(
                "No minimum coverage defined in configuration, using {:.0%} as default coverage.".format(0.1))
            coverage = 0.1
        else:
            logging.debug("Using {:.0%} coverage.".format(coverage))
        # Open db
        with sqlite3.connect(database_path("l8_s2_coverage.db")) as connection:
            logging.debug(wrs_path)
            cur = connection.execute(
                "SELECT TILE_ID, WRS_ID, Coverage from l8_s2_coverage WHERE WRS_ID = ? and Coverage >= ?",
                ("{}_{}".format(*wrs_path), coverage * 100))
            data = cur.fetchall()
            # Sort by coverage
            data = sorted(data, key=lambda t: t[2], reverse=True)
            result = [entry[0] for entry in data]
        return result

    @staticmethod
    def get_coverage(wrs_path, mgrs_tile):
        # Open db
        coverage = 0
        with sqlite3.connect(database_path("l8_s2_coverage.db")) as connection:
            logging.debug((wrs_path, mgrs_tile))
            cur = connection.execute(
                "SELECT Coverage from l8_s2_coverage WHERE WRS_ID = ? and TILE_ID = ?",
                ("{}_{}".format(*wrs_path), mgrs_tile))
            data = cur.fetchall()
            if len(data) > 0:
                coverage = data[0][0]
        return coverage

    @staticmethod
    def roi_to_tiles(roi):
        with sqlite3.connect(database_path("s2tiles.db")) as connection:
            logging.debug("ROI: {}".format(roi))
            connection.enable_load_extension(True)
            connection.load_extension("mod_spatialite")
            sql = f"select TILE_ID from s2tiles where intersects(s2tiles.geometry, GeomFromText('{roi}'))==1"
            logging.debug("SQL request: {}".format(sql))
            cur = connection.execute(sql)
            # TODO: For now, first mgrs tile is excluded. To improve in a future version
            # TODO: Add coverage
            tiles = [tile[0] for tile in cur.fetchall() if
                     not tile[0].startswith('01') and not tile[0].startswith('60')]
            logging.debug("Tiles: {}".format(tiles))
        return tiles

    @staticmethod
    def mgrs_to_wkt(tile):
        with sqlite3.connect(database_path("s2tiles.db")) as connection:
            logging.debug("TILE: {}".format(tile))
            sql = f"select LL_WKT from s2tiles where TILE_ID='{tile}'"
            logging.debug("SQL request: {}".format(sql))
            cur = connection.execute(sql)
            res = cur.fetchall()
            if len(res) > 0:
                wkt = res[0][0]
                logging.debug("TILE WKT: {}".format(wkt))
            else:
                wkt = None
                logging.error(f"tile {tile} not found in database")
        return wkt

    @staticmethod
    def wrs_to_wkt(wrs_id):
        with sqlite3.connect(database_path("s2grid.db")) as connection:
            logging.debug("WRS: {}".format(wrs_id))
            sql = f"select LL_WKT from l8tiles where WRS_ID='{wrs_id}'"
            logging.debug("SQL request: {}".format(sql))
            cur = connection.execute(sql)
            wkt = cur.fetchall()[0][0]
            logging.debug("WRS WKT: {}".format(wkt))
        return wkt

    def download_file(self, url):
        try:
            with urlopen(url, timeout=120) as stream:
                logger.debug("http request status: %s" % stream.status)
                return json.loads(stream.read().decode())
        except (urllib.error.URLError, ValueError) as error:
            logger.error("Cannot read %s" % url)
            logger.error(error)
            return {}

    def read_products_from_url(self, url, tile_coverage):
        urls = []
        products = {}
        logger.debug("URL: %s" % url)

        for download_try in range(1, 5):
            logger.debug("Trying to download url: try %s/5 " % (download_try))
            products = self.download_file(url)
            if products:
                break
            time.sleep(5)
        else:
            logger.error("Cannot download products from url: %s" % url)

        for product in products.get("features"):
            downloaded = InputProduct(tile_coverage=tile_coverage)
            _product = product
            for _property in self.configuration.get("thumbnail_property").split('/'):
                _product = _product.get(_property, {})
            downloaded.path = _product
            _cloud_cover = product
            for _property in self.configuration.get("cloud_cover_property").split('/'):
                _cloud_cover = _cloud_cover.get(_property, {})
            downloaded.cloud_cover = _cloud_cover
            _gml_geometry = product
            for _property in self.configuration.get("gml_geometry_property").split('/'):
                _gml_geometry = _gml_geometry.get(_property, {})
            downloaded.gml_geometry = _gml_geometry
            if downloaded.path:
                urls.append(downloaded)
        return urls

    @staticmethod
    def is_local(url):
        for prefix in ["http", "https", "ftp"]:
            if url.startswith("{}://".format(prefix)):
                return False
        return True

    def get_products_url_from_tile(self, tile, start_date=None, end_date=None):
        """Get products on tile on the provided time interval.

        :param tile: The tile path
        :param start_date: Start of the period
        :param end_date: End of the period
        :return:
        """
        wrs = self.mgrs_to_wrs(tile, self.configuration.getfloat("coverage"))
        logger.debug("{} > {}".format(tile, wrs))
        # Build urls for Sentinel2
        urls = [(self.construct_url("Sentinel2", tile, start_date=start_date, end_date=end_date), 100)]

        # Build urls for Landsat8
        for [path, row], tile_coverage in wrs:
            add_url = True
            # Check if wrs path actually intersects the ROI
            if self.roi is not None:
                wkt = self.wrs_to_wkt(f"{path}_{row}")
                path_polygon = ogr.CreateGeometryFromWkt(wkt)
                roi_polygon = ogr.CreateGeometryFromWkt(self.roi)
                intersection = path_polygon.Intersection(roi_polygon)
                if intersection is None or intersection.Area() == 0:
                    logger.info("WRS %s_%s does not intersect given ROI. Skip wrs tile." % (path, row))
                    add_url = False
            if add_url:
                urls.append((
                    self.construct_url("Landsat8", tile, start_date=start_date, end_date=end_date, path=path, row=row),
                    tile_coverage))
        if not urls:
            logger.warning(
                "No product found for tile {} during period {} - {}".format(tile, start_date, end_date))
        return urls

    def get_products_from_urls(self, urls, start_date=None, end_date=None, product_mode=False, exclude=None,
                               processing_level=None):
        """Get products on tile on the provided time interval.

        :param processing_level: Add processing level for filtering
        :param exclude: List of products to exclude
        :param product_mode: Indicates if we are in product or tile mode
        :param urls: The urls to parse
        :param start_date: Start of the period
        :param end_date: End of the period
        :return:
        """
        products_urls = []
        for index, (url, tile_coverage) in enumerate(urls, 1):
            logger.debug('Reading product sources: {:.2%} ({}/{})'.format(index / len(urls), index, len(urls)))
            if self.is_local(url):
                if os.path.exists(url):
                    if product_mode:
                        products_urls.append(InputProduct(path=url, tile_coverage=tile_coverage))
                    else:
                        products_urls.extend(
                            [InputProduct(path=os.path.join(url, _dir), tile_coverage=tile_coverage) for _dir in
                             os.listdir(url)])
                else:
                    logger.error("Invalid product path: %s does not exist" % url)
            else:
                products_urls.extend(self.read_products_from_url(url, tile_coverage=tile_coverage))

        processing_level_filter = self.configuration.get('s2_processing_level')
        if processing_level_filter is None:
            processing_level_filter = processing_level

        products = []
        for product in products_urls:
            product.reader = get_product(product.path)
            regexp, date_format = product.reader.date_format(os.path.basename(product.path))
            product.date = product.reader.date(product.path, regexp, date_format)
            is_product_valid = self.filter_on_date(product, start_date, end_date)

            if product.instrument == 'S2' and processing_level_filter is not None:
                is_product_valid &= product.reader.processing_level(
                    os.path.basename(product.path)) == processing_level_filter
            if is_product_valid:
                products.append(product)
                logger.debug('  + {} {}'.format(product.reader.sensor, os.path.basename(product.path)))

        # Filter products with exclude list
        if exclude is not None:
            excluded_path = [os.path.normpath(p.path) for p in exclude]
            filtered_products = [p for p in products if os.path.normpath(p.path) not in excluded_path]
            logger.debug("{} products excluded".format(len(products) - len(filtered_products)))
            products = filtered_products

        return self.filter_and_sort_products(products)

    @staticmethod
    def filter_product_composition(products):
        if products:
            reader = get_product(products[0].path)
            if reader.sensor == 'L8':
                filtered = reader.best_product([p.path for p in products])
                return [p for p in products if p.path in filtered]
        return products

    def filter_on_tile_coverage(self, products):
        products_filtered = []
        # update tile coverage and refilter
        tile_wkt = self.mgrs_to_wkt(self.configuration.get('tile'))
        if tile_wkt is None:
            return products_filtered
        tile_polygon = ogr.CreateGeometryFromWkt(tile_wkt)
        coverage = self.configuration.getfloat('coverage')
        if coverage is None:
            coverage = 0.1
        for product in products:
            if product.instrument == 'S2' and product.gml_geometry:
                product_polygon = ogr.CreateGeometryFromGML(product.gml_geometry)
                logger.debug(
                    'PRODUCT/TILE_COVERAGE: {}/{}'.format(os.path.basename(product.path), product.tile_coverage))
                product.tile_coverage = 100 * product_polygon.Intersection(
                    tile_polygon).GetArea() / tile_polygon.GetArea()
                logger.debug('PRODUCT/TILE_COVERAGE (UPDATED): {}/{}'.format(os.path.basename(product.path),
                                                                             product.tile_coverage))
                if product.tile_coverage > 100 * coverage:
                    products_filtered.append(product)
            else:
                products_filtered.append(product)
        return products_filtered

    def filter_and_sort_products(self, products):
        # update tile coverage and filter
        products = self.filter_on_tile_coverage(products)

        # Group products by dates
        flipped = defaultdict(lambda: defaultdict(list))
        for product in products:
            flipped[product.short_date][product.instrument].append(product)

        results = []
        for date, instruments in flipped.items():
            for instrument, _products in instruments.items():
                if instrument == 'L8':
                    _products = self.filter_product_composition(_products)
                results.append(sorted(_products, key=lambda p: p.tile_coverage if p.tile_coverage is not None else 0,
                                      reverse=True)[0])

        # Sort products by date, and S2 products before L8 products
        results = sorted(sorted(results, key=lambda prod: prod.instrument, reverse=True),
                         key=lambda prod: prod.short_date)
        return results

    @staticmethod
    def filter_on_date(product, start_date=None, end_date=None):
        if product.date is None:
            return False
        logger.debug("Extracted date for {}: {}".format(product.path, product.date.strftime("%Y/%m/%d")))

        product_is_valid = True
        if start_date:
            product_is_valid &= start_date <= product.date
        if end_date:
            end_date = end_date.replace(hour=23, minute=59, second=59)
            product_is_valid &= product.date <= end_date
        if not product_is_valid:
            logger.debug(
                "Product not contained in {} - {}".format(start_date.strftime("%Y/%m/%d") if start_date else '',
                                                          end_date.strftime("%Y/%m/%d") if end_date else ''))

        return product_is_valid
