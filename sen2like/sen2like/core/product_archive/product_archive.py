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

import json
import logging
import os
import time
import urllib
from collections import defaultdict
from datetime import datetime
from urllib.request import urlopen

from osgeo import ogr

from core import S2L_config
from core.product_archive import tile_db
from core.products import get_s2l_product_class

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
        return datetime(self.date.year, self.date.month, self.date.day) if self.date else None


class InputProductArchive:
    """Input product archive to retrieve products from there they are stored
    """
    def __init__(self, configuration: S2L_config, roi=None):
        self.config = configuration
        self.roi = roi

    def construct_url(self, mission, tile=None, start_date=None, end_date=None, path=None, row=None, cloud_cover=None):
        # WARN : load variable to having them in the local scope when using **locals()
        base_url_landsat = self.config.get('base_url_landsat')
        base_url_s2 = self.config.get('base_url_s2')
        base_url = self.config.get('base_url')
        # TODO : specific to s2, see how to avoid it here
        s2_processing_level = self.config.get('s2_processing_level')

        # Special formatting for date
        if start_date:
            start_date = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        if end_date:
            end_date = end_date.strftime("%Y-%m-%dT23:59:59")

        parameter = self.config.get(f'url_parameters_pattern_{mission}')
        if parameter is None:
            parameter = self.config.get('url_parameters_pattern')

        # Get location parameter depending on mission, then format it with available local variable
        location = self.config.get(f'location_{mission}', "").format(**locals())
        if cloud_cover is None:
            cloud_cover = self.config.get('cloud_cover', 10)

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
        except urllib.error.HTTPError as http_error:
            logger.error("Cannot read %s", url)
            logger.error(http_error)
            # for now only check 404, but could be some other
            if http_error.code == 404:
                raise
            return {}
        except (urllib.error.URLError, ValueError) as error:
            logger.error("Cannot read %s", url)
            logger.error(error)
            return {}


    def read_products_from_url(self, url, tile_coverage) -> list[InputProduct]:
        input_product_list: list[InputProduct] = []
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
            for _property in self.config.get("thumbnail_property").split('/'):
                _product = _product.get(_property, {})
            input_product.path = _product
            _cloud_cover = product
            for _property in self.config.get("cloud_cover_property").split('/'):
                _cloud_cover = _cloud_cover.get(_property, {})
            input_product.cloud_cover = _cloud_cover
            _gml_geometry = product
            for _property in self.config.get("gml_geometry_property").split('/'):
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

    def get_search_url_from_tile(self, tile: str, start_date: datetime=None, end_date: datetime=None) -> list[tuple]:
        """Get products URL on tile on the provided time interval, sorted by tile coverage
        - For local URL, URLs are folder that should contains products, not full product path.
        - For remote URL, URLs are remote catalogue search URL.

        Args:
            tile (str): MGRS tile code
            start_date (datetime, optional): Start of the period. Defaults to None.
            end_date (datetime, optional): End of the period. Defaults to None.

        Returns:
            List[Tuple]: list of url,coverage tuple, sorted by tile coverage.
            Example: 
            [
                 ('/data/Products/Sentinel2/12SYH', 1), 
                 ('/data/Products/Landsat8/35/33', 0.7126961469055555), 
                 ('/data/Products/Landsat9/35/33', 0.7126961469055555), 
                 ('/data/Products/Landsat8/35/34', 0.46340014084620473), 
                 ...
             ]
        """
        # get path row for landsat product url to build
        same_utm = not self.config.getboolean("allow_other_srs")
        # wrs tiles are sorted by coverage
        wrs = tile_db.mgrs_to_wrs(
            tile, self.config.getfloat("coverage"),
            same_utm=same_utm
        )

        logger.debug("%s > %s", tile, wrs)
        # Build urls for Sentinel2
        urls = [(self.construct_url("Sentinel2", tile, start_date=start_date, end_date=end_date), 1)]
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
                    parameter = self.config.get(f'url_parameters_pattern_{mission}')

                    if parameter is None:
                        parameter = self.config.get(f'location_{mission}')

                    if parameter is not None:
                        urls.append((self.construct_url(mission, tile, start_date=start_date,
                                    end_date=end_date, path=path, row=row), tile_coverage))

        if not urls:
            logger.warning("No product found for tile %s during period %s - %s", tile, start_date, end_date)

        return urls

    def _load_input_product(self, urls: list[tuple[str,float]], product_mode: bool) -> list[InputProduct]:
        """Looks for product in their archive and load founded ones

        Args:
            urls (List[Tuple[str,float]]): list of search urls,coverage tuple
            product_mode (bool): Indicates if we are in product mode or not

        Returns:
            List[InputProduct]: founded archived products
        """
        input_product_list = []
        for index, (url, tile_coverage) in enumerate(urls, 1):
            logger.debug('Reading product sources: %.2f (%s/%s)', index / len(urls), index, len(urls))
            if self.is_local(url):
                if os.path.exists(url):
                    if product_mode:
                        input_product_list.append(InputProduct(path=url, tile_coverage=tile_coverage))
                    else:
                        # url are directories that contains products, so list url to complete product path
                        input_product_list.extend(
                            [InputProduct(path=os.path.join(url, _dir), tile_coverage=tile_coverage) for _dir in
                             os.listdir(url)])
                else:
                    logger.warning("Missing product path: %s does not exist", url)
            else:
                input_product_list.extend(self.read_products_from_url(url, tile_coverage=tile_coverage))

        return input_product_list

    def _filter_valid_products(self, input_product_list: list[InputProduct], start_date: datetime, end_date: datetime, processing_level_filter) -> list[InputProduct]:
        """Filter product by checking if it is in the given period and its processing level

        Args:
            input_product_list (List[InputProduct]): list input product to filter
            start_date (datetime): period start date
            end_date (datetime): period end date
            processing_level_filter (str): processing level filter

        Returns:
            List[InputProduct]: valid input product
        """
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

        return valid_input_product_list

    # FIXME remove exclusion, it exists only for stitching
    # see to manage that only where needed
    def search_product(self, urls, tile, start_date: datetime=None, end_date: datetime=None, product_mode=False, exclude=None,
                               processing_level=None) -> list[InputProduct]:
        """Get products on tile on the provided time interval.
        
        :param urls: list of search urls,coverage tuple
        :param tile: tile for which search product
        :param start_date: Start of the period
        :param end_date: End of the period
        :param product_mode: Indicates if we are in product or tile mode
        :param exclude: List of products to exclude
        :param processing_level: Add processing level for filtering
        :return: list of selected InputProduct
        """
        input_product_list = self._load_input_product(urls, product_mode)
        
        processing_level_filter = self.config.get('s2_processing_level')

        if processing_level_filter is None:
            processing_level_filter = processing_level

        valid_input_product_list = self._filter_valid_products(
            input_product_list, start_date, end_date, processing_level_filter)
        
        # Filter products with exclude list
        if exclude is not None:
            excluded_path = [os.path.normpath(p.path) for p in exclude]
            filtered_products = [p for p in valid_input_product_list if os.path.normpath(p.path) not in excluded_path]
            logger.debug("%s products excluded", len(valid_input_product_list) - len(filtered_products))
            valid_input_product_list = filtered_products

        return self._filter_and_sort_products(valid_input_product_list, tile)

    @staticmethod
    def filter_product_composition(products: list[InputProduct]):
        if products:
            s2l_product_class = get_s2l_product_class(products[0].path)
            filtered = s2l_product_class.best_product([p.path for p in products])
            return [p for p in products if p.path in filtered]

        return products

    def filter_on_tile_coverage(self, input_products: list[InputProduct], tile: str) -> list[InputProduct]:
        input_products_filtered = []
        # update tile coverage and refilter
        tile_wkt = tile_db.mgrs_to_wkt(tile)
        if tile_wkt is None:
            return input_products_filtered

        tile_polygon = ogr.CreateGeometryFromWkt(tile_wkt)
        coverage = self.config.getfloat('coverage')

        if coverage is None:
            coverage = 0.1

        for input_product in input_products:

            logger.debug(
                    'PRODUCT/TILE_COVERAGE: %s/%s', os.path.basename(input_product.path),
                    input_product.tile_coverage)

            if input_product.instrument == 'S2' and input_product.gml_geometry:
                product_polygon = ogr.CreateGeometryFromGML(input_product.gml_geometry)

                input_product.tile_coverage = product_polygon.Intersection(
                    tile_polygon).GetArea() / tile_polygon.GetArea()

                logger.debug('PRODUCT/TILE_COVERAGE (UPDATED): %s/%s',
                             os.path.basename(input_product.path), input_product.tile_coverage)

                if input_product.tile_coverage > coverage:
                    input_products_filtered.append(input_product)

            else:
                input_products_filtered.append(input_product)

        return input_products_filtered

    def _filter_and_sort_products(self, input_products: list[InputProduct], tile) -> list[InputProduct]:
        # update tile coverage and filter
        filtered_input_products = self.filter_on_tile_coverage(input_products, tile)

        # Group products by dates
        flipped = defaultdict(lambda: defaultdict(list))
        for input_product in filtered_input_products:
            flipped[input_product.short_date][input_product.instrument].append(input_product)

        results = []
        for date, instruments in flipped.items():
            for instrument, _products in instruments.items():

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
