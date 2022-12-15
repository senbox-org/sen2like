#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2020

import logging

from s2l_processes.S2L_Product_Packager import S2L_Product_Packager, PackagerConfig

log = logging.getLogger("Sen2Like")

packager_config = PackagerConfig(
    product_type_name='L2H',
    mtd_mask_field='masks_H',
    mtd_product_name_field='product_H_name',
    mtd_granule_name_field='granule_H_name',
    mtd_band_root_name_field='band_rootName_H',
    mtd_band_path_field='bands_path_H',
    mtd_quicklook_field='quicklooks_H',
    mtd_bb_qi_path_field='bb_QIH_path',
    mtd_qi_report_file_name_field='L2H_QUALITY.xml',
    product_suffix='H',
    mtd_product_qi_xsd_field='product_QIH_xsd',
    tile_mtd_file_path='MTD_TL_L2H.xml'
)


class S2L_PackagerL2H(S2L_Product_Packager):
    """
    S2H product packager
    """

    def __init__(self):
        super().__init__(packager_config)
