import fnmatch
import glob
import io
import logging
import os
import re

from core.metadata_extraction import NOT_FOUND, reg_exp, compute_earth_solar_distance, get_in_band_solar_irrandiance_value
from core.readers.reader import BaseReader


log = logging.getLogger('Sen2Like')

band_regex = re.compile(r'[B,d]\d{1,2}')

# LC08_L1TP_196030_20171130_20171130_01_RT_sr_band2.tif => regex2
regex2 = r'(?i)L[O,M,T,C]0[1-9]_L.*_(RT|T1|LT|T2).*(_MTI)?_sr_band\d{1,2}.tif'
p2 = re.compile(regex2)
# LM31980381978220MTI00_B4.TIF                        => regex3
# LC81960302015153MTI00_B2.TIF                        => regex3
regex3 = '(?i)L[O,M,T,C][1-9].*_B.?.TIF'
p3 = re.compile(regex3)
# LT05_L1TP_198030_20111011_20161005_01_T1_B1.TIF     => regex4
# LC08_L1TP_196030_20170420_20170501_01_T1_B1.TIF     => regex4
# LC08_L1TP_196030_20171130_20171130_01_RT_MTI_B1.TIF => regex4
# LC08_L1GT_087113_20171118_20171205_01_T2_B1.TIF     => regex4
regex4 = r'(?i)L[O,M,T,C]0[1-9]_L.*_(RT|T1|LT|T2).*(_MTI)?B\d{1,2}.TIF(F)?'
p4 = re.compile(regex4)


