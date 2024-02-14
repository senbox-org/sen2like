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
import os
import shutil

from core.products.product import S2L_Product
from s2l_processes.S2L_Product_Packager import PackagerConfig, S2L_Product_Packager

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

    def __init__(self, generate_intermediate_products: bool):
        super().__init__(generate_intermediate_products, packager_config)

    def postprocess_quicklooks(self, qi_data_dir, product: S2L_Product):
        """
        Creates all QL as done by `2L_Product_Packager.postprocess_quicklooks` plus Fusion Mask QL if needed
        Args:
            qi_data_dir (str): path to quicklook output dir
            product (S2L_Product): product

        Returns:

        """
        super().postprocess_quicklooks(qi_data_dir, product)
        # Copy fusion auto check threshold mask
        if product.fusion_auto_check_threshold_msk_file is not None:
            outfile = "_".join([product.metadata.mtd.get(self.mtd_band_root_name_field), 'FCM']) + '.TIF'
            fpath = os.path.join(qi_data_dir, outfile)
            shutil.copyfile(product.fusion_auto_check_threshold_msk_file, fpath)
            product.metadata.mtd.get(self.mtd_quicklook_field).append(fpath)

    def guard(self, product:S2L_Product):
        """ Define required condition to algorithm execution
        """
        if not product.fusionable:
            log.info("Fusion has not been performed. So s2l does not write L2F product.")
            return False
        return True
