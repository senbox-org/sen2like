#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2020

import logging
import os
import shutil

from core import S2L_config
from core.QI_MTD.mtd import metadata
from s2l_processes.S2L_Product_Packager import S2L_Product_Packager, PackagerConfig

log = logging.getLogger("Sen2Like")

packager_config = PackagerConfig(
    product_type_name='L2F',
    mtd_mask_field='masks_F',
    mtd_product_name_field='product_F_name',
    mtd_granule_name_field='granule_F_name',
    mtd_band_root_name_field='band_rootName_F',
    mtd_band_path_field='bands_path_F',
    mtd_quicklook_field='quicklooks_F',
    mtd_bb_qi_path_field='bb_QIF_path',
    mtd_qi_report_file_name_field='L2F_QUALITY.xml',
    product_suffix='F',
    mtd_product_qi_xsd_field='product_QIF_xsd',
    tile_mtd_file_path='MTD_TL_L2F.xml'
)


class S2L_PackagerL2F(S2L_Product_Packager):
    """
    S2F product packager
    """

    def __init__(self):
        super().__init__(packager_config)

    def postprocess_quicklooks(self, qi_data_dir, product):
        """
        Creates all QL as done by `2L_Product_Packager.postprocess_quicklooks` plus Fusion Mask QL if needed
        Args:
            qi_data_dir (str): path to quicklook output dir
            product (): product

        Returns:

        """
        super().postprocess_quicklooks(qi_data_dir, product)
        # Copy fusion auto check threshold mask
        if product.fusion_auto_check_threshold_msk_file is not None:
            outfile = "_".join([metadata.mtd.get(self.mtd_band_root_name_field), 'FCM']) + '.TIF'
            fpath = os.path.join(qi_data_dir, outfile)
            shutil.copyfile(product.fusion_auto_check_threshold_msk_file, fpath)
            metadata.mtd.get(self.mtd_quicklook_field).append(fpath)

    def guard(self):
        """ Define required condition to algorithm execution
        """
        if S2L_config.config.getboolean('none_S2_product_for_fusion'):
            log.info("Fusion has not been performed. So s2l does not write L2F product.")
            return False
        return True