class LandsatMTL(BaseReader):
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

        mtl_regex = 'L*_MTL.txt'
        # Recherche du MTL file, soit :
        # Directement dans le repertoire d entree               => USGS
        # Dans un sous repertoire contentant le suffix (.TIFF)  => ESA

        md_list_1 = glob.glob(os.path.join(self.product_path, mtl_regex))
        md_list_2 = glob.glob(os.path.join(self.product_path, os.path.basename(product_path) + '.TIFF', mtl_regex))
        md_list = md_list_1 + md_list_2
        # check if MTL file is present
        if not md_list:
            log.error(' Warning - no MTL file found')
            log.error(' Procedure aborted')
            self.isValid = False
            return

        try:
            mtl_file_name = md_list_1[0]
            self.product_directory_name = os.path.basename(self.product_path)
            self.mtl_file_name = mtl_file_name
            with io.open(mtl_file_name, 'r') as mtl_file:
                mtl_text = mtl_file.read()
            self.product_name = os.path.basename(
                os.path.dirname(mtl_file_name))  # PRODUCT_NAME # VDE : linux compatible

            string_to_search = 'COLLECTION_NUMBER =.*'
            self.collection_number = reg_exp(mtl_text, string_to_search)

            regex = re.compile('LANDSAT_SCENE_ID =.*')
            res = regex.findall(mtl_text)
            if res:
                self.landsat_scene_id = res[0].split('=')[1].replace('"', '').replace(' ', '')
            else:
                self.landsat_scene_id = os.path.basename(mtl_file_name).split('_')[0].replace(" ", "")
            log.info(' -- Landsat_id : %s', self.landsat_scene_id)

            string_to_search = 'LANDSAT_PRODUCT_ID =.*'
            self.product_id = reg_exp(mtl_text, string_to_search)
            if self.collection_number == '02':
                string_to_search = 'DATE_PRODUCT_GENERATED =.*'
            else:
                string_to_search = 'FILE_DATE =.*'
            self.file_date = reg_exp(mtl_text, string_to_search)
            string_to_search = 'PROCESSING_SOFTWARE_VERSION =.*'
            self.processing_sw = reg_exp(mtl_text, string_to_search)
            string_to_search = 'SPACECRAFT_ID =.*'
            self.mission = reg_exp(mtl_text, string_to_search)
            string_to_search = 'SENSOR_ID =.*'
            self.sensor = reg_exp(mtl_text, string_to_search)
            if self.collection_number == '02':
                string_to_search = 'PROCESSING_LEVEL =.*'
            else:
                string_to_search = 'DATA_TYPE =.*'
            self.data_type = reg_exp(mtl_text, string_to_search)
            string_to_search = 'COLLECTION_CATEGORY =.*'
            self.collection = reg_exp(mtl_text, string_to_search)
            if self.collection == NOT_FOUND:
                self.collection = 'Pre Collection'

            # Les produits de niveau SR ne sont pas indiques dans le MTL (USGS)
            regex = 'L[O, M, T, C]0[1 - 8].*-SC.*'
            p0 = re.compile(regex)
            log.debug('product name: %s', self.product_name)
            # For match the name of directory and not the path is to be provided
            # Conflict with radiometric processing - split required
            # In radiometric processing path with following type :
            #
            test_name = self.product_name.split('/')
            for rec in test_name:
                if p0.match(str(rec)):
                    self.data_type = 'L2A'

            string_to_search = 'MODEL_FIT_TYPE =.*'
            # MODEL_FIT_TYPE = "L1T_SINGLESCENE_OPTIMAL"
            # MODEL_FIT_TYPE = "L1T_MULTISCENE_SUBOPTIMAL"
            # MODEL_FIT_TYPE = "L1G+_MULTISCENE_SUBOPTIMAL"
            self.model_fit = reg_exp(mtl_text, string_to_search)

            if self.data_type in ["L1T", "L2A"]:
                if self.collection_number == '02':
                    string_to_search = 'DATA_SOURCE_ELEVATION =.*'
                else:
                    string_to_search = 'ELEVATION_SOURCE =.*'
                self.elevation_source = reg_exp(mtl_text, string_to_search)
            else:
                self.elevation_source = 'N/A'
            string_to_search = 'OUTPUT_FORMAT =.*'  # OUTPUT_FORMAT

            self.output_format = reg_exp(mtl_text, string_to_search)
            string_to_search = 'EPHEMERIS_TYPE =.*'
            self.ephemeris_type = reg_exp(mtl_text, string_to_search)
            string_to_search = 'SPACECRAFT_ID =.*'
            self.spacecraft_id = reg_exp(mtl_text, string_to_search)
            string_to_search = 'SENSOR_ID =.*'
            self.sensor_id = reg_exp(mtl_text, string_to_search)
            string_to_search = 'WRS_PATH =.*'
            self.path = reg_exp(mtl_text, string_to_search)
            string_to_search = 'WRS_ROW =.*'
            self.row = reg_exp(mtl_text, string_to_search)
            string_to_search = 'DATE_ACQUIRED =.*'
            self.observation_date = reg_exp(mtl_text, string_to_search)
            string_to_search = 'SCENE_CENTER_TIME =.*'
            self.scene_center_time = reg_exp(mtl_text, string_to_search)
            second = (self.scene_center_time.split('.')[1])[0:2]
            self.scene_center_time = ''.join([self.scene_center_time.split('.')[0],
                                              '.', second + 'Z'])

            self.relative_orbit = self.path
            self.absolute_orbit = 'N/A'

            # SET GEOGRAPHIC INFORMATION :
            self.scene_boundary_lat = []
            string_to_search = 'CORNER_UL_LAT_PRODUCT =.*'
            self.scene_boundary_lat.append(reg_exp(mtl_text, string_to_search))
            string_to_search = 'CORNER_UR_LAT_PRODUCT =.*'
            self.scene_boundary_lat.append(reg_exp(mtl_text, string_to_search))
            string_to_search = 'CORNER_LR_LAT_PRODUCT =.*'
            self.scene_boundary_lat.append(reg_exp(mtl_text, string_to_search))
            string_to_search = 'CORNER_LL_LAT_PRODUCT =.*'
            self.scene_boundary_lat.append(reg_exp(mtl_text, string_to_search))
            self.scene_boundary_lon = []
            string_to_search = 'CORNER_UL_LON_PRODUCT =.*'
            self.scene_boundary_lon.append(reg_exp(mtl_text, string_to_search))
            string_to_search = 'CORNER_UR_LON_PRODUCT =.*'
            self.scene_boundary_lon.append(reg_exp(mtl_text, string_to_search))
            string_to_search = 'CORNER_LR_LON_PRODUCT =.*'
            self.scene_boundary_lon.append(reg_exp(mtl_text, string_to_search))
            string_to_search = 'CORNER_LL_LON_PRODUCT =.*'
            self.scene_boundary_lon.append(reg_exp(mtl_text, string_to_search))
            # INFORMATION ON GROUND CONTROL POINTS :
            if self.collection_number == '02':
                string_to_search = 'FILE_NAME_GROUND_CONTROL_POINT =.*'
            else:
                string_to_search = 'GROUND_CONTROL_POINT_FILE_NAME =.*'
            self.gcp_filename = reg_exp(mtl_text, string_to_search)

            if self.processing_sw == "SLAP_03.04":
                if self.data_type == "L1T":
                    log.debug("GCP : %s", self.gcp_filename)
                    if self.gcp_filename != 'NotApplicable-geometricrefinementusingneighbouringscenes':
                        self.model_fit = "L1T_SINGLESCENE_OPTIMAL"
                    else:
                        self.model_fit = "L1T_MULTISCENE_SUBOPTIMAL"
            string_to_search = 'GROUND_CONTROL_POINTS_MODEL =.*'
            self.gcp_nb = reg_exp(mtl_text, string_to_search)
            string_to_search = 'GROUND_CONTROL_POINTS_DISCARDED =.*'
            self.gcp_nb_dis = reg_exp(mtl_text, string_to_search)
            string_to_search = 'GEOMETRIC_RMSE_MODEL =.*'
            self.gcp_rms = reg_exp(mtl_text, string_to_search)
            string_to_search = 'GEOMETRIC_RMSE_MODEL_Y =.*'
            self.gcp_rms_x = reg_exp(mtl_text, string_to_search)
            string_to_search = 'GEOMETRIC_RMSE_MODEL_X =.*'
            self.gcp_rms_y = reg_exp(mtl_text, string_to_search)
            string_to_search = 'GEOMETRIC_MAX_ERR =.*'
            self.gcp_max_err = reg_exp(mtl_text, string_to_search)

            string_to_search = 'GROUND_CONTROL_POINT_RESIDUALS_SKEW_X =.*'
            self.gcp_res_skew_x = reg_exp(mtl_text, string_to_search)
            string_to_search = 'GROUND_CONTROL_POINT_RESIDUALS_SKEW_Y =.*'
            self.gcp_res_skew_y = reg_exp(mtl_text, string_to_search)
            string_to_search = 'GROUND_CONTROL_POINT_RESIDUALS_KURTOSIS_X =.*'
            self.gcp_res_kurt_x = reg_exp(mtl_text, string_to_search)
            string_to_search = 'GROUND_CONTROL_POINT_RESIDUALS_KURTOSIS_Y =.*'
            self.gcp_res_kurt_y = reg_exp(mtl_text, string_to_search)

            # INFORMATION ON FILE NAMES :
            if self.collection_number == '02':
                string_to_search = 'FILE_NAME_METADATA_ODL =.*'
            else:
                string_to_search = 'METADATA_FILE_NAME =.*'

            self.md_filename = reg_exp(mtl_text, string_to_search)
            if self.collection_number == '02':
                string_to_search = 'FILE_NAME_CPF =.*'
            else:
                string_to_search = 'CPF_NAME =.*'
            self.cpf_filename = reg_exp(mtl_text, string_to_search)

            string_to_search = 'CLOUD_COVER =.*'
            self.cloud_cover = reg_exp(mtl_text, string_to_search)
            string_to_search = 'CLOUD_COVER_AUTOMATED_L1 =.*'
            self.cloud_cover_l1 = reg_exp(mtl_text, string_to_search)
            string_to_search = 'IMAGE_QUALITY =.*'
            self.image_quality = reg_exp(mtl_text, string_to_search)
            string_to_search = 'SUN_AZIMUTH =.*'
            self.sun_azimuth_angle = reg_exp(mtl_text, string_to_search)
            string_to_search = 'SUN_ELEVATION =.*'
            self.sun_zenith_angle = 90.0 - float(reg_exp(mtl_text, string_to_search))
            string_to_search = 'UTM_ZONE =.*'
            self.utm_zone = reg_exp(mtl_text, string_to_search)
            string_to_search = 'MAP_PROJECTION =.*'
            self.map_projection = reg_exp(mtl_text, string_to_search)
            string_to_search = 'DATUM =.*'
            self.datum = reg_exp(mtl_text, string_to_search)

            regex = re.compile('FILE_NAME_BAND_.* =.*')
            result = regex.findall(mtl_text)
            image_file_name = []
            self.band_sequence = []
            for k in result:
                image_file_band_name = k.split('=')[1].replace(' ', '').replace('"', '')
                image_file_name.append(image_file_band_name)
                band_id = image_file_band_name.split('.')[0].split('B')[-1]
                if band_id != 'QA':
                    self.band_sequence.append(band_id)

            regex = re.compile('RADIANCE_MAXIMUM_BAND_.* =.*')
            result = regex.findall(mtl_text)
            self.radiance_maximum = []
            for k in result:
                v = float(k.split('=')[1].replace(' ', ''))
                self.radiance_maximum.append(v)

            regex = re.compile('RADIANCE_MINIMUM_.* =.*')
            result = regex.findall(mtl_text)
            self.radiance_minimum = []
            for k in result:
                v = float(k.split('=')[1].replace(' ', ''))
                self.radiance_minimum.append(v)

            self.rad_radio_coefficient_dic = {}
            regex = re.compile('RADIANCE_MULT_BAND_.* =.*')
            result = regex.findall(mtl_text)
            self.rescaling_gain = []
            for cpt, k in enumerate(result):
                v = float(k.split('=')[1].replace(' ', ''))
                self.rescaling_gain.append(v)
                band_id = k.split('_')[3].split('=')[0].replace(' ', '')
                self.rad_radio_coefficient_dic[str(cpt)] = {"Band_id": str(band_id), "Gain": v, "Offset": "0"}

            regex = re.compile('RADIANCE_ADD_BAND_.* =.*')
            result = regex.findall(mtl_text)
            self.rescaling_offset = []
            for cpt, k in enumerate(result):
                v = float((k.split('='))[1].replace(' ', ''))
                band_id = k.split('_')[3].split('=')[0].replace(' ', '')
                for x in self.rad_radio_coefficient_dic:
                    bd = self.rad_radio_coefficient_dic[x]['Band_id']
                    if bd == band_id:
                        self.rad_radio_coefficient_dic[x]['Offset'] = v

            # Reflectance coefficient exclusively for ls8 products

            radio_coefficient_dic = {}
            regex = re.compile('REFLECTANCE_MULT_BAND_.* =.*')
            result = regex.findall(mtl_text)
            self.rho_rescaling_gain = []
            for cpt, k in enumerate(result):
                v = float(k.split('=')[1].replace(' ', ''))
                self.rho_rescaling_gain.append(v)
                band_id = int(k.split('_')[3].split('=')[0].replace(' ', ''))
                if band_id < 10:
                    band_id_st = '0' + str(band_id)
                else:
                    band_id_st = str(band_id)
                radio_coefficient_dic[str(cpt)] = {"Band_id": band_id_st,
                                                   "Gain": v, "Offset": "0"}

            regex = re.compile('REFLECTANCE_ADD_BAND_.* =.*')
            result = (regex.findall(mtl_text))
            self.rho_rescaling_offset = []
            for cpt, k in enumerate(result):
                v = float(k.split('=')[1].replace(' ', ''))
                band_id = int(k.split('_')[3].split('=')[0].replace(' ', ''))
                if band_id < 10:
                    band_id_st = '0' + str(band_id)
                else:
                    band_id_st = str(band_id)
                for x in radio_coefficient_dic:
                    bd = radio_coefficient_dic[x]['Band_id']
                    if bd == band_id_st:
                        radio_coefficient_dic[x]['Offset'] = v

            self.radio_coefficient_dic = radio_coefficient_dic

            # End of Reflectance coefficient exclusively for ls8 products

            self.doy = int(self.landsat_scene_id[13:16])
            self.dE_S = compute_earth_solar_distance(self.doy)
            self.sun_earth_distance = compute_earth_solar_distance(self.doy)
            self.solar_irradiance = get_in_band_solar_irrandiance_value(self.mission, self.sensor)

            #  BQA List :
            if self.collection_number == '02':
                string_to_search = 'FILE_NAME_QUALITY_L1_PIXEL =.*'
            else:
                string_to_search = 'FILE_NAME_BAND_QUALITY =.*'

            self.bqa_filename = None
            bqa_filename = reg_exp(mtl_text, string_to_search)
            if bqa_filename != NOT_FOUND:
                self.bqa_filename = os.path.join(self.product_path, bqa_filename)

            if self.collection_number == '02':
                string_to_search = 'ANGLE_COEFFICIENT_FILE_NAME =.*'
            else:
                string_to_search = 'FILE_NAME_ANGLE_COEFFICIENT =.*'
            ang_filename = reg_exp(mtl_text, string_to_search)
            if ang_filename != NOT_FOUND:
                self.ang_filename = os.path.join(self.product_path, ang_filename)

            self.scl, self.scene_classif_band = self.get_scl_band()

            #  Set Image list :
            self.dn_image_list = None
            self.radiance_image_list = None
            self.rhotoa_image_list = None

            tif_files = [filename for filename in os.listdir(product_path) if
                         re.search(r'\.tif$', filename, re.IGNORECASE)]
            self.tif_image_list = [rec for rec in tif_files if p2.match(rec) or p3.match(rec) or p4.match(rec)]

            # Sen2Cor L2A processing for Landsat-8/9. Get the path of L2A_QUALITY.xml
            if self.data_type == 'L2TP':
                self.l2a_qi_report_path = os.path.join(product_path, 'L2A_QUALITY.xml')
                if not os.path.isfile(self.l2a_qi_report_path):
                    self.l2a_qi_report_path = None

            if self.data_type == 'L2A':
                self.surf_image_list = self.set_image_file_name('surf')
                self.reflective_band_list = self.surf_image_list

                # Assume that for L2A image_file are present
                self.missing_image_in_list = 'FALSE'
                aerosol_file_list = fnmatch.filter(os.listdir(self.product_path), '*sr_aerosol.tif')
                if aerosol_file_list:
                    self.aerosol_band = os.path.join(self.product_path, aerosol_file_list[0])
                    log.info(' -- Aerosol image found ')

            else:
                self.dn_image_list = self.set_image_file_name('DN')

                try:
                    self.dn_image_valid = os.path.exists(self.dn_image_list[0])
                    log.info(' DN Images found')
                except IndexError:
                    self.dn_image_valid = False
                    log.warning(' DN Images not found')

                self.radiance_image_list = self.set_image_file_name('RAD')
                self.radiance_image_valid = False
                for rec in self.radiance_image_list:
                    if os.path.exists(rec):
                        self.radiance_image_valid = True
                        break
                if self.radiance_image_valid:
                    log.info(' Radiance Images found')
                else:
                    self.radiance_image_valid = False
                    log.debug('WARNING No Radiance Images')

                self.rhotoa_image_list = self.set_image_file_name('RHO')
                self.rhotoa_image_valid = False
                for rec in self.rhotoa_image_list:
                    if os.path.exists(rec):
                        self.rhotoa_image_valid = True
                        break
                if self.rhotoa_image_valid:
                    log.info(' Reflectance TOA Images found')
                else:
                    self.rhotoa_image_valid = False
                    log.debug('WARNING No TOA Images')

                # If harmonization reprocessing start at level 2, needs to set
                # reflective band properties in any cases
                if not self.dn_image_valid and not self.radiance_image_valid:
                    if self.rhotoa_image_valid:
                        self.reflective_band_list = self.rhotoa_image_list
                    else:
                        log.warning('Unable to define reflective band')

                # Check Image_file_name versus MTL information
                self.missing_image_in_list = 'FALSE'
                for ch in image_file_name:
                    if not os.path.exists(os.path.join(self.product_path, ch)):
                        self.missing_image_in_list = 'Missing_image'
                        break
        except IndexError:
            # if not md_list:
            log.error(' -- Warning - no MTL *** file found')
            log.error(' -- Procedure aborted')
            self.isValid = False
            self.mtl_file_name = ''

    def _get_band(self, regex):
        image_list = [filename for filename in os.listdir(self.product_path) if
                      re.search(regex, filename, re.IGNORECASE)]
        return len(image_list) > 0, os.path.join(self.product_path, image_list[0]) if image_list else ' '

    def get_scl_band(self):
        return self._get_band(r'.*_SCL\.tif')

    @staticmethod
    def _get_band_id(record, remove=None):
        if remove is None:
            remove = ['B', 'd']
        match = band_regex.search(record)
        if match:
            res = match.group(0)
            for rem in remove:
                res = res.replace(rem, '')
            return int(res)

    def set_image_file_name(self, opt):  # Landsat
        """
        Check if files are present
        Define input / output file names configuration
        :param opt: 'dn' ,'RAD','rho',,,,,,,,,,,
        :return:
        """
        image_list = []

        if opt == 'DN':
            log.info(' -- DN configuration')
            self.reflective_band_list = []
            self.thermal_band_list = []

            array = []
            for record in self.tif_image_list:
                if ('RHO' not in record) and ('RAD' not in record):
                    full_name = os.path.join(self.product_path, record)
                    band_id = self._get_band_id(record)
                    if band_id is not None:
                        array.append([band_id, full_name])
                        if self.mission in ('LANDSAT_8', 'LANDSAT_9'):
                            if band_id in [1, 2, 3, 4, 5, 6, 7, 9]:
                                self.reflective_band_list.append(full_name)
                            elif band_id in [10, 11]:
                                self.thermal_band_list.append(full_name)

                        if self.mission == 'LANDSAT_7':
                            if band_id in [1, 2, 3, 4, 5, 7]:
                                self.reflective_band_list.append(full_name)
                            elif band_id in [6]:
                                self.thermal_band_list.append(full_name)

                        if self.mission == 'LANDSAT_5':  # TM
                            if band_id in [1, 2, 3, 4, 5, 7]:
                                self.reflective_band_list.append(full_name)
                            elif band_id in [6]:
                                self.thermal_band_list.append(full_name)

                        if self.mission in ('LANDSAT_1', 'LANDSAT_2', 'LANDSAT_3', 'LANDSAT_4'):  # MSS
                            if band_id in [1, 2, 3, 4]:
                                self.reflective_band_list.append(full_name)

            if self.reflective_band_list:
                array_sort = sorted(array, key=lambda x: x[0])
                for record in array_sort:
                    image_list.append(record[1])

        if opt == 'RAD':
            log.info(' -- RADIANCE configuration')
            for record in self.dn_image_list:
                band_id = self._get_band_id(record)
                image_list.append(
                    os.path.join(self.product_path, ''.join([self.product_name, '_RAD_B', str(band_id), '.TIF'])))

        if opt == 'RHO':
            log.info(' -- RHO TOA configuration')
            for record in self.tif_image_list:
                if 'RHO' in record:
                    image_list.append(os.path.join(self.product_path, record))
                else:
                    # Add list of TOA
                    for _record in self.dn_image_list:
                        band_id = self._get_band_id(_record)
                        rad = _record.split('_B')[0]
                        image_list.append(
                            os.path.join(self.product_path, ''.join([rad, '_RHO_B', str(band_id), '.TIF'])))

        if opt == 'surf':
            # Assume no additional transformation needed
            log.info(' -- SURFACE REFLECTANCE configuration')
            self.reflective_band_list = []
            array = []
            for record in self.tif_image_list:
                band_id = self._get_band_id(record, ['_sr_band'])
                if band_id is not None:
                    array.append([band_id, record])
                    if self.mission in ('LANDSAT_8', 'LANDSAT_9'):
                        if band_id in [1, 2, 3, 4, 5, 6, 7]:
                            self.reflective_band_list.append(record)
            if not self.reflective_band_list:
                log.warning("%%%%% [WARNING] - No SR file found [set_image_file_name]")
            else:
                log.info("%%%%% !!!!!!!!! - Surface Reflectance file found, [self.surf_image_list] is set")
            self.surf_image_list = self.reflective_band_list[:]

            array_sort = sorted(array, key=lambda x: x[0])
            for record in array_sort:
                image_list.append(record[1])

        return image_list

    @staticmethod
    def can_read(product_name):
        name = os.path.basename(product_name)
        return name.startswith('LC') or name.startswith('LO') or \
               (name.startswith('L2F') and ('_LS8_' in name or '_LS9_' in name))
