# -*- coding: utf-8 -*-
# Copyright (c) 2023 ESA.
#
# This file is part of Prisma4sen2like.
# See https://github.com/senbox-org/sen2like/prisma4sen2like for further info.
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

import logging
import os
import time

from osgeo import gdal
from prisma_product import PrismaProduct
from spectral_aggregation_functions import *
from sunpy.coordinates import sun

logger = logging.getLogger(__name__)


_ESUN = np.array(
    [
        1874.3,
        1959.75,
        1824.93,
        1512.79,
        1425.78,
        1291.13,
        1175.57,
        1041.28,
        953.93,
        817.58,
        365.41,
        247.08,
        87.75,
    ]
)


class SpectralAggregation:
    def __init__(self, product: PrismaProduct, work_dir: str):
        self._product = product
        # shortcut to h5py.File
        self._product_file = product.product
        self._work_dir = work_dir
        self._p_prisma_vnir = None
        self._p_prisma_swir = None
        self._sun_earth_distance = None
        self._sun_earth_correction = None

    def _generate_coefficients(self):
        start_time = time.time()

        # Create Coefficients output filename
        s2p_aggregation_coefficients_file = os.path.join(
            self._work_dir, "S2P_aggregation_coefficients_P_full_frame_v3.npz"
        )

        if os.path.exists(s2p_aggregation_coefficients_file):
            logger.info("Read all aggregation coefficients from numpy saved file")

            npz_file = np.load(s2p_aggregation_coefficients_file, allow_pickle=True)

            self._p_prisma_vnir = npz_file["p_prisma_vnir"]
            self._p_prisma_swir = npz_file["p_prisma_swir"]

        else:
            logger.info("Generate aggregation coefficients")

            # Compute spectral aggregation coefficients (PRISMA => S2-MSI-A)
            self._p_prisma_vnir, self._p_prisma_swir = generate_aggregation_coefficients_prisma_s2(self._product_file)

            np.savez(
                s2p_aggregation_coefficients_file, p_prisma_vnir=self._p_prisma_vnir, p_prisma_swir=self._p_prisma_swir
            )
            logger.info("Coefficients saved to file %s", s2p_aggregation_coefficients_file)

        logger.info("Aggregation coefficients loaded")

    @property
    def sun_earth_distance(self):
        # Auxiliary data for conversion to TOA reflectance:

        if self._sun_earth_distance:
            return self._sun_earth_distance

        product_start_time = self._product.product_start_time
        sun_earth_distance = sun.earth_distance(product_start_time.raw).value
        sun_earth_correction_esa, sun_earth_distance_esa = sun_earth_correction(product_start_time.as_datetime)
        sza = self._product.sun_zenith_angle

        logger.info(f"Sun Earth distance = {sun_earth_distance:.9f} AU; sza = {sza:.4f} deg")
        logger.info(f"Sun Earth distance ESA = {sun_earth_distance_esa:.9f} AU; sza = {sza:.4f} deg")
        logger.info(f"Sun Earth correction ESA <U> = {sun_earth_correction_esa:.9f} ; sza = {sza:.4f} deg")

        # Apply ESA computation for sun_earth_distance
        self._sun_earth_distance = sun_earth_distance_esa
        self._sun_earth_correction = sun_earth_correction_esa

        return self._sun_earth_distance

    @property
    def sun_earth_correction(self):
        # _sun_earth_correction is computed by sun_earth_distance

        if self._sun_earth_correction:
            return self._sun_earth_correction

        # compute sun earth values
        self.sun_earth_distance

        return self._sun_earth_correction

    def process(self):
        start_time = time.time()

        # -----------------------------------------------------------------------------------------------
        # Generation of spectral aggregation coefficients for PRISMA to Sentinel-2 MSI-A (based on Barry and al)
        # -----------------------------------------------------------------------------------------------

        self._generate_coefficients()

        # -----------------------------------------------------------------------------------------------
        # Read all PRISMA bands (VNIR & SWIR) and convert into radiance units (W.m-2.sr-1.um-1)
        # -----------------------------------------------------------------------------------------------

        # Read VNIR bands (read, rotate, convert to radiance)
        image_cube_vnir_radiance = read_cube_to_radiance(self._product_file, "VNIR")
        logger.info("%s VNIR bands processed (read, rotate, convert to radiance)", image_cube_vnir_radiance.shape[2])

        # Read SWIR bands (read, rotate, convert to radiance)
        image_cube_swir_radiance = read_cube_to_radiance(self._product_file, "SWIR")
        logger.info("%s SWIR bands processed (read, rotate, convert to radiance)", image_cube_swir_radiance.shape[2])

        logger.info("PRISMA VNIR and SWIR Cubes loaded")

        # -----------------------------------------------------------------------------------------------
        # Perform spectral aggregation of PRISMA hyperspectral bands into S2A multi-spectral spectral bands
        # -----------------------------------------------------------------------------------------------

        logger.info("Performing Aggregation and saving S2P radiance and reflectance files")

        # Create output filenames
        out_image_rad = os.path.join(self._work_dir, "S2P_image_cube_toa_radiance_v5.tif")
        out_image_ref = os.path.join(self._work_dir, "S2P_image_cube_toa_reflectance_v5_esa.tif")

        # Image output properties (n_samples, n_lines, n_bands)
        ns = image_cube_vnir_radiance.shape[1]
        nl = image_cube_vnir_radiance.shape[0]
        n_bands_s2 = 13

        # Create Geotiff
        driver = gdal.GetDriverByName("GTiff")
        dest_ds_rad = driver.Create(out_image_rad, ns, nl, n_bands_s2, gdal.GDT_Float32)
        dest_ds_ref = driver.Create(out_image_ref, ns, nl, n_bands_s2, gdal.GDT_Float32)

        for b in range(n_bands_s2):
            if b < 10:
                prisma_s2_toa_radiance = spectral_aggregation_prisma_s2(
                    image_cube_vnir_radiance, self._p_prisma_vnir, b
                )

            else:
                prisma_s2_toa_radiance = spectral_aggregation_prisma_s2(
                    image_cube_swir_radiance, self._p_prisma_swir, b
                )

            # Conversion from radiance (W.m-2.sr-1.um-1) to reflectance (unitless)
            prisma_s2_toa_reflectance = radiance_to_reflectance(
                prisma_s2_toa_radiance, _ESUN[b], self._product.sun_zenith_angle, self.sun_earth_distance
            )

            # Write TOA radiance band to multi-band raster file
            dest_ds_rad.GetRasterBand(b + 1).WriteArray(prisma_s2_toa_radiance)

            # Write TOA reflectance band to multi-band raster file
            dest_ds_ref.GetRasterBand(b + 1).WriteArray(prisma_s2_toa_reflectance)

        # Close properly the datasets
        dest_ds_rad = None
        dest_ds_ref = None

        logger.info("Spectral Aggregation done")

        total_processing_time = time.time() - start_time

        logger.info("Total processing time: %.3f seconds", total_processing_time)
        logger.info("Radiance image : %s", out_image_rad)
        logger.info("Reflectance image : %s", out_image_ref)
        logger.info("Finished")

        return out_image_rad, out_image_ref
