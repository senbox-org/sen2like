#! /usr/bin/env python
# -*- coding: utf-8 -*-
# S. Saunier (TPZ) 2018


import logging
from dataclasses import dataclass

import numpy as np

from core import S2L_config
from core.QI_MTD.mtd import metadata
from core.image_file import S2L_ImageFile
from core.products.landsat_8.landsat8 import Landsat8Product
from core.products.product import S2L_Product
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


@dataclass
class SbafParams:
    """Simple sbaff param storage
    """
    coefficient: float
    offset: float


class S2L_Sbaf(S2L_Process):

    def initialize(self):
        self._sbaf_params = {}

    def get_sen2like_coef(self, mission):
        """
        Derived from value in HLS Guide v 1.4
        Get Adjustement coefficient for SEN2LIKE processing,
        Coefficient applied to Landsat8/OLI towards Sentinel2A/MSI data
        Coef array definition [slope, intercept]"""

        adj_coef = {}
        if mission in ('LANDSAT_8', 'LANDSAT_9'):
            adj_coef['B01'] = {'bandLabel': 'CA'}
            adj_coef['B02'] = {'bandLabel': 'BLUE'}
            adj_coef['B03'] = {'bandLabel': 'GREEN'}
            adj_coef['B04'] = {'bandLabel': 'RED'}
            adj_coef['B05'] = {'bandLabel': 'NIR 20'}
            adj_coef['B06'] = {'bandLabel': 'SWIR 1'}
            adj_coef['B07'] = {'bandLabel': 'SWIR 2'}

            # compute coeff from Nasa SBAF values
            adj_coef_l8_s2a = self.get_oli_like_coef("Sentinel-2A")
            for oli_band in adj_coef.keys():
                s2_band = Landsat8Product.get_s2like_band(oli_band)
                if not s2_band:
                    continue
                coef = adj_coef_l8_s2a[s2_band]['coef']
                a = 1 / coef[0]
                b = - coef[1] / coef[0]
                adj_coef[oli_band]['coef'] = [a, b]

        return adj_coef

    def get_oli_like_coef(self, mission):
        """S.Saunier 20/11/2018
        Value in HLS Guide v 1.4
        Get Adjustement coefficient for OLI LIKE processing,
        Coefficient applied to Sentinel 2 S30 data  and NOT to Landsat
        data
        Coef array definition [slope, intercept]"""

        adj_coef = dict()
        if mission == 'Sentinel-2A':
            adj_coef['B01'] = {'bandLabel': 'CA', 'coef': [0.9959, -0.0002]}
            adj_coef['B02'] = {'bandLabel': 'BLUE', 'coef': [0.9778, -0.004]}
            adj_coef['B03'] = {'bandLabel': 'GREEN', 'coef': [1.0053, -0.0009]}
            adj_coef['B04'] = {'bandLabel': 'RED', 'coef': [0.9765, 0.0009]}
            adj_coef['B8A'] = {'bandLabel': 'NIR 20', 'coef': [0.9983, -0.0001]}
            adj_coef['B11'] = {'bandLabel': 'SWIR 1', 'coef': [0.9987, -0.0011]}
            adj_coef['B12'] = {'bandLabel': 'SWIR 2', 'coef': [1.003, -0.0012]}

        elif mission == 'Sentinel-2B':
            adj_coef['B01'] = {'bandLabel': 'CA', 'coef': [0.9959, -0.0002]}
            adj_coef['B02'] = {'bandLabel': 'BLUE', 'coef': [0.9778, -0.004]}
            adj_coef['B03'] = {'bandLabel': 'GREEN', 'coef': [1.0075, -0.0008]}
            adj_coef['B04'] = {'bandLabel': 'RED', 'coef': [0.9761, 0.001]}
            adj_coef['B8A'] = {'bandLabel': 'NIR 20', 'coef': [0.9966, 0.000]}
            adj_coef['B11'] = {'bandLabel': 'SWIR 1', 'coef': [1.000, -0.0003]}
            adj_coef['B12'] = {'bandLabel': 'SWIR 2', 'coef': [0.9867, 0.0004]}

        return adj_coef

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        log.info('Start')

        # init to None
        offset = None
        slope = None

        if product.mtl.mission == "Sentinel-2A":
            # skip for S2A
            # set SBAF parameters for export in L2H/F_QUALITY.xml file
            self._sbaf_params[band] = SbafParams(1, 0)
            log.info('Skip for Sentinel-2A')
            log.info("End")
            return image

        elif product.mtl.mission == "Sentinel-2B":
            # skip for S2B as S2B is intercalibrated with S2B in Collection-1 (PB >= 4.00)
            # set SBAF parameters for export in L2H/F_QUALITY.xml file
            self._sbaf_params[band] = SbafParams(1, 0)
            log.info('Skip for Sentinel-2B, already intercalibrated')
            log.info("End")
            return image

        elif product.mtl.mission in ('LANDSAT_8', 'LANDSAT_9'):
            # L8 => S2A
            band_sbaf = band
            adj_coef = self.get_sen2like_coef("LANDSAT_8")
            if band_sbaf in adj_coef:
                log.info('Sbaf coefficient find to %s', band)
                slope, offset = adj_coef[band_sbaf]['coef']
                log.info('slop = %s, offset = %s', slope, offset)
            else:
                self._sbaf_params[band] = SbafParams(1, 0)
                log.info("No Sbaf coefficient defined for %s", band)
                return image

        self._sbaf_params[band] = SbafParams(slope, offset)

        # Apply SBAF
        if offset is not None and slope is not None:
            log.debug("Applying SBAF")
            new = image.array
            new = new * slope + offset
            # transfer no data
            new[image.array == 0] = 0

            # Format Output : duplicate, link  to product as parameter
            image = image.duplicate(self.output_file(product, band), array=new.astype(np.float32))
            if S2L_config.config.getboolean('generate_intermediate_products'):
                image.write(creation_options=['COMPRESS=LZW'])

        log.info('End')

        return image

    def postprocess(self, product: S2L_Product):
        """Set QI parameters

        Args:
            product (S2L_Product): product to post process
        """
        for band, params in self._sbaf_params.items():
            # set sbaf qi param with S2 band naming
            s2_band = product.__class__.get_s2like_band(band)
            if not s2_band:
                # avoid Non Sentinel native band
                continue
            metadata.qi[f'SBAF_COEFFICIENT_{s2_band}'] = params.coefficient
            metadata.qi[f'SBAF_OFFSET_{s2_band}'] = params.offset
