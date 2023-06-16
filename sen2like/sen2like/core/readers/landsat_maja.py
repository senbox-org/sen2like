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

"""Module for Landsat Maja product"""
import logging
import os
import re

import shapely
import shapely.geometry
import shapely.wkt
from osgeo import ogr

from core.metadata_extraction import (
    compute_earth_solar_distance,
    from_date_to_doy,
    get_in_band_solar_irrandiance_value,
)
from core.readers.maja_reader import MajaReader

log = logging.getLogger('Sen2Like')

band_regex = re.compile(r'[B,d]\d{1,2}')
utm_zone_regexp = re.compile(r'(.*) / (\w+) zone (\d+).?')


def get_wrs_from_lat_lon(lat, lon):
    shapefile = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'l8_descending', 'WRS2_descending.shp')
    wrs = ogr.Open(shapefile)
    layer = wrs.GetLayer(0)
    point = shapely.geometry.Point(lon, lat)
    mode = 'D'

    i = 0
    while not checkpoint(layer.GetFeature(i), point, mode):
        i += 1
    feature = layer.GetFeature(i)
    path = feature['PATH']
    row = feature['ROW']
    return path, row


def checkpoint(feature, point, mode):
    geom = feature.GetGeometryRef()  # Get geometry from feature
    shape = shapely.wkt.loads(geom.ExportToWkt())  # Import geometry into shapely to easily work with our point
    return point.within(shape) and feature['MODE'] == mode


class LandsatMajaMTL(MajaReader):
    # Object for metadata extraction

    def __init__(self, product_path):
        super().__init__(product_path)

        if not self.isValid:
            return

        self.tile_metadata = None
        self.thermal_band_list = []

        self.product_directory_name = os.path.basename(self.product_path)
        self.product_name = os.path.basename(os.path.dirname(self.mtl_file_name))  # PRODUCT_NAME # VDE : linux compatible

        self.landsat_scene_id = self.root.findtext('.//Dataset_Identification/IDENTIFIER')
        log.info(' -- Landsat_id : %s', self.landsat_scene_id)

        self.product_id = self.root.findtext('.//Product_Characteristics/PRODUCT_ID')
        self.file_date = self.root.findtext('.//Product_Characteristics/ACQUISITION_DATE')
        self.sensor = self.root.findtext('.//Product_Characteristics/INSTRUMENT')
        self.collection = self.root.findtext('.//Product_Characteristics/PRODUCT_ID')
        if self.collection == 'not found':
            self.collection = 'Pre Collection'

        self.spacecraft_id = self.root.findtext('.//Product_Characteristics/PLATFORM')
        self.mgrs = self.root.findtext('.//Dataset_Identification/GEOGRAPHICAL_ZONE')
        self.path = self.root.findtext('.//Product_Characteristics/ORBIT_NUMBER[@type="Path"]')

        self.relative_orbit = self.path
        # hardcoded as we can't have it
        self.absolute_orbit = '000000'

        observation_date = self.root.findtext('.//Product_Characteristics/ACQUISITION_DATE')
        self.observation_date = observation_date.split('T')[0]
        self.scene_center_time = observation_date.split('T')[-1]

        masks_nodes = self.root.findall('.//Mask_List/Mask')
        nature_mask_path = './/Mask_Properties/NATURE'
        mask_file_path = './/Mask_File_List/MASK_FILE'
        for mask_node in masks_nodes:
            if mask_node.findtext(nature_mask_path) == 'Cloud':
                self.cloud_mask = mask_node.findtext(mask_file_path)
            elif mask_node.findtext(nature_mask_path) == 'Edge':
                self.edge_mask = mask_node.findtext(mask_file_path)
            elif mask_node.findtext(nature_mask_path) == 'Saturation':
                self.saturation_mask = mask_node.findtext(mask_file_path)

        # Read angles
        self.cloud_cover = self.root.findtext('.//QUALITY_INDEX[@name="CloudPercent"]')
        self.sun_azimuth_angle = self.root.findtext('.//Sun_Angles/AZIMUTH_ANGLE')
        self.sun_zenith_angle = self.root.findtext('.//Sun_Angles/ZENITH_ANGLE')

        utm_zone = self.root.findtext('.//Horizontal_Coordinate_System/HORIZONTAL_CS_NAME')
        match = utm_zone_regexp.match(utm_zone)
        if match:
            self.datum = match.group(1)
            self.map_projection = match.group(2)
            self.utm_zone = match.group(3)
        else:
            log.warning('Cannot read Geographical zone : %s', utm_zone)
            self.datum = self.utm_zone = self.map_projection = None

        bands_files = []
        image_list_node = self.root.findall('.//Image_List/Image')
        for image_node in image_list_node:
            nature = image_node.findtext('.//Image_Properties/NATURE')
            if nature == 'Surface_Reflectance':
                bands_files = image_node.findall('.//Image_File_List/IMAGE_FILE')
            elif nature == 'Aerosol_Optical_Thickness':
                self.aerosol_band = os.path.join(self.product_path,
                                                 image_node.findtext('.//Image_File_List/IMAGE_FILE'))
                log.info(' -- Aerosol image found ')

        self.reflective_band_list = []
        self.band_sequence = []
        for image in bands_files:
            self.band_sequence.append(image.attrib['band_id'])
            self.reflective_band_list.append(os.path.join(self.product_path, image.text))

        self.rad_radio_coefficient_dic = {}
        self.radio_coefficient_dic = {}
        spectral_nodes = self.root.findall('.//Spectral_Band_Informations')
        for cpt, spectral_node in enumerate(spectral_nodes):
            band_id = spectral_node.attrib['band_id']
            gain = spectral_node.findtext('.//COEFFICIENT[@name="RadianceMult"]')
            offset = spectral_node.findtext('.//COEFFICIENT[@name="RadianceAdd"]')
            self.rad_radio_coefficient_dic[str(cpt)] = {"Band_id": band_id,
                                                    "Gain": gain, "Offset": offset}
            gain = spectral_node.findtext('.//COEFFICIENT[@name="ReflectanceeMult"]')
            offset = spectral_node.findtext('.//COEFFICIENT[@name="ReflectanceAdd"]')
            self.radio_coefficient_dic[str(cpt)] = {"Band_id": band_id,
                                                        "Gain": gain, "Offset": offset}

        obs = self.observation_date.split('T')[0].split('-')
        input_date = obs[2] + '-' + obs[1] + '-' + obs[0]
        self.doy = int(from_date_to_doy(input_date))
        self.dE_S = compute_earth_solar_distance(self.doy)
        self.sun_earth_distance = compute_earth_solar_distance(self.doy)
        self.solar_irradiance = get_in_band_solar_irrandiance_value(self.mission, self.sensor)

        # Compute scene boundary - EXT_POS_LIST tag
        self.compute_boundary()
        # End of scene boundary

        lon, lat = self.get_scene_center_coordinates()
        self.path, self.row = get_wrs_from_lat_lon(lat, lon)
        if self.data_type == 'L2A':
            self.l2a_qi_report_path = os.path.join(product_path, 'L2A_QUALITY.xml')
            if not os.path.isfile(self.l2a_qi_report_path):
                self.l2a_qi_report_path = None

    @staticmethod
    def can_read(product_name):
        return os.path.basename(product_name).startswith('LANDSAT8') or \
               os.path.basename(product_name).startswith('LANDSAT9')
