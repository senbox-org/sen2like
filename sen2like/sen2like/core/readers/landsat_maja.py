import glob
import logging
import os
import re
import sys
from xml import parsers
from xml.etree import ElementTree

import numpy as np
from osgeo import ogr
import shapely
import shapely.geometry
import shapely.wkt

from core.metadata_extraction import compute_earth_solar_distance, get_in_band_solar_irrandiance_value, from_date_to_doy
from core.readers.reader import BaseReader

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


class LandsatMajaMTL(BaseReader):
    # Object for metadata extraction

    def __init__(self, product_path):
        super().__init__(product_path)

        # Check product path as input
        if not os.path.exists(self.product_path):
            log.error(' -- Input product does not exist')
            self.isValid = False
            return

        self.isValid = True
        self.tile_metadata = None

        self.thermal_band_list = []

        try:
            mtl_file_name = glob.glob(os.path.join(self.product_path, '*MTD*.xml'))[0]
        except IndexError:
            self.isValid = False
            sys.exit('No MTD product file information found')

        try:
            root = ElementTree.parse(mtl_file_name)
        except parsers.expat.ExpatError as err:
            self.isValid = False
            logging.error("Error during parsing of MTD product file: %s", mtl_file_name)
            logging.error(err)
            sys.exit(-1)

        self.mtl_file_name = mtl_file_name
        self.product_directory_name = os.path.basename(self.product_path)
        self.product_name = os.path.basename(os.path.dirname(mtl_file_name))  # PRODUCT_NAME # VDE : linux compatible

        self.landsat_scene_id = root.findtext('.//Dataset_Identification/IDENTIFIER')
        log.info(' -- Landsat_id : %s', self.landsat_scene_id)

        self.product_id = root.findtext('.//Product_Characteristics/PRODUCT_ID')
        self.file_date = root.findtext('.//Product_Characteristics/ACQUISITION_DATE')
        self.processing_sw = root.findtext('.//Product_Characteristics/PRODUCT_VERSION')
        self.sensor = root.findtext('.//Product_Characteristics/INSTRUMENT')
        self.mission = root.findtext('.//Product_Characteristics/PLATFORM')
        self.data_type = root.findtext('.//Product_Characteristics/PRODUCT_LEVEL')
        self.collection = root.findtext('.//Product_Characteristics/PRODUCT_ID')
        if self.collection == 'not found':
            self.collection = 'Pre Collection'

        self.spacecraft_id = root.findtext('.//Product_Characteristics/PLATFORM')
        self.mgrs = root.findtext('.//Dataset_Identification/GEOGRAPHICAL_ZONE')
        self.path = root.findtext('.//Product_Characteristics/ORBIT_NUMBER[@type="Path"]')

        self.relative_orbit = self.path
        self.absolute_orbit = 'N/A'

        observation_date = root.findtext('.//Product_Characteristics/ACQUISITION_DATE')
        self.observation_date = observation_date.split('T')[0]
        self.scene_center_time = observation_date.split('T')[-1]

        masks_nodes = root.findall('.//Mask_List/Mask')
        for mask_node in masks_nodes:
            if mask_node.findtext('.//Mask_Properties/NATURE') == 'Cloud':
                self.cloud_mask = mask_node.findtext('.//Mask_File_List/MASK_FILE')
            elif mask_node.findtext('.//Mask_Properties/NATURE') == 'Edge':
                self.edge_mask = mask_node.findtext('.//Mask_File_List/MASK_FILE')
            elif mask_node.findtext('.//Mask_Properties/NATURE') == 'Saturation':
                self.saturation_mask = mask_node.findtext('.//Mask_File_List/MASK_FILE')

        # Read angles
        self.cloud_cover = root.findtext('.//QUALITY_INDEX[@name="CloudPercent"]')
        self.sun_azimuth_angle = root.findtext('.//Sun_Angles/AZIMUTH_ANGLE')
        self.sun_zenith_angle = root.findtext('.//Sun_Angles/ZENITH_ANGLE')

        utm_zone = root.findtext('.//Horizontal_Coordinate_System/HORIZONTAL_CS_NAME')
        match = utm_zone_regexp.match(utm_zone)
        if match:
            self.datum = match.group(1)
            self.map_projection = match.group(2)
            self.utm_zone = match.group(3)
        else:
            log.warning('Cannot read Geographical zone : %s', utm_zone)
            self.datum = self.utm_zone = self.map_projection = None

        bands_files = []
        image_list_node = root.findall('.//Image_List/Image')
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
        spectral_nodes = root.findall('.//Spectral_Band_Informations')
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
        scene_boundary_lat = [float(point.findtext('LAT')) for point in
                              root.findall('.//Global_Geopositioning/Point') if point.attrib['name'] != 'center']
        scene_boundary_lon = [float(point.findtext('LON')) for point in
                              root.findall('.//Global_Geopositioning/Point') if point.attrib['name'] != 'center']
        arr1 = np.asarray(scene_boundary_lat, np.float)
        arr1_r = np.roll(arr1, -1)
        # Retour d index
        arr2 = np.asarray(scene_boundary_lon, np.float)
        arr2_r = np.roll(arr2, -1)
        x = arr1_r - arr1  # Vecteur X - latitude
        y = arr2_r - arr2  # Vecteur Y - longitude
        # Remove point with diff null in the two direction
        index = (np.argwhere((x == 0) & (y == 0))).flatten()
        x = np.delete(x, index)
        y = np.delete(y, index)
        x_r = np.roll(x, -1)
        y_r = np.roll(y, -1)
        scalar = np.multiply(x, x_r) + np.multiply(y, y_r)  # Scalar product
        # Norm
        norm = np.power(np.multiply(x, x) + np.multiply(y, y), 0.5)
        norm_r = np.roll(norm, -1)
        # Product of Norm || U || * || V ||

        theta = np.roll(
            np.arccos(np.divide(scalar, np.multiply(norm, norm_r))) * (np.divide(180, np.pi)),
            1)
        arr1 = np.delete(arr1, index)
        arr2 = np.delete(arr2, index)
        self.scene_boundary_lat = arr1[theta > 60.0].tolist()
        self.scene_boundary_lon = arr2[theta > 60.0].tolist()
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
