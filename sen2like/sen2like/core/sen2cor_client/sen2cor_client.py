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

import affine
import logging
import os
import subprocess
import lxml.etree as ET

from osgeo import osr
import mgrs

from core import S2L_config
from core.image_file import S2L_ImageFile


logger = logging.getLogger("Sen2Like")


def get_mgrs_center(tilecode: str, utm=False) -> tuple:
    """Get MGRS tile center coordinates in native tile UTM or WGS84

    Args:
        tilecode (str): tile to get center coords
        utm (bool, optional): Flag for output SRS . Defaults to False.

    Returns:
        tuple: (lat,long) coords if utm=False, else (utm, N/S, easting, northing)
    """
    if tilecode.startswith('T'):
        tilecode = tilecode[1:]
    centercode = tilecode + '5490045100'
    m = mgrs.MGRS()
    if utm:
        return m.MGRSToUTM(centercode)
    return m.toLatLon(centercode)


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

    def __init__(self, sen2cor_command, out_mgrs, enable_topo_corr=False):
        """
        :params sen2cor_command: main sen2cor python script
        :params out_mgrs: out mgrs tile code, sen2cor will only compute value on this tile
        :params enable_topo_corr: activate or not topographic correction
        """
        self.sen2cor_command = sen2cor_command
        self.out_mgrs = out_mgrs
        self.enable_topo_corr = enable_topo_corr

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

        with open(self.gipp_template_file, mode='r', encoding='utf-8') as template:
            tree = ET.parse(template)#, parser = _CommentedTreeBuilder())

        # configure topo correction
        root = tree.getroot()
        dem_correction_node = root.find('Atmospheric_Correction/Flags/DEM_Terrain_Correction')
        dem_correction_node.text = "TRUE" if self.enable_topo_corr else "FALSE"

        # ref_band = None is considered as S2 product format (S2A, S2B, S2P prisma)
        ref_band = self.roi_ref_band.get(product.mtl.mission, None)

        if ref_band:
            # Compute ROI center for landsat and fill template with result
            ref_band_file = product.get_band_file(ref_band)

            y, x = self._pixel_center(ref_band_file)

            logger.debug('Pixel center : (%s, %s)', y, x)

            row0 = root.find('Common_Section/Region_Of_Interest/row0')
            row0.text = str(y)
            col0 = root.find('Common_Section/Region_Of_Interest/col0')
            col0.text = str(x)

            ET.ElementTree(root).write(gipp_path, encoding='utf-8', xml_declaration=True)

        else:
            logger.debug("For sentinel, sen2cor don't use ROI")

        logger.info('GIPP L2A : %s', gipp_path)

        ET.ElementTree(root).write(gipp_path, encoding='utf-8', xml_declaration=True)

        return gipp_path

    def _pixel_center(self, image: S2L_ImageFile):
        """Get mgrs tile center coordinates from tile code in image coordinates

        Args:
            image (S2L_ImageFile): image to get srs from

        Returns:
            tuple: (y,x) image coordinates
        """

        lat, lon = get_mgrs_center(self.out_mgrs) # pylint: disable=W0632

        # Transform src SRS
        wgs84_srs = osr.SpatialReference()
        wgs84_srs.ImportFromEPSG(4326)

        # Transform dst SRS
        image_srs = osr.SpatialReference(wkt=image.projection)

        # convert MGRS center coordinates from lat lon to image EPSG coordinates (UTM)
        transformation = osr.CoordinateTransformation(wgs84_srs, image_srs)
        easting, northing, _ = transformation.TransformPoint(lat, lon)

        # northing = y = latitude, easting = x = longitude
        tr = affine.Affine(
            image.yRes, 0, image.yMax,
            0, image.xRes, image.xMin
        )

        # compute y,x in image coordinates
        y, x = (northing, easting) * (~ tr)
        return int(y), int(x)


class Sen2corError(Exception):
    pass
