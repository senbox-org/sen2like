import datetime
import json
import logging
import os
import time
import urllib
from typing import List
from collections import defaultdict
from urllib.request import urlopen

from osgeo import ogr

from core.products import get_s2l_product_class
from core.product_archive import tile_db

logger = logging.getLogger("Sen2Like")


class InputProduct:
    def __init__(self, path=None, tile_coverage=None, date=None, s2l_product_class=None):
        self.path = path
        # concrete S2L_Product class for S2L product instantiation
        self.s2l_product_class = s2l_product_class
        self.cloud_cover = None
        self.tile_coverage = tile_coverage
        self.date = date
        self.gml_geometry = None

    def __eq__(self, other):
        return self.path == other.path and self.instrument == other.instrument and self.date == other.date

    @property
    def instrument(self):
        return self.s2l_product_class.sensor if self.s2l_product_class is not None else None

    @property
    def short_date(self):
        return datetime.datetime(self.date.year, self.date.month, self.date.day) if self.date else None


class InputProductArchive:
    """Input product archive to retrieve products from there they are stored
    """
    def __init__(self, configuration, roi=None):
        self.configuration = configuration
        self.roi = roi

    def construct_url(self, mission, tile=None, start_date=None, end_date=None, path=None, row=None, cloud_cover=None):
        # WARN : load variable to having them in the local scope when using **locals()
        base_url_landsat = self.configuration.get('base_url_landsat')
        base_url_s2 = self.configuration.get('base_url_s2')
        base_url = self.configuration.get('base_url')
        # TODO : specific to s2, see how to avoid it here
        s2_processing_level = self.configuration.get('s2_processing_level')

        # Special formatting for date
        if start_date:
            start_date = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        if end_date:
            end_date = end_date.strftime("%Y-%m-%dT23:59:59")

        parameter = self.configuration.get(f'url_parameters_pattern_{mission}')
        if parameter is None:
            parameter = self.configuration.get('url_parameters_pattern')

        # Get location parameter depending on mission, then format it with available local variable
        location = self.configuration.get(f'location_{mission}', "").format(**locals())
        if cloud_cover is None:
            cloud_cover = self.configuration.get('cloud_cover', 10)

        # fill url with variable in local scope
        url = parameter.format(**locals())
        logging.debug(url)
        return url

    @staticmethod
    def _download_file(url: str) -> dict:
        """Download resource at given url. Expect a json resource

        Args:
            url (str): url to fetch

        Returns:
            dict: json response as dict

        Raises:
            urllib.error.HTTPError: for 404
        """
        try:
            with urlopen(url, timeout=120) as stream:
                logger.debug("http request status: %s", stream.status)
                return json.loads(stream.read().decode())
        except (urllib.error.URLError, ValueError) as error:
            logger.error("Cannot read %s", url)
            logger.error(error)
            # for now only check 404, but could be some other
            if isinstance(error, urllib.error.HTTPError) and error.code == 404:
                raise
            return {}

    def read_products_from_url(self, url, tile_coverage) -> List[InputProduct]:
        input_product_list: List[InputProduct] = []
        products = {}
        logger.debug("URL: %s", url)

        for download_try in range(1, 5):
            logger.debug("Trying to download url: try %s/5 ", download_try)

            try:
                products = self._download_file(url)
            except urllib.error.HTTPError:
                break
            if products:
                break

            time.sleep(5)

        if not products:
            logger.error("Cannot download products from url: %s", url)
            return input_product_list

        for product in products.get("features"):
            input_product = InputProduct(tile_coverage=tile_coverage)
            _product = product
            for _property in self.configuration.get("thumbnail_property").split('/'):
                _product = _product.get(_property, {})
            input_product.path = _product
            _cloud_cover = product
            for _property in self.configuration.get("cloud_cover_property").split('/'):
                _cloud_cover = _cloud_cover.get(_property, {})
            input_product.cloud_cover = _cloud_cover
            _gml_geometry = product
            for _property in self.configuration.get("gml_geometry_property").split('/'):
                _gml_geometry = _gml_geometry.get(_property, {})
            input_product.gml_geometry = _gml_geometry
            if input_product.path:
                input_product_list.append(input_product)

        return input_product_list

    @staticmethod
    def is_local(url):
        for prefix in ["http", "https", "ftp"]:

            if url.startswith(f"{prefix}://"):
                return False

        return True

    def get_products_url_from_tile(self, tile, start_date=None, end_date=None):
        """Get products on tile on the provided time interval.

        :param tile: The tile path
        :param start_date: Start of the period
        :param end_date: End of the period
        :return:
        """
        wrs = tile_db.mgrs_to_wrs(tile, self.configuration.getfloat("coverage"))
        logger.debug("%s > %s", tile, wrs)
        # Build urls for Sentinel2
        urls = [(self.construct_url("Sentinel2", tile, start_date=start_date, end_date=end_date), 100)]
        # Build urls for Landsat8
        for [path, row], tile_coverage in wrs:
            add_url = True
            # Check if wrs path actually intersects the ROI
            if self.roi is not None:
                wkt = tile_db.wrs_to_wkt(f"{path}_{row}")
                path_polygon = ogr.CreateGeometryFromWkt(wkt)
                roi_polygon = ogr.CreateGeometryFromWkt(self.roi)
                intersection = path_polygon.Intersection(roi_polygon)

                if intersection is None or intersection.Area() == 0:
                    logger.info("WRS %s_%s does not intersect given ROI. Skip wrs tile.", path, row)
                    add_url = False

            if add_url:
                for mission in ['Landsat8', 'Landsat9']:
                    parameter = self.configuration.get(f'url_parameters_pattern_{mission}')

                    if parameter is None:
                        parameter = self.configuration.get(f'location_{mission}')

                    if parameter is not None:
                        urls.append((self.construct_url(mission, tile, start_date=start_date,
                                    end_date=end_date, path=path, row=row), tile_coverage))

        if not urls:
            logger.warning("No product found for tile %s during period %s - %s", tile, start_date, end_date)

        return urls

    def get_products_from_urls(self, urls, start_date=None, end_date=None, product_mode=False, exclude=None,
                               processing_level=None) -> List[InputProduct]:
        """Get products on tile on the provided time interval.

        :param processing_level: Add processing level for filtering
        :param exclude: List of products to exclude
        :param product_mode: Indicates if we are in product or tile mode
        :param urls: The urls to parse
        :param start_date: Start of the period
        :param end_date: End of the period
        :return: list of selected InputProduct
        """
        input_product_list = []
        for index, (url, tile_coverage) in enumerate(urls, 1):
            logger.debug('Reading product sources: %.2f (%s/%s)', index / len(urls), index, len(urls))
            if self.is_local(url):
                if os.path.exists(url):
                    if product_mode:
                        input_product_list.append(InputProduct(path=url, tile_coverage=tile_coverage))
                    else:
                        input_product_list.extend(
                            [InputProduct(path=os.path.join(url, _dir), tile_coverage=tile_coverage) for _dir in
                             os.listdir(url)])
                else:
                    logger.warning("Missing product path: %s does not exist", url)
            else:
                input_product_list.extend(self.read_products_from_url(url, tile_coverage=tile_coverage))

        processing_level_filter = self.configuration.get('s2_processing_level')

        if processing_level_filter is None:
            processing_level_filter = processing_level

        valid_input_product_list = []
        for input_product in input_product_list:
            input_product.s2l_product_class = get_s2l_product_class(input_product.path)

            if input_product.s2l_product_class is None:
                logger.warning("No S2L Product type found for %s, skip", input_product.path)
                continue

            regexp, date_format = input_product.s2l_product_class.date_format(os.path.basename(input_product.path))
            input_product.date = input_product.s2l_product_class.date(input_product.path, regexp, date_format)
            is_product_valid = self.filter_on_date(input_product, start_date, end_date)

            if input_product.instrument == 'S2' and processing_level_filter is not None:
                is_product_valid &= input_product.s2l_product_class.processing_level(
                    os.path.basename(input_product.path)) == processing_level_filter

            if is_product_valid:
                valid_input_product_list.append(input_product)
                logger.debug('  + %s %s', input_product.s2l_product_class.sensor, os.path.basename(input_product.path))

        # Filter products with exclude list
        if exclude is not None:
            excluded_path = [os.path.normpath(p.path) for p in exclude]
            filtered_products = [p for p in valid_input_product_list if os.path.normpath(p.path) not in excluded_path]
            logger.debug("%s products excluded", len(valid_input_product_list) - len(filtered_products))
            valid_input_product_list = filtered_products

        return self.filter_and_sort_products(valid_input_product_list)

    @staticmethod
    def filter_product_composition(products):
        if products:
            s2l_product_class = get_s2l_product_class(products[0].path)
            try:
                filtered = s2l_product_class.best_product([p.path for p in products])
                return [p for p in products if p.path in filtered]
            except AttributeError:
                logger.debug('%s has no best_product method.', s2l_product_class.__class__.__name__)

        return products

    def filter_on_tile_coverage(self, input_products: List[InputProduct]) -> List[InputProduct]:
        input_products_filtered = []
        # update tile coverage and refilter
        tile_wkt = tile_db.mgrs_to_wkt(self.configuration.get('tile'))
        if tile_wkt is None:
            return input_products_filtered

        tile_polygon = ogr.CreateGeometryFromWkt(tile_wkt)
        coverage = self.configuration.getfloat('coverage')

        if coverage is None:
            coverage = 0.1

        for input_product in input_products:

            if input_product.instrument == 'S2' and input_product.gml_geometry:
                product_polygon = ogr.CreateGeometryFromGML(input_product.gml_geometry)

                logger.debug(
                    'PRODUCT/TILE_COVERAGE: %s/%s', os.path.basename(input_product.path),
                    input_product.tile_coverage)

                input_product.tile_coverage = 100 * product_polygon.Intersection(
                    tile_polygon).GetArea() / tile_polygon.GetArea()

                logger.debug('PRODUCT/TILE_COVERAGE (UPDATED): %s/%s',
                             os.path.basename(input_product.path), input_product.tile_coverage)

                if input_product.tile_coverage > 100 * coverage:
                    input_products_filtered.append(input_product)

            else:
                input_products_filtered.append(input_product)

        return input_products_filtered

    def filter_and_sort_products(self, input_products: List[InputProduct]) -> List[InputProduct]:
        # update tile coverage and filter
        filtered_input_products = self.filter_on_tile_coverage(input_products)

        # Group products by dates
        flipped = defaultdict(lambda: defaultdict(list))
        for input_product in filtered_input_products:
            flipped[input_product.short_date][input_product.instrument].append(input_product)

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
    def filter_on_date(product: InputProduct, start_date=None, end_date=None):
        if product.date is None:
            return False

        logger.debug("Extracted date for %s: %s", product.path, product.date.strftime("%Y/%m/%d"))

        product_is_valid = True
        if start_date:
            product_is_valid &= start_date <= product.date

        if end_date:
            end_date = end_date.replace(hour=23, minute=59, second=59)
            product_is_valid &= product.date <= end_date

        if not product_is_valid:
            logger.debug("Product not contained in %s - %s", start_date.strftime("%Y/%m/%d")
                         if start_date else '', end_date.strftime("%Y/%m/%d") if end_date else '')

        return product_is_valid
