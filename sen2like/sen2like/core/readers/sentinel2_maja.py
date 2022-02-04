import glob
import logging
import os
import sys
import xml.etree.ElementTree as ElementTree
from xml import parsers as pars

import numpy as np
from osgeo import osr
from osgeo import gdal
import mgrs

from atmcor.get_s2_angles import reduce_angle_matrix, from_values_list_to_array, get_angles_band_index
from core.image_file import S2L_ImageFile
from core.metadata_extraction import from_date_to_doy
from core.readers.reader import BaseReader

log = logging.getLogger('Sen2Like')


class Sentinel2MajaMTL(BaseReader):
    resolutions = {10: 'R1', 20: 'R2'}
    classif_band = {10: 'B4', 20: 'B5'}

    # Object for metadata extraction

    def __init__(self, product_path, mtd_file=None):
        super().__init__(product_path)

        if not os.path.exists(self.product_path):
            log.error('Input product does not exist')
            self.isValid = False
            return

        self.isValid = True

        self.mgrs = os.path.basename(self.product_path).split('_')[3][-5:]

        try:
            mtl_file_name = glob.glob(os.path.join(self.product_path, '*MTD*.xml'))[0]
        except IndexError:
            self.isValid = False
            sys.exit('No MTD product file information found')
        try:
            root = ElementTree.parse(mtl_file_name)
        except pars.expat.ExpatError as err:
            self.isValid = False
            logging.error("Error during parsing of MTD product file: %s" % mtl_file_name)
            logging.error(err)
            sys.exit(-1)

        self.mask_filename = None
        self.nodata_mask_filename = None
        self.aerosol_band = None
        self.aerosol_value = None

        self.dt_sensing_start = root.findtext('Product_Characteristics/ACQUISITION_DATE')
        self.ds_sensing_start = root.findtext('Product_Characteristics/ACQUISITION_DATE')

        # Read XML Metadata
        try:
            # mini dom
            self.mtl_file_name = mtl_file_name

            self.data_type = root.findtext('Product_Characteristics/PRODUCT_LEVEL')  # Level-1C / Level-2
            self.product_name = root.findtext('Product_Characteristics/PRODUCT_ID')

            self.file_date = root.findtext('Product_Characteristics/PRODUCTION_DATE')
            self.processing_sw = root.findtext('Product_Characteristics/PRODUCT_VERSION')
            self.mission = root.findtext('Product_Characteristics/PLATFORM')
            self.sensor = 'MSI'
            self.absolute_orbit = root.findtext('Product_Characteristics/ORBIT_NUMBER')

            image_list_node = root.findall('.//Image_List/Image')

            self.bands = {}

            for image_node in image_list_node:
                nature = image_node.findtext('Image_Properties/NATURE')
                if nature == 'Surface_Reflectance':
                    bands_files = image_node.findall('.//Image_File_List/IMAGE_FILE')
                    for band_file in bands_files:
                        band_id = band_file.text.split('_')[-1].split('.')[0]
                        file_path = os.path.join(self.product_path, band_file.text)
                        log.debug('{} {}'.format(band_id, file_path))
                        self.bands[band_id] = file_path

            # Collection not applicable for Landsat
            # self.collection = ' '
            self.radio_coefficient_dic = {}

            # RESCALING GAIN And OFFSET :
            self.quantification_value = root.findtext('.//Radiometric_Informations/REFLECTANCE_QUANTIFICATION_VALUE')

            solar_nodes = root.findall('.//Spectral_Band_Informations_List/Spectral_Band_Informations')
            self.band_sequence = []
            for solar_band_node in solar_nodes:
                band_id = solar_band_node.attrib['band_id']
                self.band_sequence.append(band_id)
                solar_irradiance = solar_band_node.findtext('.//SOLAR_IRRADIANCE')
                self.radio_coefficient_dic[band_id] = {"Band_id": band_id,
                                                       "Gain": 0.00001, "Offset": 0.0,
                                                       "Solar_irradiance": solar_irradiance
                                                       }

            # self.band_sequence = [np.int(rec) + 1 for rec in self.band_sequence]
            # self.rescaling_gain = [0.00001] * len(self.band_sequence)
            # self.rescaling_offset = [0] * len(self.band_sequence)

            tab = [self.radio_coefficient_dic[x]["Solar_irradiance"] for x in self.radio_coefficient_dic]
            self.solar_irradiance = [np.double(rec) for rec in tab]
            self.cloud_cover = root.findtext('.//Global_Index_List/QUALITY_INDEX[@name="CloudPercent"]')

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
            self.angles_file = None
            self.sun_zenith_angle = root.findtext('.//Geometric_Informations/Mean_Value_List/Sun_Angles/ZENITH_ANGLE')
            self.sun_azimuth_angle = root.findtext('.//Geometric_Informations/Mean_Value_List/Sun_Angles/AZIMUTH_ANGLE')

            self.viewing_azimuth_angle = {}
            self.viewing_zenith_angle = {}
            incidence_angle_nodes = root.find('.//Mean_Viewing_Incidence_Angle_List')
            for cpt, incidence_angle_node in enumerate(incidence_angle_nodes):
                band_id = incidence_angle_node.attrib['band_id']
                self.viewing_azimuth_angle[str(cpt)] = {"Band_id": band_id,
                                                        "VAA": incidence_angle_node.findtext('AZIMUTH_ANGLE'),
                                                        }
                self.viewing_zenith_angle[str(cpt)] = {"Band_id": band_id,
                                                       "VZA": incidence_angle_node.findtext('ZENITH_ANGLE'),
                                                       }

            # TO USE </Viewing_Incidence_Angles_Grids> to set the angle files
            self.angles_file = None

            geoposition_node = root.find('Geoposition_Informations/Coordinate_Reference_System')
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

            mask_nodes = root.findall('.//Mask_List/Mask')
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

    def get_valid_pixel_mask(self, mask_filename, res=20):
        """
        :param res:
        :param mask_filename:
        :return:
        """
        resolution = self.resolutions.get(res)
        mask_band = self.classif_band.get(res)

        log.info('Read validity and nodata masks')
        log.debug(f'Read mask: {mask_band}')

        # No data mask
        edge = S2L_ImageFile(os.path.join(self.product_path, self.edge_mask[resolution]))
        edge_arr = edge.array
        defective = S2L_ImageFile(os.path.join(self.product_path, self.nodata_mask[mask_band]))
        defective_arr = defective.array

        nodata = np.zeros(edge_arr.shape, np.uint8)
        nodata[edge_arr == 1] = 1
        nodata[defective_arr == 1] = 1

        del edge_arr
        del defective_arr

        nodata_mask_filename = os.path.join(os.path.dirname(mask_filename), 'nodata_pixel_mask.tif')
        mask = edge.duplicate(nodata_mask_filename, array=nodata)
        mask.write(creation_options=['COMPRESS=LZW'])
        self.nodata_mask_filename = mask_filename

        # Validity mask
        cloud = S2L_ImageFile(os.path.join(self.product_path, self.cloud_mask[resolution]))
        cloud_arr = cloud.array
        saturation = S2L_ImageFile(os.path.join(self.product_path, self.saturation_mask[mask_band]))
        saturation_arr = saturation.array

        valid_px_mask = np.ones(cloud_arr.shape, np.uint8)
        valid_px_mask[cloud_arr == 1] = 0
        valid_px_mask[cloud_arr == 2] = 0
        valid_px_mask[cloud_arr == 4] = 0
        valid_px_mask[cloud_arr == 8] = 0
        valid_px_mask[saturation_arr == 1] = 0
        valid_px_mask[nodata == 1] = 0

        mask = cloud.duplicate(mask_filename, array=valid_px_mask)
        mask.write(creation_options=['COMPRESS=LZW'])
        self.mask_filename = mask_filename

        return True

    def get_angle_images(self, DST=None):
        """
        :param DST: Optional name of the output tif containing all angle images
        :return: set self.angles_file
        Following band order : SAT_AZ , SAT_ZENITH, SUN_AZ, SUN_ZENITH ')
        The unit is DEGREES
        """
        if DST is not None:
            root_dir = os.path.dirname(DST)
        else:
            root_dir = os.path.dirname(self.tile_metadata)

        # Viewing Angles (SAT_AZ / SAT_ZENITH)
        dst_file = os.path.join(root_dir, 'VAA.tif')
        out_file_list = self.extract_viewing_angle(dst_file, 'Azimuth')

        dst_file = os.path.join(root_dir, 'VZA.tif')
        out_file_list.extend(self.extract_viewing_angle(dst_file, 'Zenith'))

        # Solar Angles (SUN_AZ, SUN_ZENITH)
        dst_file = os.path.join(root_dir, 'SAA.tif')
        self.extract_sun_angle(dst_file, 'Azimuth')
        out_file_list.append(dst_file)

        dst_file = os.path.join(root_dir, 'SZA.tif')
        self.extract_sun_angle(dst_file, 'Zenith')
        out_file_list.append(dst_file)

        out_vrt_file = os.path.join(root_dir, 'tie_points.vrt')
        gdal.BuildVRT(out_vrt_file, out_file_list, separate=True)

        if DST is not None:
            out_tif_file = DST
        else:
            out_tif_file = os.path.join(root_dir, 'tie_points.tif')
        gdal.Translate(out_tif_file, out_vrt_file, format="GTiff")

        self.angles_file = out_vrt_file
        log.info('SAT_AZ, SAT_ZENITH, SUN_AZ, SUN_ZENITH')
        log.info('UNIT = DEGREES (scale: x100) :')
        log.info('             ' + out_tif_file)
        self.angles_file = out_tif_file

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
            x_res = np.int(x_size)
            y_res = np.int(y_size)

            x_pixel_size = np.int(col_step)
            y_pixel_size = np.int(row_step)

            dst_file_bd = dst_file.replace('.tif', '_band_' + str(rec) + '.tif')
            out_list.append(dst_file_bd)
            log.debug(' Save in {}'.format(dst_file_bd))
            target_ds = gdal.GetDriverByName('GTiff').Create(dst_file_bd, x_res, y_res, 1, gdal.GDT_Int16)
            target_ds.SetGeoTransform(
                (np.int(np.float(ulx)), x_pixel_size, 0, np.int(np.float(uly)), 0, -y_pixel_size))
            band = target_ds.GetRasterBand(1)
            band.SetNoDataValue(NoData_value)
            band.SetDescription('Viewing_' + angle_type + '_band_' + str(rec))  # This sets the band name!
            target_ds.GetRasterBand(1).WriteArray((arr * 100).astype(np.int16), 0, 0)  # int16 with scale factor 100
            target_ds.SetProjection(wkt)
            band = None
            target_ds = None
            arr = None
            a = None

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
        node_name = 'Sun_Angles_Grid'  # Level-1C / Level-2A ?
        sun_angle_node = root.find('.//Sun_Angles_Grids')

        selected_node = sun_angle_node.find(f'.//{angle_type}')

        x_size, y_size, col_step, row_step, arr = from_values_list_to_array(selected_node)

        # scale between -180 and 180 deg.
        if arr.max() > 180.0:
            arr[arr > 180] -= 360

        # Create gdal dataset
        x_res = np.int(x_size)
        y_res = np.int(y_size)

        x_pixel_size = np.int(col_step)
        y_pixel_size = np.int(row_step)

        log.debug(' Save in {}'.format(dst_file))
        target_ds = gdal.GetDriverByName('GTiff').Create(dst_file, x_res, y_res, 1, gdal.GDT_Int16)
        target_ds.SetGeoTransform((np.int(np.float(ulx)), x_pixel_size, 0, np.int(np.float(uly)), 0, -y_pixel_size))
        band = target_ds.GetRasterBand(1)
        band.SetNoDataValue(NoData_value)
        band.SetDescription('Solar_' + angle_type)
        band.WriteArray((arr * 100).astype(np.int16), 0, 0)  # int16 with scale factor 100
        target_ds.SetProjection(wkt)

    def get_scene_center_coordinates(self):
        m = mgrs.MGRS()
        lat, lon = m.toLatLon(self.mgrs + '5490045100')
        return lon, lat


def from_values_list_to_array(selected_node):
    col_step = selected_node.findtext('COL_STEP')
    row_step = selected_node.findtext('ROW_STEP')

    values_list = selected_node.find('.//Values_List').findall('.//VALUES')

    # x_size, y_size , size of the matrix
    x_size = len(values_list[0].text.split())
    y_size = len(values_list)

    # Create np array of size (x_size, y_size) for values :
    arr = np.empty([x_size, y_size], np.float)
    for j in range(y_size):
        a = np.asarray(values_list[j].text.split(), np.float)
        arr[j] = a

    return x_size, y_size, col_step, row_step, arr
