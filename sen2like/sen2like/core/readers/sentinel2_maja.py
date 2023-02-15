"""Module for Sentinel 2 Maja product""" 
import logging
import os
import sys
import xml.etree.ElementTree as ElementTree
from xml import parsers as pars

import numpy as np
from osgeo import osr
from osgeo import gdal
import mgrs

from atmcor.get_s2_angles import reduce_angle_matrix, get_angles_band_index
from core.metadata_extraction import from_date_to_doy
from core.readers.maja_reader import MajaReader

log = logging.getLogger('Sen2Like')

def from_values_list_to_array(selected_node):
    col_step = selected_node.findtext('COL_STEP')
    row_step = selected_node.findtext('ROW_STEP')

    values_list = selected_node.find('.//Values_List').findall('.//VALUES')

    # x_size, y_size , size of the matrix
    x_size = len(values_list[0].text.split())
    y_size = len(values_list)

    # Create np array of size (x_size, y_size) for values :
    arr = np.empty([x_size, y_size], float)
    for j in range(y_size):
        a = np.asarray(values_list[j].text.split(), float)
        arr[j] = a

    return x_size, y_size, col_step, row_step, arr


class Sentinel2MajaMTL(MajaReader):
    resolutions = {10: 'R1', 20: 'R2'}
    classif_band = {10: 'B4', 20: 'B5'}

    # Object for metadata extraction

    def __init__(self, product_path):
        super().__init__(product_path)

        if not self.isValid:
            return

        self.mgrs = os.path.basename(self.product_path).split('_')[3][-5:]

        self.aerosol_band = None
        self.aerosol_value = None

        self.dt_sensing_start = self.root.findtext('Product_Characteristics/ACQUISITION_DATE')
        self.ds_sensing_start = self.root.findtext('Product_Characteristics/ACQUISITION_DATE')

        # Read XML Metadata
        try:
            # mini dom
            self.product_name = self.root.findtext('Product_Characteristics/PRODUCT_ID')
            self.file_date = self.root.findtext('Product_Characteristics/PRODUCTION_DATE')
            self.sensor = 'MSI'
            self.absolute_orbit = self.root.findtext('Product_Characteristics/ORBIT_NUMBER')

            image_list_node = self.root.findall('.//Image_List/Image')

            self.bands = {}

            for image_node in image_list_node:
                nature = image_node.findtext('Image_Properties/NATURE')
                if nature == 'Surface_Reflectance':
                    bands_files = image_node.findall('.//Image_File_List/IMAGE_FILE')
                    for band_file in bands_files:
                        band_id = band_file.text.split('_')[-1].split('.')[0]
                        file_path = os.path.join(self.product_path, band_file.text)
                        log.debug('%s %s', band_id, file_path)
                        self.bands[band_id] = file_path

            # Collection not applicable for Landsat
            # self.collection = ' '
            self.radio_coefficient_dic = {}

            # RESCALING GAIN And OFFSET :
            self.quantification_value = self.root.findtext('.//Radiometric_Informations/REFLECTANCE_QUANTIFICATION_VALUE')

            solar_nodes = self.root.findall('.//Spectral_Band_Informations_List/Spectral_Band_Informations')
            self.band_sequence = []
            for solar_band_node in solar_nodes:
                band_id = solar_band_node.attrib['band_id']
                self.band_sequence.append(band_id)
                solar_irradiance = solar_band_node.findtext('.//SOLAR_IRRADIANCE')
                self.radio_coefficient_dic[band_id] = {"Band_id": band_id,
                                                        "Gain": 0.00001, "Offset": 0.0,
                                                        "Solar_irradiance": solar_irradiance
                                                        }

            # self.band_sequence = [int(rec) + 1 for rec in self.band_sequence]
            # self.rescaling_gain = [0.00001] * len(self.band_sequence)
            # self.rescaling_offset = [0] * len(self.band_sequence)

            tab = [self.radio_coefficient_dic[x]["Solar_irradiance"] for x in self.radio_coefficient_dic]
            self.solar_irradiance = [np.double(rec) for rec in tab]
            self.cloud_cover = self.root.findtext('.//Global_Index_List/QUALITY_INDEX[@name="CloudPercent"]')

            # Compute scene boundary - EXT_POS_LIST tag
            self.compute_boundary()
            # End of scene boundary

        except IndexError:
            # if not md_list:
            file_path = None
            log.error(' -- Warning - no MTL file found')
            log.error(' -- Procedure aborted')
            self.mtl_file_name = ''

        # Observation date

        # Only one metadata file for Maja product
        self.tile_metadata = self.mtl_file_name

        try:
            self.doy = 0
            self.sun_zenith_angle = self.root.findtext('.//Geometric_Informations/Mean_Value_List/Sun_Angles/ZENITH_ANGLE')
            self.sun_azimuth_angle = self.root.findtext('.//Geometric_Informations/Mean_Value_List/Sun_Angles/AZIMUTH_ANGLE')

            self.viewing_azimuth_angle = {}
            self.viewing_zenith_angle = {}
            incidence_angle_nodes = self.root.find('.//Mean_Viewing_Incidence_Angle_List')
            for cpt, incidence_angle_node in enumerate(incidence_angle_nodes):
                band_id = incidence_angle_node.attrib['band_id']
                self.viewing_azimuth_angle[str(cpt)] = {"Band_id": band_id,
                                                        "VAA": incidence_angle_node.findtext('AZIMUTH_ANGLE'),
                                                        }
                self.viewing_zenith_angle[str(cpt)] = {"Band_id": band_id,
                                                       "VZA": incidence_angle_node.findtext('ZENITH_ANGLE'),
                                                       }

            # TO USE </Viewing_Incidence_Angles_Grids> to set the angle files
            # self.angles_file = None

            geoposition_node = self.root.find('Geoposition_Informations/Coordinate_Reference_System')
            self.utm = geoposition_node.findtext('HORIZONTAL_CS_NAME')

            # 2017 - 12 - 07T09:13:39.027 Z
            d = self.dt_sensing_start
            obs = d.split('T')[0]
            rr = obs.split('-')  # 2007-12-08
            input_date = rr[2] + '-' + rr[1] + '-' + rr[0]
            self.doy = from_date_to_doy(input_date)
            self.scene_center_time = d.split('T')[1]
            self.observation_date = obs

            self.epsg = geoposition_node.findtext('HORIZONTAL_CS_CODE')

            mask_nodes = self.root.findall('.//Mask_List/Mask')
            self.cloud_mask = []
            self.nodata_mask = {}
            self.detfoo_mask = {}
            mask_path = './/Mask_File_List/MASK_FILE'
            for mask_node in mask_nodes:
                mask_nature = mask_node.findtext('.//NATURE')
                if mask_nature == 'Cloud':
                    self.cloud_mask = {mask.attrib['group_id']: mask.text for mask in mask_node.findall(mask_path)}
                if mask_nature == 'Edge':
                    self.edge_mask = {mask.attrib['group_id']: mask.text for mask in mask_node.findall(mask_path)}
                if mask_nature == 'Saturation':
                    self.saturation_mask = {mask.attrib['band_id']: mask.text for mask in mask_node.findall(mask_path)}
                elif mask_nature == 'Defective_Pixel':
                    self.nodata_mask = {mask.attrib['band_id']: mask.text for mask in mask_node.findall(mask_path)}
        except IndexError:
            sys.exit(' TILE MTL Parsing Issue ')

        # Absolute orbit is contained in the granule ID as _A00000_
        # absolute_orbit = re.compile(r'A\d{6}_').search(self.granule_id)
        self.relative_orbit = '000000'  # FIXME: no relative orbit ?

        # L2A QI report file
        if self.data_type == "Level-2A":
            self.l2a_qi_report_path = os.path.join(
                product_path, 'GRANULE', self.granule_id, 'QI_DATA', 'L2A_QUALITY.xml')
            if not os.path.isfile(self.l2a_qi_report_path):
                self.l2a_qi_report_path = None

    @staticmethod
    def can_read(product_name):
        name = os.path.basename(product_name)
        return name.startswith('SENTINEL2')

    def extract_viewing_angle(self, dst_file, angle_type):
        # Access to MTL and extract vieing angles depending on the angletype
        # Return the list of files that have been generated, out_list
        out_list = []  # Store the path of all outputs
        log.debug('Extract viewing angle')
        try:
            root = ElementTree.parse(self.mtl_file_name)
        except pars.expat.ExpatError:
            sys.exit('Invalid XML metadata file.')

        # gdal parameter :
        NoData_value = -9999

        # Load xmlf file and retrieve projection parameter :
        epsg_code = root.findtext('.//Horizontal_Coordinate_System/HORIZONTAL_CS_CODE')
        ulx = root.findtext('.//Geopositioning/Global_Geopositioning/Point[@name="upperLeft"]/X')
        uly = root.findtext('.//Geopositioning/Global_Geopositioning/Point[@name="upperLeft"]/Y')

        # Call gdalsrs info to generate wkt for the projection :
        # Replaced by gdal python api:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(int(epsg_code))
        wkt = srs.ExportToWkt()

        # Load xml file and extract parameter for sun zenith :
        viewing_angle_nodes = root.findall(
            './/Viewing_Incidence_Angles_Grids_List/Band_Viewing_Incidence_Angles_Grids_List')

        x_size = y_size = col_step = row_step = 0
        v_dico = {}
        for band_viewing_angle in viewing_angle_nodes:
            band_id = band_viewing_angle.attrib["band_id"]
            for viewing_incidence_angles_grid in band_viewing_angle.findall('.//Viewing_Incidence_Angles_Grids'):
                detector = viewing_incidence_angles_grid.attrib["detector_id"]
                selected_node = viewing_incidence_angles_grid.find(f'.//{angle_type}')
                x_size, y_size, col_step, row_step, arr = from_values_list_to_array(selected_node)
                v_dico['_'.join([band_id, detector])] = {"Band_id": get_angles_band_index(band_id),
                                                         "Detector": detector,
                                                         "Values": arr}

        for rec in range(13):
            band_dico = {k: v for k, v in v_dico.items() if v["Band_id"] == rec}
            arr = reduce_angle_matrix(x_size, y_size, band_dico)
            # scale between -180 and 180 deg.
            if arr.max() > 180.0:
                arr[arr > 180] -= 360

            # Create gdal dataset
            x_res = int(x_size)
            y_res = int(y_size)

            x_pixel_size = int(col_step)
            y_pixel_size = int(row_step)

            dst_file_bd = dst_file.replace('.tif', '_band_' + str(rec) + '.tif')
            out_list.append(dst_file_bd)
            log.debug(' Save in %s', dst_file_bd)
            target_ds = gdal.GetDriverByName('GTiff').Create(dst_file_bd, x_res, y_res, 1, gdal.GDT_Int16)
            target_ds.SetGeoTransform(
                (int(float(ulx)), x_pixel_size, 0, int(float(uly)), 0, -y_pixel_size))
            band = target_ds.GetRasterBand(1)
            band.SetNoDataValue(NoData_value)
            band.SetDescription('Viewing_' + angle_type + '_band_' + str(rec))  # This sets the band name!
            target_ds.GetRasterBand(1).WriteArray((arr * 100).astype(np.int16), 0, 0)  # int16 with scale factor 100
            target_ds.SetProjection(wkt)
            band = None
            target_ds = None
            arr = None

        return out_list

    def extract_sun_angle(self, dst_file, angle_type):
        try:
            root = ElementTree.parse(self.mtl_file_name)
        except pars.expat.ExpatError:
            sys.exit('Invalid XML metadata file')

        # gdal parameter :
        NoData_value = -9999

        # Load xmlf file and retrieve projection parameter :
        epsg_code = root.findtext('.//Horizontal_Coordinate_System/HORIZONTAL_CS_CODE')
        ulx = root.findtext('.//Geopositioning/Global_Geopositioning/Point[@name="upperLeft"]/X')
        uly = root.findtext('.//Geopositioning/Global_Geopositioning/Point[@name="upperLeft"]/Y')

        # Call gdalsrs info to generate wkt for the projection
        # Replaced by gdal python api:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(int(epsg_code.replace('EPSG:', '')))
        wkt = srs.ExportToWkt()

        # Load xml file and extract parameter for sun zenith :
        # Level-1C / Level-2A ?
        sun_angle_node = root.find('.//Sun_Angles_Grids')

        selected_node = sun_angle_node.find(f'.//{angle_type}')

        x_size, y_size, col_step, row_step, arr = from_values_list_to_array(selected_node)

        # scale between -180 and 180 deg.
        if arr.max() > 180.0:
            arr[arr > 180] -= 360

        # Create gdal dataset
        x_res = int(x_size)
        y_res = int(y_size)

        x_pixel_size = int(col_step)
        y_pixel_size = int(row_step)

        log.debug(' Save in %s', dst_file)
        target_ds = gdal.GetDriverByName('GTiff').Create(dst_file, x_res, y_res, 1, gdal.GDT_Int16)
        target_ds.SetGeoTransform((int(float(ulx)), x_pixel_size, 0, int(float(uly)), 0, -y_pixel_size))
        band = target_ds.GetRasterBand(1)
        band.SetNoDataValue(NoData_value)
        band.SetDescription('Solar_' + angle_type)
        band.WriteArray((arr * 100).astype(np.int16), 0, 0)  # int16 with scale factor 100
        target_ds.SetProjection(wkt)

    def get_scene_center_coordinates(self):
        m = mgrs.MGRS()
        lat, lon = m.toLatLon(self.mgrs + '5490045100')
        return lon, lat
