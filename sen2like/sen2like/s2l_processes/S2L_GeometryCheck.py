"""Geometry verification module"""
import logging
import os

import numpy as np
from scipy.stats import skew, kurtosis

from core import S2L_config
from core.QI_MTD.mtd import metadata
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from klt import klt
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")

class S2L_GeometryCheck(S2L_Process):
    """Class to verify product geometry

    Args:
        S2L_Process (_type_): _description_
    """

    def initialize(self):
        self._tmp_stats = {}
        self._klt_results = []
        self._klt_matcher = klt.KLTMatcher()

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        log.info('Start')

        # do Geometry Assessment only if required
        assess_geometry_bands = S2L_config.config.get('doAssessGeometry', default='').split(',')
        if product.sensor != 'S2':
            assess_geometry_bands = [product.reverse_bands_mapping.get(band) for band in assess_geometry_bands]

        if assess_geometry_bands and band in assess_geometry_bands:
            # open validity mask
            mask = S2L_ImageFile(product.mask_filename)

            work_dir = os.path.join(S2L_config.config.get('wd'), product.name)

            log.info("Geometry assessment for band %s", band)

            ref_image = klt.get_ref_image(image)
            if ref_image is None:
                log.warning("Abort geometry assessment, no reference image found for %s", image.filepath)
                # abort, cannot do matching without ref image
                return image

            # Coarse resolution of correlation grid (only for stats)
            self._matching(ref_image, image, mask, work_dir)

            # Append bands name to keys
            if S2L_config.config.get('reference_band') != band:
                for key in self._tmp_stats:
                    self._tmp_stats[f'{key}_{band}'] = self._tmp_stats.pop(key)

            # set qi info to reference band stats
            metadata.qi.update(self._tmp_stats)

            # clear for next band process
            self._tmp_stats = {}

        log.info('End')

        return image

    def _matching(self, image_ref: S2L_ImageFile, image: S2L_ImageFile, mask: S2L_ImageFile, working_dir: str) -> klt.KTLResult:

        log.info('Start matching')

        # do matching with KLT
        result = self._klt_matcher.do_matching(working_dir, image_ref, image, mask.array)

        dx = result.dx_array
        dy = result.dy_array

        dist = np.sqrt(np.power(dx, 2) + np.power(dy, 2)).flatten()
        self._tmp_stats.update({'SKEW': np.round(skew(dist, axis=None), 1),
                                'KURTOSIS': np.round(kurtosis(dist, axis=None), 1),
                                'REF_IMAGE': os.path.basename(S2L_config.config.get('refImage')),
                                'MEAN': np.round(np.mean(dist), 1),
                                'MEAN_X': dx.mean(),
                                'MEAN_Y': dy.mean(),
                                'STD': np.round(np.std(dist), 1),
                                'STD_X': np.round(np.std(dx), 1),
                                'STD_Y': np.round(np.std(dy), 1),
                                'RMSE': np.round(np.sqrt(np.mean(np.power(dist, 2))), 1),
                                'NB_OF_POINTS': result.nb_matching_point})

        return result