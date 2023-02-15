# -*- coding: utf-8 -*-
# M. Arthaud (TPZ-F) 2021

import logging
import os
import subprocess
import shutil

import xml.etree.ElementTree as ET

from core import S2L_config
from grids.mgrs_framing import pixel_center

logger = logging.getLogger("Sen2Like")


class Sen2corClient:

    gipp_template = {
        'LANDSAT_8': 'L2A_GIPP_ROI_Landsat_template.xml',
        'LANDSAT_9': 'L2A_GIPP_ROI_Landsat_template.xml',
        'Sentinel-2A': 'L2A_GIPP_ROI_Landsat_template.xml',
        'Sentinel-2B': 'L2A_GIPP_ROI_Landsat_template.xml',
    }

    roi_ref_band = {
        'LANDSAT_8': 'B04',
        'LANDSAT_9': 'B04',
        'Sentinel-2A': None,
        'Sentinel-2B': None,
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
            if product.mtl.mission in self.gipp_template:
                gipp_path = self._write_gipp(product)
                cmd = [
                    'python', self.sen2cor_command,
                    product.path,
                    "--output_dir", sen2cor_output_dir,
                    "--GIP_L2A", gipp_path,
                    "--work_dir", sen2cor_output_dir,
                    "--sc_classic"
                ]
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
            raise Sen2corError("Sen2Cor error: Cannot get output product")

        return os.path.join(sen2cor_output_dir, generated_product[0])

    def _write_gipp(self, product):

        gipp_path = os.path.join(
            S2L_config.config.get('wd'), 'sen2cor',
            product.name, f'sen2cor_gipp_{self.out_mgrs}.xml')

        template_file = os.path.join(
            os.path.dirname(__file__), self.gipp_template[product.mtl.mission])

        logger.debug('GIPP template : %s', template_file)

        if product.sensor == 'S2':
            shutil.copyfile(template_file, gipp_path)
            logger.debug("For sentinel, sen2cor don't use ROI")
            return gipp_path

        ref_band = product.get_band_file(self.roi_ref_band[product.mtl.mission])
        y, x = pixel_center(ref_band, self.out_mgrs)
        logger.debug('Pixel center : (%s, %s)', y, x)

        with open(template_file, mode='r', encoding='utf-8') as template:
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
