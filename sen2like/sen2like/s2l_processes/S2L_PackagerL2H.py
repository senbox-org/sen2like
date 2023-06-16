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

from s2l_processes.S2L_Product_Packager import PackagerConfig, S2L_Product_Packager

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
