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

"""Geometry verification module"""
import logging
import os

import numpy as np
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from core.reference_image import get_resampled_ref_image
from klt import KLTMatcher, KTLResult
from s2l_processes.S2L_Process import S2L_Process
from scipy.stats import kurtosis, skew

log = logging.getLogger("Sen2Like")


class S2L_GeometryCheck(S2L_Process):
    """Class to verify product geometry"""

    def __init__(
        self,
        klt_matcher: KLTMatcher,
        assess_bands: list[str],
        reference_band: str,
        generate_intermediate_products: bool,
    ):
        """Constructor

        Args:
            klt_matcher (KLTMatcher): KLT matcher component
            assess_bands (list[str]): list of S2 band name for which to do the assessment.
            For other missions, band name resolution will be performed
            reference_band (str): reference band name that is used for correction
            generate_intermediate_products (bool): generate or not intermediate image products.
        """
        super().__init__(generate_intermediate_products)
        self._tmp_stats = {}
        self._assess_bands = assess_bands
        self._reference_band = reference_band
        self._klt_matcher = klt_matcher

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:

        # do Geometry Assessment only if required
        assess_geometry_bands = [
            product.reverse_bands_mapping.get(band) for band in self._assess_bands
        ]

        if assess_geometry_bands and band in assess_geometry_bands:
            # open validity mask
            mask = S2L_ImageFile(product.mask_filename)

            log.info("Geometry assessment for band %s", band)

            ref_image = get_resampled_ref_image(image, product.ref_image)
            if ref_image is None:
                log.warning(
                    "Abort geometry assessment, no reference image found for %s", image.filepath
                )
                # abort, cannot do matching without ref image
                return image

            # Coarse resolution of correlation grid (only for stats)
            klt_result = self._matching(
                ref_image, image, mask, product.working_dir, product.ref_image
            )

            log.info(
                "Geometrical Offsets after correction if any (DX/DY): %sm %sm",
                klt_result.dx_array.mean(),
                klt_result.dy_array.mean(),
            )

            # Append bands name to keys
            if self._reference_band != band:
                for key in self._tmp_stats:
                    self._tmp_stats[f"{key}_{band}"] = self._tmp_stats.pop(key)

            # set qi info to reference band stats
            product.metadata.qi.update(self._tmp_stats)

            # clear for next band process
            self._tmp_stats = {}

        return image

    def _matching(
        self,
        image_ref: S2L_ImageFile,
        image: S2L_ImageFile,
        mask: S2L_ImageFile,
        working_dir: str,
        ref_image_path: str,
    ) -> KTLResult:
        log.info("Start matching")

        # do matching with KLT
        result = self._klt_matcher.do_matching(
            working_dir, image_ref, image, mask.array, assessment=True
        )

        dx = result.dx_array
        dy = result.dy_array

        dist = np.sqrt(np.power(dx, 2) + np.power(dy, 2)).flatten()
        self._tmp_stats.update(
            {
                "SKEW": np.round(skew(dist, axis=None), 1),
                "KURTOSIS": np.round(kurtosis(dist, axis=None), 1),
                "REF_IMAGE": os.path.basename(ref_image_path),
                "MEAN": np.round(np.mean(dist), 1),
                "MEAN_X": dx.mean(),
                "MEAN_Y": dy.mean(),
                "STD": np.round(np.std(dist), 1),
                "STD_X": np.round(np.std(dx), 1),
                "STD_Y": np.round(np.std(dy), 1),
                "RMSE": np.round(np.sqrt(np.mean(np.power(dist, 2))), 1),
                "NB_OF_POINTS": result.nb_matching_point,
            }
        )

        return result
