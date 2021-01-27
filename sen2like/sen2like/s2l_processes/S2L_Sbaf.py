#! /usr/bin/env python
# -*- coding: utf-8 -*-
# S. Saunier (TPZ) 2018


import logging

import numpy as np

from core.S2L_config import config
from core.QI_MTD.mtd import metadata
from core.products.landsat_8.landsat8 import Landsat8Product
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


class S2L_Sbaf(S2L_Process):
    def __init__(self):
        super().__init__()

    def getSen2likeCoef(self, mission):
        """
        Derived from value in HLS Guide v 1.4
        Get Adjustement coefficient for SEN2LIKE processing,
        Coefficient applied to Landsat8/OLI towards Sentinel2A/MSI data
        Coef array definition [slope, intercept]"""

        adj_coef = dict()
        if mission == 'LANDSAT_8':
            adj_coef['B01'] = {'bandLabel': 'CA'}
            adj_coef['B02'] = {'bandLabel': 'BLUE'}
            adj_coef['B03'] = {'bandLabel': 'GREEN'}
            adj_coef['B04'] = {'bandLabel': 'RED'}
            adj_coef['B05'] = {'bandLabel': 'NIR 20'}
            adj_coef['B06'] = {'bandLabel': 'SWIR 1'}
            adj_coef['B07'] = {'bandLabel': 'SWIR 2'}

            # compute coeff from Nasa SBAF values
            adj_coef_L8_S2A = self.getOLILikeCoef("Sentinel-2A")
            for oli_band in adj_coef.keys():
                s2_band = Landsat8Product.get_s2like_band(oli_band)
                if s2_band is None:
                    continue
                coef = adj_coef_L8_S2A[s2_band]['coef']
                a = 1 / coef[0]
                b = - coef[1] / coef[0]
                adj_coef[oli_band]['coef'] = [a, b]

        return adj_coef

    def getOLILikeCoef(self, mission):
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

    def process(self, product, image, band):
        log.info('Start')

        # init to None
        offset = None
        slope = None

        if product.mtl.mission == "Sentinel-2A":
            # skip for S2A
            metadata.qi['SBAF_COEFFICIENT_{}'.format(band)] = 1
            metadata.qi['SBAF_OFFSET_{}'.format(band)] = 0
            return image

        elif product.mtl.mission == "Sentinel-2B":
            # S2B => L8 + L8 => S2A
            adj_coef1 = self.getOLILikeCoef("Sentinel-2B")
            adj_coef2 = self.getSen2likeCoef("LANDSAT_8")
            band_sbaf1 = band
            band_sbaf2 = Landsat8Product.get_band_from_s2(band)
            if band_sbaf1 in adj_coef1 and band_sbaf2 in adj_coef2:
                slope1, offset1 = adj_coef1[band_sbaf1]['coef']
                slope2, offset2 = adj_coef2[band_sbaf2]['coef']
                # merging coefficients
                slope = slope2 * slope1
                offset = slope2 * offset1 + offset2
            else:
                log.error("No Sbaf coefficient defined for {}".format(band))

        elif product.mtl.mission == "LANDSAT_8":
            # L8 => S2A
            band_sbaf = band
            adj_coef = self.getSen2likeCoef("LANDSAT_8")
            if band_sbaf in adj_coef:
                slope, offset = adj_coef[band_sbaf]['coef']
            else:
                metadata.qi['SBAF_COEFFICIENT_{}'.format(band)] = 1
                metadata.qi['SBAF_OFFSET_{}'.format(band)] = 0
                log.error("No Sbaf coefficient defined for {}".format(band))
                return image

        metadata.qi['SBAF_COEFFICIENT_{}'.format(band)] = slope
        metadata.qi['SBAF_OFFSET_{}'.format(band)] = offset

        # Apply SBAF
        if offset is not None and slope is not None:
            log.debug("Applying SBAF")
            new = image.array
            new = new * slope + offset
            # transfer no data
            new[image.array == 0] = 0

            # Format Output : duplicate, link  to product as parameter
            image = image.duplicate(self.output_file(product, band), array=new.astype(np.float32))
            if config.getboolean('generate_intermediate_products'):
                image.write(creation_options=['COMPRESS=LZW'])

        log.info('End')

        return image
