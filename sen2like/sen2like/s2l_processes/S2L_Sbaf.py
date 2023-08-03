#! /usr/bin/env python
# -*- coding: utf-8 -*-
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


import logging
from typing import NamedTuple

import numpy as np
from core.image_file import S2L_ImageFile
from core.products.landsat_8.landsat8 import Landsat8Product
from core.products.product import S2L_Product
from numpy.typing import NDArray
from s2l_processes.S2L_Process import S2L_Process
from skimage.transform import resize as skit_resize

log = logging.getLogger("Sen2Like")


class SbafParams(NamedTuple):
    """Simple sbaff param storage"""

    slope: float
    offset: float


# params
adaptive_adj_coef = {}
adaptive_adj_coef["B01"] = {"bandLabel": "CA", "coef": SbafParams(-0.13363398, 0.92552824)}
adaptive_adj_coef["B02"] = {"bandLabel": "BLUE", "coef": SbafParams(0.1422238, 1.05114394)}
adaptive_adj_coef["B03"] = {"bandLabel": "GREEN", "coef": SbafParams(0.00898318, 0.97937428)}
adaptive_adj_coef["B04"] = {"bandLabel": "RED", "coef": SbafParams(-0.09417763, 1.0296573)}
adaptive_adj_coef["B8A"] = {"bandLabel": "NIR 20", "coef": SbafParams(-0.00292645, 0.99517658)}
adaptive_adj_coef["B11"] = {"bandLabel": "SWIR 1", "coef": SbafParams(0.01377031, 0.99593527)}
adaptive_adj_coef["B12"] = {"bandLabel": "SWIR 2", "coef": SbafParams(0.01272434, 0.97395877)}


