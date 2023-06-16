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
Module dedicated to product preparation before 
running processing blocks.
"""
import datetime
import glob
import logging
import os
import shutil
from argparse import Namespace

from core.argparser import Mode
from core.product_archive import tile_db
from core.product_archive.product_archive import InputProduct, InputProductArchive
from core.products.product import S2L_Product
from core.readers import BaseReader
from core.S2L_config import S2L_Config

logger = logging.getLogger("Sen2Like")


_LS_SENSOR_MISSION_MAPPING = {"L8": "Landsat8","L9": "Landsat9"}


class ProductPreparator:
    """Product preparator class"""

    def __init__(self, config: S2L_Config, args: Namespace, ref_image: str):
        """Constructor

        Args:
            config (S2L_config): config to use
            args (Namespace): program arguments
        """
        self._config = config
        self._roi_file = (
            args.roi if args.operational_mode == Mode.ROI_BASED else None
        )
        self._ref_image = ref_image

    def prepare(self, product: S2L_Product):
        """Prepare the product for processing bloc exec on it.
        - Search and attach related product to product only if S2L_Stitching activated,
        - Extract product files,
        - Set ref_image on the product and on its related product if any,
        - Set product and its related product if any, working_dir

        Args:
            product (S2L_Product): product to prepare
        """
        product.ref_image = self._ref_image
        # set product working dir with name of new product
        product.working_dir = os.path.join(self._config.get("wd"), product.name)

        # search and attach related product to product
        # only if S2L_Stitching activated
        if product.context.doStitching:
            logger.debug("Stitching Enable, look for related product for %s", product.name)
            self._set_related_product(product)
        else:
            logger.debug("Stitching Disable, skip looking for related product")

        # prepare the product
        self._extract_product_files(product)

    def _search_interrelated_product(
        self, product: S2L_Product, row_offset=1
    ) -> list[InputProduct]:
        """Search product before or after the given product depending offset (for landsat)

        Args:
            product (S2L_Product): search reference product
            row_offset (int, optional): image search offset. Defaults to 1.

        Returns:
            List[InputProduct]: list of product found
        """

        # TODO : see to inject it
        archive = InputProductArchive(self._config)

        _tile = product.context.tile

        start_date = product.acqdate.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = product.acqdate.replace(hour=23, minute=59, second=59)

        search_urls = []
        if product.sensor in _LS_SENSOR_MISSION_MAPPING:
            if product.mtl.row is not None:
                row = int(product.mtl.row) + row_offset
            else:
                row = product.mtl.row
                logger.debug("Search product on path [%s, %s]", product.mtl.path, row)

            search_urls.extend([
                (
                    archive.construct_url(
                        _LS_SENSOR_MISSION_MAPPING.get(product.sensor),
                        path=product.mtl.path,
                        row=row,
                        start_date=start_date,
                        end_date=end_date,
                        cloud_cover=100,
                    ),
                    None,
                )
            ])
        else:
            logger.debug("Search product on same tile [%s]", _tile)
            search_urls.extend([
                (
                    archive.construct_url(
                        "Sentinel2",
                        tile=_tile,
                        start_date=start_date,
                        end_date=end_date,
                        cloud_cover=100,
                    ),
                    None,
                )
            ])

        # get products as InputProduct
        logger.debug("Urls: %s", search_urls)
        return archive.search_product(
            search_urls,
            _tile,
            start_date=start_date,
            end_date=end_date,
            exclude=[product],
            processing_level=product.processing_level(product.name),
        )

    def _get_s2_interrelated_product(self, product: S2L_Product) -> InputProduct:

        related_product = None

        logger.debug("Product is located on %s", product.mgrs)
        products_found = self._search_interrelated_product(product)
        logger.debug("Products on same date:")
        logger.debug(products_found)
        if len(products_found):
            # verify instrument as S2A/B cannot be stitched with S2P 
            # S2P product archive is the same as S2A/B, so we must check
            for rel_product in products_found:
                if product.sensor == rel_product.instrument:
                    return rel_product

        return related_product

    def _get_l8_interrelated_product(self, product: S2L_Product) -> InputProduct:

        related_product = None

        _same_utm_only = self._config.getboolean("same_utm_only")
        products = []
        logger.debug(
            "Product is located on [%s, %s]", product.mtl.path, product.mtl.row
        )
        logger.debug(
            "Product tile coverage: %s",
            tile_db.get_coverage((product.mtl.path, product.mtl.row), product.mgrs),
        )
        # Get previous and next product, then test eligibility
        for row_offset in [-1, 1]:
            products_found = self._search_interrelated_product(
                product, row_offset=row_offset
            )
            logger.debug("Products for row_offset: %s", row_offset)
            logger.debug([p.path for p in products_found])
            if len(products_found):
                # usage of _same_utm_only help to filter or not the product
                # if True, returned coverage will be 0
                path = int(product.mtl.path)
                row = int(product.mtl.row) + row_offset

                coverage = tile_db.get_coverage(
                    (path, row), product.mgrs, _same_utm_only
                )

                logger.debug(
                    "Coverage form path/row/same_utm %s/%s/%s : %s",
                    path,
                    row,
                    _same_utm_only,
                    coverage,
                )

                if coverage > 0.001:
                    products.append((products_found[0], coverage))

        # TODO : maybe allow to get product that cover, not only the most covering
        if len(products) > 0:
            products = sorted(products, key=lambda t: t[1], reverse=True)
            related_product = products[0][0]
            logger.info("Product found for stitching %s:", related_product.path)

        return related_product

    def _set_related_product(self, product: S2L_Product):
        """Look for related product and attach it on the product if any.
        Also set ref_image on the related product

        Args:
            product (S2L_Product): product to search related for
        """
        related_input_product = None
        if product.sensor in ("L8", "L9"):
            related_input_product = self._get_l8_interrelated_product(product)
        elif product.sensor == "S2":
            related_input_product = self._get_s2_interrelated_product(product)
        else:
            logger.warning("stitching not supported for sensor %s", product.sensor)

        if related_input_product is None:
            logger.info("No product found for stitching")
        else:
            product.related_product = related_input_product.s2l_product_class(
                related_input_product.path,
                product.context
            )

            # set related product working dir
            product.related_product.working_dir = os.path.join(
                self._config.get("wd"),
                product.related_product.name
            )

            # set ref image to the related product
            product.related_product.ref_image = self._ref_image

    def _extract_aux_product_files(self, product: S2L_Product):
        """Extract aux product files of the product and its related product if any.
        - angle images (see 'S2L_Product.get_angle_images' impl)
        - valid and no data pixel masks (see 'S2L_Product.get_valid_pixel_mask' impl)
        - NDVI image

        Args:
            product (S2L_Product): product that should have aux data files
        """

        working_dir = product.working_dir

        # Angles extraction
        product.get_angle_images(os.path.join(working_dir, "tie_points.tif"))

        # extract masks
        product.get_valid_pixel_mask(
            os.path.join(working_dir, "valid_pixel_mask.tif"), self._roi_file
        )

        # extract NDVI
        if self._config.get("nbar_methode") == "VJB":
            product.get_ndvi_image(os.path.join(working_dir, "ndvi.tif"))

    def _extract_product_files(self, product: S2L_Product):
        """Prepare the product before process by extracting
        some files in the current working dir when possible.
        Extracted data from product are :
        - product metadata file
        - product tile metadata file
        - product aux files (angle images , masks, NDVI image)
        Args:
            product (S2L_Product): product to prepare
        """

        # create working directory
        working_dir = product.working_dir
        if not os.path.exists(working_dir):
            os.makedirs(working_dir)

        product_reader: BaseReader = product.mtl

        # copy MTL files in final product
        shutil.copyfile(
            product_reader.mtl_file_name,
            os.path.join(working_dir, os.path.basename(product_reader.mtl_file_name)),
        )
        if product_reader.tile_metadata:
            shutil.copyfile(
                product_reader.tile_metadata,
                os.path.join(
                    working_dir, os.path.basename(product_reader.tile_metadata)
                ),
            )

        # Get scl map for valid pixel mask for L1C as aux data
        scl_dir = self._config.get("scl_dir")
        if (
            scl_dir
            and (not product.context.use_sen2cor)
            and product_reader.data_type != "Level-2A"
        ):
            product_reader.scene_classif_band = self._get_scl_map(scl_dir, product)

        # extract aux files product and its related product if any
        self._extract_aux_product_files(product)

        # extract aux files of related product if any
        if product.related_product is not None:
            self._extract_product_files(product.related_product)

    def _get_scl_map(self, scl_dir: str, product: S2L_Product):
        scl_map = None

        if product.sensor == "S2":
            acq_date = datetime.datetime.strftime(
                product.dt_sensing_start, "%Y%m%dT%H%M%S"
            )
        else:
            acq_date = datetime.datetime.strftime(product.acqdate, "%Y%m%dT%H%M%S")

        result = glob.glob(
            os.path.join(scl_dir, product.mgrs, f"T{product.mgrs}_{acq_date}_SCL_60m.tif")
        )
        if result:
            scl_map = result[0]

        if scl_map is not None:
            logger.info("Auxiliary scene classification map found: %s", scl_map)
        else:
            logger.info("Auxiliary scene classification map NOT found.")

        return scl_map
