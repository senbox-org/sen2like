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
import subprocess
import xml.etree.ElementTree as ET

from core import S2L_config
from grids.mgrs_framing import pixel_center

logger = logging.getLogger("Sen2Like")


class Sen2corClient:

    gipp_template_file = os.path.join(
        os.path.dirname(__file__),
        'L2A_GIPP_ROI_Landsat_template.xml'
    )

    roi_ref_band = {
        'LANDSAT_8': 'B04',
        'LANDSAT_9': 'B04',
    }

    mission_specific_cmd_params = {
        "Prisma" : ["--Hyper_MS",  "--resolution", "30"]
    }

    def __init__(self, sen2cor_command, out_mgrs):
        """
        :params sen2cor_command: main sen2cor python script
        :params out_mgrs: out mgrs tile code, sen2cor will only compute value on this tile
        :params wd: work directory
        """
        self.sen2cor_command = sen2cor_command
        self.out_mgrs = out_mgrs

    def run(self, product):
        """
        :param product: product archive InputProduct
        :params product_roi: bbox in MULTIPOLYGON wkt string, input product bbox
        """
        logger.debug("<<< RUNNING SEN2CORE... >>>")
        sen2cor_output_dir = os.path.join(
            S2L_config.config.get('wd'),
            'sen2cor',
            os.path.basename(product.path))

        if not os.path.exists(sen2cor_output_dir):
            os.makedirs(sen2cor_output_dir)

        try:
            gipp_path = self._write_gipp(product)
            cmd = [
                'python', self.sen2cor_command,
                product.path,
                "--output_dir", sen2cor_output_dir,
                "--GIP_L2A", gipp_path,
                "--work_dir", sen2cor_output_dir,
                "--sc_classic"
            ]

            additional_params = self.mission_specific_cmd_params.get(product.mtl.mission, None)
            if additional_params:
                cmd.extend(additional_params)

            logger.info(' '.join(cmd))
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as run_error:
            logger.error("An error occurred during the run of sen2cor")
            logger.error(run_error)
            raise Sen2corError(run_error) from run_error

        # Read output product
        generated_product = next(os.walk(sen2cor_output_dir))[1]

        if len(generated_product) != 1:
            logger.error("Sen2Cor error: Cannot get output product")
            raise Sen2corError(f"Sen2Cor error: Cannot get output product from {sen2cor_output_dir}")

        return os.path.join(sen2cor_output_dir, generated_product[0])

    def _write_gipp(self, product):

        gipp_path = os.path.join(
            S2L_config.config.get('wd'), 'sen2cor',
            product.name, f'sen2cor_gipp_{self.out_mgrs}.xml')

        logger.debug('GIPP template : %s', self.gipp_template_file)

        # ref_band = None is considered as S2 product format (S2A, S2B, S2P prisma)
        ref_band = self.roi_ref_band.get(product.mtl.mission, None)

        if ref_band is None:
            shutil.copyfile(self.gipp_template_file, gipp_path)
            logger.debug("For sentinel, sen2cor don't use ROI")
            return gipp_path

        y, x = pixel_center(ref_band, self.out_mgrs)
        logger.debug('Pixel center : (%s, %s)', y, x)

        with open(self.gipp_template_file, mode='r', encoding='utf-8') as template:
            tree = ET.parse(template)

        root = tree.getroot()
        row0 = root.find('Common_Section/Region_Of_Interest/row0')
        row0.text = str(y)
        col0 = root.find('Common_Section/Region_Of_Interest/col0')
        col0.text = str(x)

        out_string = ET.tostring(root)

        with open(gipp_path, mode='wb') as gipp:
            gipp.write(out_string)

        logger.info('GIPP L2A : %s', gipp_path)
        return gipp_path


class Sen2corError(Exception):
    pass
