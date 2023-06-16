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

"""Base module for Maja product"""
import glob
import logging
import os
import sys
from xml import parsers
from xml.etree import ElementTree

from core.readers.reader import BaseReader, compute_scene_boundaries

log = logging.getLogger('Sen2Like')


class MajaReader(BaseReader):
    """Base reader for MAJA product"""

    def __init__(self, product_path):
        super().__init__(product_path)

        # Check product path as input
        if not os.path.exists(self.product_path):
            log.error('Input product does not exist')
            self.isValid = False
            return

        self.isValid = True

        try:
            mtl_file_name = glob.glob(os.path.join(self.product_path, '*MTD*.xml'))[0]
        except IndexError:
            self.isValid = False
            sys.exit('No MTD product file information found')

        try:
            self.root = ElementTree.parse(mtl_file_name)
        except parsers.expat.ExpatError as err:
            self.isValid = False
            logging.error("Error during parsing of MTD product file: %s", mtl_file_name)
            logging.error(err)
            sys.exit(-1)

        self.mtl_file_name = mtl_file_name
        self.mission = self.root.findtext('.//Product_Characteristics/PLATFORM')
        self.data_type = self.root.findtext('.//Product_Characteristics/PRODUCT_LEVEL')
        self.processing_sw = self.root.findtext('.//Product_Characteristics/PRODUCT_VERSION')

    def compute_boundary(self):
         # Compute scene boundary - EXT_POS_LIST tag
        scene_boundary_lat = [float(point.findtext('LAT')) for point in
                              self.root.findall('.//Global_Geopositioning/Point') if point.attrib['name'] != 'center']
        scene_boundary_lon = [float(point.findtext('LON')) for point in
                              self.root.findall('.//Global_Geopositioning/Point') if point.attrib['name'] != 'center']

        boundaries = compute_scene_boundaries(scene_boundary_lat, scene_boundary_lon)
        self.scene_boundary_lat = boundaries[0]
        self.scene_boundary_lon = boundaries[1]
        # End of scene boundary