class S2L_Sbaf(S2L_Process):
    def __init__(
        self,
        adaptative: bool,
        adaptative_band_candidates: list[str],
        generate_intermediate_products: bool,
    ):
        """Constructor

        Args:
            adaptative (bool): use adaptative SBAF. If False, standard slope and offset are used.
            generate_intermediate_products (bool): generate or not intermediate image
            adaptative_band_candidates (list[str]): list of band (S2 band name) that to treat with adaptative method if enabled
        """
        super().__init__(generate_intermediate_products)
        self._adaptative: bool = adaptative
        self._adaptative_band_candidates: list[str] = adaptative_band_candidates
        # store used params for QI report
        self._sbaf_params: dict[str, SbafParams] = {}

    def get_sen2like_coef(self, mission):
        """
        Derived from value in HLS Guide v 1.4
        Get Adjustment coefficient for SEN2LIKE processing,
        Coefficient applied to Landsat8/OLI towards Sentinel2A/MSI data
        Coef array definition [slope, intercept]"""

        adj_coef = {}
        if mission in ("LANDSAT_8", "LANDSAT_9"):
            adj_coef["B01"] = {"bandLabel": "CA"}
            adj_coef["B02"] = {"bandLabel": "BLUE"}
            adj_coef["B03"] = {"bandLabel": "GREEN"}
            adj_coef["B04"] = {"bandLabel": "RED"}
            adj_coef["B05"] = {"bandLabel": "NIR 20"}
            adj_coef["B06"] = {"bandLabel": "SWIR 1"}
            adj_coef["B07"] = {"bandLabel": "SWIR 2"}

            # compute coeff from Nasa SBAF values
            adj_coef_l8_s2a = self.get_oli_like_coef("Sentinel-2A")
            for oli_band, band_coef in adj_coef.items():
                s2_band = Landsat8Product.get_s2like_band(oli_band)
                if not s2_band:
                    continue
                coef = adj_coef_l8_s2a[s2_band]["coef"]
                slope = 1 / coef.slope
                offset = -coef.offset / coef.slope
                band_coef["coef"] = SbafParams(slope, offset)

        return adj_coef

    def get_oli_like_coef(self, mission):
        """S.Saunier 20/11/2018
        Value in HLS Guide v 1.4
        Get Adjustment coefficient for OLI LIKE processing,
        Coefficient applied to Sentinel 2 S30 data  and NOT to Landsat
        data
        Coef array definition [slope, intercept]"""

        adj_coef = {}
        if mission == "Sentinel-2A":
            adj_coef["B01"] = {"bandLabel": "CA", "coef": SbafParams(0.9959, -0.0002)}
            adj_coef["B02"] = {"bandLabel": "BLUE", "coef": SbafParams(0.9778, -0.004)}
            adj_coef["B03"] = {"bandLabel": "GREEN", "coef": SbafParams(1.0053, -0.0009)}
            adj_coef["B04"] = {"bandLabel": "RED", "coef": SbafParams(0.9765, 0.0009)}
            adj_coef["B8A"] = {"bandLabel": "NIR 20", "coef": SbafParams(0.9983, -0.0001)}
            adj_coef["B11"] = {"bandLabel": "SWIR 1", "coef": SbafParams(0.9987, -0.0011)}
            adj_coef["B12"] = {"bandLabel": "SWIR 2", "coef": SbafParams(1.003, -0.0012)}

        elif mission == "Sentinel-2B":
            adj_coef["B01"] = {"bandLabel": "CA", "coef": SbafParams(0.9959, -0.0002)}
            adj_coef["B02"] = {"bandLabel": "BLUE", "coef": SbafParams(0.9778, -0.004)}
            adj_coef["B03"] = {"bandLabel": "GREEN", "coef": SbafParams(1.0075, -0.0008)}
            adj_coef["B04"] = {"bandLabel": "RED", "coef": SbafParams(0.9761, 0.001)}
            adj_coef["B8A"] = {"bandLabel": "NIR 20", "coef": SbafParams(0.9966, 0.000)}
            adj_coef["B11"] = {"bandLabel": "SWIR 1", "coef": SbafParams(1.000, -0.0003)}
            adj_coef["B12"] = {"bandLabel": "SWIR 2", "coef": SbafParams(0.9867, 0.0004)}

        return adj_coef

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        log.info("Start")

        # init to None
        sbaf_params = None

        if not product.apply_sbaf_param:
            # Feed params for QI report
            self._sbaf_params[band] = SbafParams(1, 0)
            log.info("Skip for %s", product.mtl.mission)
            log.info("End")
            return image

        # TODO : what about MAJA product ?
        # (where mission is LANDSAT8,LANDSAT9, SENTINEL2) it will be None, is that right ?
        if product.mtl.mission in ("LANDSAT_8", "LANDSAT_9"):
            # L8 => S2A
            band_sbaf = band
            adj_coef = self.get_sen2like_coef(product.mtl.mission)
            if band_sbaf in adj_coef:
                log.info("Sbaf coefficient find to %s", band)
                sbaf_params = adj_coef[band_sbaf]["coef"]
                log.info(str(sbaf_params))
            else:
                self._sbaf_params[band] = SbafParams(1, 0)
                log.info("No Sbaf coefficient defined for %s", band)
                return image

        self._sbaf_params[band] = sbaf_params

        # Apply SBAF
        if sbaf_params is not None:
            new_image_array = self._do_sbaf(product, image, band, self._sbaf_params[band])

            # Format Output : duplicate, link  to product as parameter
            image = image.duplicate(
                self.output_file(product, band), array=new_image_array.astype(np.float32)
            )

            if self.generate_intermediate_products:
                image.write(creation_options=["COMPRESS=LZW"])

        log.info("End")

        return image

    def postprocess(self, product: S2L_Product):
        """Set QI parameters

        Args:
            product (S2L_Product): product to post process
        """
        product.metadata.qi["SBAF_ADAPTATIVE"] = self._adaptative

        if self._adaptative:
            # select only processed bands
            product.metadata.qi["SBAF_ADAPTED_BANDS"] = " ".join(
                product.__class__.get_s2like_band(band)
                for band in self._sbaf_params
                if band in self._adaptative_band_candidates
            )

        for band, params in self._sbaf_params.items():
            # set sbaf qi param with S2 band naming
            s2_band = product.__class__.get_s2like_band(band)
            if not s2_band:
                # avoid Non Sentinel native band
                continue
            product.metadata.qi[f"SBAF_COEFFICIENT_{s2_band}"] = params.slope
            product.metadata.qi[f"SBAF_OFFSET_{s2_band}"] = params.offset

    def _do_sbaf(
        self, product: S2L_Product, image: S2L_ImageFile, band: str, static_params: SbafParams
    ) -> NDArray:
        """Apply sbaf to an image band.
        Depending the processing block configuration, static or adaptative method is applied.
        Even if adaptative method should be applied, some image band values will be treat
        with static because adaptative have no sense for them.

        Args:
            product (S2L_Product): current processed product
            image (S2L_ImageFile): band image to which apply sbaf
            band (str): image band name
            static_params (SbafParams): static params,

        Returns:
            NDArray: adapted image band values
        """
        log.debug("Applying SBAF")

        new_image_array = None
        if (
            self._adaptative
            and product.__class__.get_s2like_band(band) in self._adaptative_band_candidates
        ):
            log.info("Use adaptative method for band %s", band)

            ndvi_image_array = self._get_ndvi_image_array(product, image)
            # given band is the product mission band name, use its corresponding S2 band to get sbaf param
            adaptative_param = adaptive_adj_coef[product.__class__.get_s2like_band(band)]["coef"]
            log.info(str(adaptative_param))
            factor = adaptative_param.slope * ndvi_image_array + adaptative_param.offset
            new_image_array = image.array * factor
            # apply static method on water, barren areas of rock, sand, or snow
            # adaptative have no sense for them
            where = ndvi_image_array <= 0.1
            new_image_array[where] = self._apply_static(image.array[where], static_params)

            # override QI report info
            self._sbaf_params[band] = adaptative_param
        else:
            log.info("Use static method")
            new_image_array = self._apply_static(image.array, static_params)

        # restore no data
        new_image_array[image.array == 0] = 0

        return new_image_array

    def _apply_static(self, in_array: NDArray, sbaf_params: SbafParams) -> NDArray:
        """Apply simple sbaf method to an image band

        Args:
            in_array (NDArray): band image values
            sbaf_params (SbafParams): sbaf param to apply

        Returns:
            NDArray: Adapted values
        """
        return in_array * sbaf_params.slope + sbaf_params.offset

    def _get_ndvi_image_array(self, product: S2L_Product, image: S2L_ImageFile) -> NDArray:
        """Get product NDVI as array having same shape as image

        Args:
            product (S2L_Product): product for which get the NDVI
            image (S2L_ImageFile): image to get shape and resolution necessary to extract NDVI

        Returns:
            NDArray: NDVI image array, resampled to image shape if needed
        """
        ndvi_image = S2L_ImageFile(product.ndvi_filename)
        ndvi_image_array = ndvi_image.array
        if ndvi_image.xRes != image.xRes:
            log.info("Resample NDVI image band resolution %s", image.xRes)
            ndvi_image_array = skit_resize(
                ndvi_image.array, image.array.shape, order=3, preserve_range=True
            )
            log.info("Resample done")

        return ndvi_image_array


"""
factor = a * NDVI + b
out = image * factor
out[ndvi < 0.1] = calcul normal

Ajouter la méthode dans les qi report (nom des méthodes à déterminer)
a et b configurable par bande ou en dur ?

resize NDVI pour les images qui ne sont pas à la résolution du NDVI

quelles valeurs pour les slope et offset dans le cas de l'adaptative ? a & b ?
"""
