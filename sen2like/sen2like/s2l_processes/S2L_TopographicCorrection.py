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

"""Topographic (Slope) correction processing block module"""

import logging
import math
import os
from typing import NamedTuple

import numpy as np
from core.dem import DEMRepository
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from numpy.typing import NDArray
from osgeo import gdal
from s2l_processes import S2L_Process
from skimage.transform import resize as skit_resize

logger = logging.getLogger("Sen2Like")


class Stat(NamedTuple):
    res: int
    val: dict[str, float]


def _get_resample_array(
    image: S2L_ImageFile, file_path: str, resample_alg: int, description: str
) -> NDArray:
    """Resample one band image file given by file_path to image shape

    Args:
        image (S2L_ImageFile): image to resample
        file_path (str): path to the file to get resample array
        resample_alg (int): skimage resize `order`
            - 0: Nearest-neighbor
            - 1: Bi-linear
            - 2: Bi-quadratic
            - 3: Bi-cubic
            - 4: Bi-quartic
            - 5: Bi-quintic
        description (str): input description (for log purpose)

    Returns:
        NDArray: resampled array
    """
    dataset = gdal.Open(file_path)
    array = np.array(dataset.GetRasterBand(1).ReadAsArray())

    # resize array to image size if needed
    geo = dataset.GetGeoTransform()
    dem_x_res = geo[1]
    if image.xRes != dem_x_res:
        logger.info("Resample %s to image resolution %s", description, image.xRes)
        array = skit_resize(array, image.array.shape, order=resample_alg, preserve_range=True)
        logger.info("Resample done")

    return array


class S2L_TopographicCorrection(S2L_Process):
    """Topographic correction processing block.
    It uses MGRS dem file matching the image to process,
    Generate a shaded relief map elevation raster from the DEM (gdal hillshade) thanks to sun angles
    Compute a topographic correction, and apply it.
    """

    def __init__(
        self,
        dem_repository: DEMRepository,
        topographic_correction_limiter: float,
        apply_valid_pixel_mask: bool,
        generate_intermediate_products: bool,
    ):
        """Constructor

        Args:
            dem_repository (DEMRepository): service to access MGRS DEM
            topographic_correction_limiter (float): max factor value.
            (down factor > topographic_correction_limiter to topographic_correction_limiter)
            apply_valid_pixel_mask (bool): Use valid pixel mask to select pixel for which the correction is done
            generate_intermediate_products (bool): generate or not intermediate image band file
        """
        super().__init__(generate_intermediate_products)
        self._dem_repository = dem_repository
        self._shaded_dem_file = None
        self._apply_valid_pixel_mask = apply_valid_pixel_mask
        self._topographic_correction_limiter = topographic_correction_limiter
        self._stats: Stat | None = None

    def preprocess(self, product: S2L_Product):
        """Create hillshade DEM if possible.
        If not, process will be skipped.

        Args:
            product (S2L_Product): product to have sun angle info for hillshade DEM creation.
        """

        logger.info("Compute hillshade")
        mgrs_dem_file = None
        try:
            mgrs_dem_file = self._dem_repository.get_by_mgrs(product.context.tile)
        except FileNotFoundError:
            logger.warning(
                "Cannot find DEM for tile %s, TopographicCorrection will not be performed",
                product.context.tile,
            )
        else:
            logger.info("Product sun zenith angle %s", product.sun_zenith_angle)
            logger.info("Product sun azimuth angle %s", product.sun_azimuth_angle)

            shaded_dem_file = os.path.join(product.working_dir, "shaded_dem.tiff")
            altitude = 90.0 - np.float32(product.sun_zenith_angle)
            azimuth = np.float32(product.sun_azimuth_angle)

            logger.info("Altitude %s", altitude)

            options = "-compute_edges -az " + str(azimuth) + " -alt " + str(altitude)
            gdal.DEMProcessing(shaded_dem_file, mgrs_dem_file, "hillshade", options=options)

            # set it at the end as it used as condition in the beginning of process function
            self._shaded_dem_file = shaded_dem_file
            logger.info("Hillshade computation finished")

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        """
        preform topographic correction.
        resize hillshade dem to image size if resolution differs.
        skip if hillshade DEM have not been produced by `preprocess`.

        Args:
            product (S2L_Product): product to process
            image (S2L_ImageFile): product image to process
            band (str): band to process

        Returns:
            S2L_ImageFile: image with topographic correction or input image
        """
        if not self._shaded_dem_file:
            logger.warning("Skip topographic correction because DEM is missing")
            return image

        # load hillshade DEM, resize it to image size if needed
        hillshade_array = _get_resample_array(image, self._shaded_dem_file, 3, "hillshade DEM")

        # compute correction factor array
        # topographic_correction_factor is limited using the
        # "topographic_correction_limiter" parameter initially set to 4.0
        logger.info("Compute correction factor for sun zenith angle %s", product.sun_zenith_angle)
        topographic_correction_factor = (
            math.cos(math.radians(product.sun_zenith_angle)) * 255.0 / hillshade_array
        ).clip(min=0.0, max=self._topographic_correction_limiter)

        # apply correction to image
        logger.info("Apply correction factor to band image %s", band)
        array_out = topographic_correction_factor * image.array

        # mask filtering
        # restore initial values on invalid pixels
        if self._apply_valid_pixel_mask:
            logger.info("Apply valid pixel mask")
            mask_array = _get_resample_array(image, product.mask_filename, 0, "valid pixel mask")
            invalid = mask_array == 0
            array_out[invalid] = image.array[invalid]
            # update to compute stats
            topographic_correction_factor = topographic_correction_factor[~invalid]

        # compute stat for higher resolution for QI report
        if not self._stats or self._stats.res > image.xRes:
            self._set_stats(topographic_correction_factor, image.xRes)

        out_image = image.duplicate(self.output_file(product, band), array_out)

        if self.generate_intermediate_products:
            logger.info("Generate intermediate product")
            out_image.write(creation_options=["COMPRESS=LZW"])

        return out_image

    def postprocess(self, product: S2L_Product):
        if self._stats:
            product.metadata.qi["DEM_DATASET"] = self._dem_repository.dataset_name
            product.metadata.qi.update(self._stats.val)

    def _set_stats(self, factor: NDArray, res: float):
        """Set stats at the given resolution

        Args:
            factor (NDArray): factor to compute stats on
            res (float): resolution for which stats are computed
        """
        logger.info("Set stats for resolution %s", res)
        stats = {
            "MIN_TOPOGRAPHIC_CORRECTION_FACTOR": factor.min(),
            "MAX_TOPOGRAPHIC_CORRECTION_FACTOR": factor.max(),
            "AVERAGE_TOPOGRAPHIC_CORRECTION_FACTOR": factor.mean(),
            "STD_TOPOGRAPHIC_CORRECTION_FACTOR": factor.std(),
        }
        self._stats = Stat(res, stats)
