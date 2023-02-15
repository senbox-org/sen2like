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
from typing import List

from core import S2L_config
from core.argparser import Mode
from core.product_archive import tile_db
from core.product_archive.product_archive import InputProductArchive, InputProduct
from core.products.product import S2L_Product
from core.readers import BaseReader


logger = logging.getLogger("Sen2Like")


_LS_SENSOR_MISSION_MAPPING = {"L8": "Landsat8","L9": "Landsat9"}


class ProductPreparator:
    """Product preparator class"""

    def __init__(self, config: S2L_config, args: Namespace):
        """Constructor

        Args:
            config (S2L_config): config to use
            args (Namespace): program arguments
        """
        self._config = config
        self._args = args

    def prepare(self, product: S2L_Product):
        """Search and attach related product to product
        only if S2L_Stitching activated, and extract product files

        Args:
            product (S2L_Product): product to prepare
        """
        # search and attach related product to product
        # only if S2L_Stitching activated
        if self._config.getboolean("doStitching"):
            logger.debug("Stitching Enable, look for related product for %s", product.name)
            self._set_related_product(product)
        else:
            logger.debug("Stitching Disable, skip looking for related product")

        # prepare the product
        self._extract_product_files(product)

    def _search_interrelated_product(
        self, product: S2L_Product, row_offset=1
    ) -> List[InputProduct]:
        """Search product before or after the given product depending offset (for landsat)

        Args:
            product (S2L_Product): search reference product
            row_offset (int, optional): image search offset. Defaults to 1.

        Returns:
            List[InputProduct]: list of product found
        """

        # TODO : see to inject it
        archive = InputProductArchive(self._config)

        _tile = S2L_config.config.get("tile", "31TFJ")

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
            start_date=start_date,
            end_date=end_date,
            exclude=[product],
            processing_level=product.processing_level(product.name),
        )

    def _get_s2_interrelated_product(self, product: S2L_Product) -> InputProduct:

        related_product = None

        logger.debug("Product is located on %s", product.mtl.mgrs)
        products_found = self._search_interrelated_product(product)
        logger.debug("Products on same date:")
        logger.debug(products_found)
        if len(products_found):
            related_product = products_found[0]

        return related_product

    def _get_l8_interrelated_product(self, product: S2L_Product) -> InputProduct:

        related_product = None

        _same_utm_only = S2L_config.config.getboolean("same_utm_only")
        products = []
        logger.debug(
            "Product is located on [%s, %s]", product.mtl.path, product.mtl.row
        )
        logger.debug(
            "Product tile coverage: %s",
            tile_db.get_coverage((product.mtl.path, product.mtl.row), product.mtl.mgrs),
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
                    (path, row), product.mtl.mgrs, _same_utm_only
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

        related_input_product = None
        if product.sensor in ("L8", "L9"):
            related_input_product = self._get_l8_interrelated_product(product)
        elif product.sensor == "S2":
            related_input_product = self._get_s2_interrelated_product(product)

        if related_input_product is None:
            logger.info("No product found for stitching")
        else:
            product.related_product = related_input_product.s2l_product_class(
                related_input_product.path
            )

    def _extract_aux_product_files(self, product: S2L_Product):
        """Extract aux product files of the product and its related product if any.
        - angle images (see 'S2L_Product.get_angle_images' impl)
        - valid and no data pixel masks (see 'S2L_Product.get_valid_pixel_mask' impl)
        - NDVI image

        Args:
            product (S2L_Product): product that should have aux data files
        """

        working_dir = os.path.join(self._config.get("wd"), product.name)

        # Angles extraction
        product.get_angle_images(os.path.join(working_dir, "tie_points.tif"))

        # extract masks
        roi_file = (
            self._args.roi if self._args.operational_mode == Mode.ROI_BASED else None
        )
        product.get_valid_pixel_mask(
            os.path.join(working_dir, "valid_pixel_mask.tif"), roi_file
        )

        # extract NDVI
        if self._config.get("nbar_methode") == "VJB":
            product.get_ndvi_image(os.path.join(working_dir, "ndvi.tif"))

        # extract aux files of related product if any
        # if product.related_product is not None:
        #     self._extract_aux_product_files(product.related_product)

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
        
        # create working directory and save conf (traceability)
        working_dir = os.path.join(self._config.get("wd"), product.name)
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

        # Get scl map for valid pixel mask
        scl_dir = self._config.get("scl_dir")
        if (
            scl_dir
            and (not self._config.getboolean("use_sen2cor"))
            and product_reader.data_type != "Level-2A"
        ):
            product_reader.scene_classif_band = self._get_scl_map(scl_dir, product)

        # extract aux files product and its related product if any
        self._extract_aux_product_files(product)

        # extract aux files of related product if any
        if product.related_product is not None:
            self._extract_product_files(product.related_product)

    def _get_scl_map(self, scl_dir, product):
        scl_map = None
        tilecode = product.mtl.mgrs

        if product.sensor == "S2":
            acq_date = datetime.datetime.strftime(
                product.dt_sensing_start, "%Y%m%dT%H%M%S"
            )
        else:
            acq_date = datetime.datetime.strftime(product.acqdate, "%Y%m%dT%H%M%S")

        result = glob.glob(
            os.path.join(scl_dir, tilecode, f"T{tilecode}_{acq_date}_SCL_60m.tif")
        )
        if result:
            scl_map = result[0]

        if scl_map is not None:
            logger.info("Auxiliary scene classification map found: %s", scl_map)
        else:
            logger.info("Auxiliary scene classification map NOT found.")

        return scl_map
