import glob
import logging
import os
import re
import sys
from xml import parsers as pars
from xml.dom import minidom

import numpy as np
import mgrs

from core.metadata_extraction import from_date_to_doy
from core.readers.reader import BaseReader

log = logging.getLogger('Sen2Like')


def node_value(dom, node_name):
    """Read xml node data.

    :param dom: The xml object to read from
    :param node_name: the name of the node
    :return: The data of the given node
    """
    node = dom.getElementsByTagName(node_name)[0]
    return node.childNodes[0].data


class Sentinel2MTL(BaseReader):
    """Object for S2 product metadata extraction"""

    def __init__(self, product_path, mtd_file=None):
        super().__init__(product_path)

        if not os.path.exists(self.product_path):
            log.error('Input product does not exist')
            self.isValid = False
            return

        self.isValid = True
        # default: short name convention (recent format)
        is_compact = True

        self.granule_id = None
        granule_folder = os.path.join(product_path, 'GRANULE')

        if os.path.exists(granule_folder):
            with os.scandir(granule_folder) as it:
                for entry in it:
                    if entry.is_dir():
                        self.granule_id = os.path.basename(entry.name)
                    break

            if len(self.granule_id) == 62:
                # long name convention
                is_compact = False
        else:
            self.granule_id = product_path

        if is_compact:
            self.mgrs = self.granule_id.split('_')[1][-5:]
        else:
            self.mgrs = self.granule_id.split('_')[-2][-5:]

        try:
            mtl_file_name = glob.glob(os.path.join(self.product_path, '*MTD*.xml'))[0]
        except IndexError:
            self.isValid = False
            sys.exit('No MTD product file information found')
        try:
            dom = minidom.parse(mtl_file_name)
        except pars.expat.ExpatError as err:
            self.isValid = False
            log.error("Error during parsing of MTD product file: %s", mtl_file_name)
            log.error(err)
            sys.exit(-1)

        self.aerosol_band = None
        self.aerosol_value = None

        # Getting datastrip and datatake sensing time from DATASTRIP MTD
        datastrip_path = glob.glob(os.path.join(self.product_path, 'DATASTRIP', '*', '*MTD*.xml'))
        datastrip_metadata = datastrip_path[0] if len(datastrip_path) != 0 else None
        if datastrip_metadata:
            dom_ds = minidom.parse(datastrip_metadata)
            self.datastrip_metadata = datastrip_metadata
            self.dt_sensing_start = node_value(dom_ds, 'DATATAKE_SENSING_START')
            # Also equal to str(node_value(dom, 'SENSING_TIME')) with dom being the tile mtd
            self.ds_sensing_start = node_value(dom_ds, 'DATASTRIP_SENSING_START')

        # Read XML Metadata
        try:
            # mini dom
            self.mtl_file_name = mtl_file_name

            self.data_type = node_value(dom, 'PROCESSING_LEVEL')  # Level-1C / Level-2
            self.product_type = node_value(dom, 'PRODUCT_TYPE')  # S2MSI2A / S2MSI1C

            if self.data_type in ('Level-1C', 'Level-2A'):
                # FILE_DATE = 2017 - 11 - 30T16:00:05Z %DEFINITION LANDSAT
                try:
                    self.product_name = node_value(dom, 'PRODUCT_URI')
                except IndexError:
                    sys.exit(' No product URI found ')

            self.file_date = node_value(dom, 'GENERATION_TIME')
            self.processing_sw = node_value(dom, 'PROCESSING_BASELINE')
            self.mission = node_value(dom, 'SPACECRAFT_NAME')
            self.sensor = self.product_type[-5:-2]  # Need sensor is always 3 character
            self.relative_orbit = node_value(dom, 'SENSING_ORBIT_NUMBER')
            if not datastrip_metadata:
                self.dt_sensing_start = str(node_value(dom, 'PRODUCT_START_TIME'))
            node_name = 'Granule'
            node1 = dom.getElementsByTagName(node_name)
            if len(node1) == 0:
                # manage old S2 format (SAFE not compact)
                node_name = 'Granules'
                node1 = dom.getElementsByTagName(node_name)

            # Check if product is refined (GRI)
            if float(self.processing_sw) >= 3:
                gri_list = dom.getElementsByTagName('GRI_List')
                if gri_list and gri_list[0].getElementsByTagName('GRI_FILENAME'):
                    self.is_refined = True

            self.scene_classif_band = None
            self.bands = {}

            file_path = None
            self.file_extension = '.jp2'
            for node in node1:
                if node.hasAttribute('imageFormat') and node.attributes['imageFormat'] == 'GEOTIFF':
                    self.file_extension = '.TIF'
                for rec in node.childNodes:
                    if rec.nodeType == 1:  # Select DOM Text Node
                        file_path = rec.childNodes[0].data
                        if self.data_type in ['Level-2A', 'Level-2F', 'Level-2H']:
                            band_id = file_path[-7:]
                        else:
                            band_id = file_path[-3:]

                        if is_compact:
                            file_path = os.path.join(self.product_path, file_path + self.file_extension)
                        else:
                            file_path = os.path.join(self.product_path, 'GRANULE', self.granule_id, 'IMG_DATA',
                                                     file_path + self.file_extension)
                        log.debug('%s %s', band_id, file_path)
                        self.bands[band_id] = file_path
            # Band name ordered by their integer id in datastrip (base on spectral information)
            spectral_information = dom.getElementsByTagName('Spectral_Information')
            self.band_names = [''] * len(spectral_information)
            for _, node in enumerate(spectral_information):
                indice = int(node.attributes['bandId'].value)
                band_name = node.attributes['physicalBand'].value
                self.band_names[indice] = self.set_zero_in_band_name(band_name)

            if 'SCL_20m' in self.bands.keys():
                self.scene_classif_band = self.bands['SCL_20m']

            # Collection not applicable for Landsat
            self.collection = ' '

            # RESCALING GAIN And OFFSET :
            for quantification_node_name in [
                    'QUANTIFICATION_VALUE', 'BOA_QUANTIFICATION_VALUE', 'L2A_BOA_QUANTIFICATION_VALUE']:
                try:
                    self.quantification_value = node_value(
                        dom, quantification_node_name)
                    break
                except IndexError:
                    pass

            self._set_radiometric_offset_dic(dom)

            self.dE_S = node_value(dom, 'U')

            nodes = dom.getElementsByTagName('SOLAR_IRRADIANCE')
            self.radio_coefficient_dic = {}
            self.band_sequence = []
            for cpt, node in enumerate(nodes):
                band_id = node.attributes['bandId']
                self.band_sequence.append(band_id.value)
                solar_irradiance = node.childNodes[0].data
                self.radio_coefficient_dic[str(cpt)] = {"Band_id": str(band_id),
                                                        "Gain": 0.00001, "Offset": 0.0,
                                                        "Solar_irradiance": solar_irradiance
                                                        }
            self.band_sequence = [int(rec) + 1 for rec in self.band_sequence]
            self.rescaling_gain = [0.00001] * len(self.band_sequence)
            self.rescaling_offset = [0] * len(self.band_sequence)

            tab = [self.radio_coefficient_dic[x]["Solar_irradiance"] for x in self.radio_coefficient_dic]
            self.solar_irradiance = [np.double(rec) for rec in tab]

            try:
                self.cloud_cover = node_value(dom, 'Cloud_Coverage_Assessment')
            except IndexError:
                self.cloud_cover = None

            # Compute scene boundary - EXT_POS_LIST tag
            pos_list = node_value(dom, 'EXT_POS_LIST').split()
            scene_boundary_lat = [rec for j, rec in enumerate(pos_list) if j % 2 == 0]
            scene_boundary_lon = [rec for j, rec in enumerate(pos_list) if j % 2 == 1]
            self.scene_pos_list = pos_list
            arr1 = np.asarray(scene_boundary_lat, float)
            arr1_r = np.roll(arr1, -1)
            # Retour d index
            arr2 = np.asarray(scene_boundary_lon, float)
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
            log.error(' -- Warning - error with MTD', exc_info=1)
            log.error(' -- Procedure aborted')
            self.mtl_file_name = ''
        # Observation date of the GRANULE
        # Assume only one Tile in the product
        if self.data_type == "Level-2A" and not os.path.basename(self.product_path).startswith('L2F'):
            tile_rep = os.path.dirname(os.path.dirname(os.path.dirname(file_path)))
        elif os.path.basename(self.product_path).startswith('L2F'):
            tile_rep = ''
        elif self.data_type in ["Level-2H", "Level-2F"] and os.path.basename(os.path.dirname(file_path)) == 'NATIVE':
            tile_rep = os.path.dirname(os.path.dirname(os.path.dirname(file_path)))
        else:
            tile_rep = os.path.dirname(os.path.dirname(file_path))

        if tile_rep is not None:
            self.tile_metadata = glob.glob(os.path.join(self.product_path, tile_rep, '*MTD*_TL*.xml'))[0]
            log.debug(self.tile_metadata)
            try:
                dom = minidom.parse(self.tile_metadata)
            except pars.expat.ExpatError:
                self.isValid = False
                sys.exit(' -- Not well formed MTD Tile XML file')
            except IOError:
                log.error(' -- No MTD  TL XML file')

            try:
                self.doy = 0
                sun_node = dom.getElementsByTagName('Mean_Sun_Angle')[0]
                self.sun_zenith_angle = node_value(sun_node, 'ZENITH_ANGLE')
                self.sun_azimuth_angle = node_value(sun_node, 'AZIMUTH_ANGLE')

                self.viewing_azimuth_angle = {}
                self.viewing_zenith_angle = {}
                node = dom.getElementsByTagName('Mean_Viewing_Incidence_Angle_List')[0]
                sub_nodes = node.getElementsByTagName('Mean_Viewing_Incidence_Angle')
                for cpt, sub_node in enumerate(sub_nodes):
                    band_id = sub_node.attributes['bandId'].value
                    self.viewing_azimuth_angle[str(cpt)] = {"Band_id": str(band_id),
                                                            "VAA": node_value(sub_node, 'AZIMUTH_ANGLE'),
                                                            }
                    self.viewing_zenith_angle[str(cpt)] = {"Band_id": str(band_id),
                                                           "VZA": node_value(sub_node, 'ZENITH_ANGLE'),
                                                           }

                # TO USE </Viewing_Incidence_Angles_Grids> to set the angle files
                # self.angles_file = None

                node = dom.getElementsByTagName('Tile_Geocoding')[0]
                self.utm = node_value(node, 'HORIZONTAL_CS_NAME')

                # 2017 - 12 - 07T09:13:39.027 Z
                d = str(node_value(dom, 'SENSING_TIME'))
                obs = d.split('T')[0]
                rr = obs.split('-')  # 2007-12-08
                input_date = rr[2] + '-' + rr[1] + '-' + rr[0]
                self.doy = from_date_to_doy(input_date)
                self.scene_center_time = d.split('T')[1]
                self.observation_date = obs
                if not datastrip_metadata:
                    self.ds_sensing_start = str(node_value(dom, 'SENSING_TIME'))

                self.epsg = node_value(dom, 'HORIZONTAL_CS_CODE')
                self.ULX = int(node_value(dom, 'ULX'))
                self.ULY = int(node_value(dom, 'ULY'))
                XDIM = int(node_value(dom, 'XDIM'))
                YDIM = int(node_value(dom, 'YDIM'))
                NROWS = int(node_value(dom, 'NROWS'))
                NCOLS = int(node_value(dom, 'NCOLS'))
                self.LRX = self.ULX + XDIM * NCOLS
                self.LRY = self.ULY + YDIM * NROWS

                nodes = dom.getElementsByTagName('MASK_FILENAME')
                self.cloudmask = []
                self.nodata_mask = {}
                self.detfoo_mask = {}
                for node in nodes:
                    maskpath = node.childNodes[0].data
                    if is_compact:
                        # new S2 format
                        maskpath = os.path.join(product_path, maskpath)
                        log.debug('compact s2 format')
                    else:
                        # old S2 format
                        log.debug('old s2 format')

                        maskpath = os.path.join(product_path, 'GRANULE', self.granule_id, 'QI_DATA', maskpath)

                    log.debug('mask path: %s', maskpath)
                    log.debug('mask type: %s', node.getAttribute("type"))

                    _type = node.getAttribute('type')
                    if _type in ['MSK_CLOUDS', 'MSK_CLASSI']:
                        self.cloudmask = maskpath
                    elif _type in ['MSK_NODATA', 'MSK_QUALIT']:
                        band = os.path.splitext(maskpath)[0][-3:]
                        self.nodata_mask[band] = maskpath
                    elif _type == 'MSK_DETFOO':
                        band = os.path.splitext(maskpath)[0][-3:]
                        self.detfoo_mask[band] = maskpath

                log.debug('Cloud Mask: %s', self.cloudmask)
                log.debug('No data mask: %s', self.nodata_mask)
                log.debug('Defective detector: %s', self.detfoo_mask)
            except IndexError:
                sys.exit(' TILE MTL Parsing Issue ')
        else:
            log.error(' -- Tile file not found --')
            self.isValid = False

        # Absolute orbit is contained in the granule ID as _A00000_
        absolute_orbit = re.compile(r'A\d{6}_').search(self.granule_id)
        self.absolute_orbit = '000000' if absolute_orbit is None else absolute_orbit.group()[1:-1]

        # L2A QI report file
        if self.data_type == "Level-2A":
            self.l2a_qi_report_path = os.path.join(
                product_path, 'GRANULE', self.granule_id, 'QI_DATA', 'L2A_QUALITY.xml')
            if not os.path.isfile(self.l2a_qi_report_path):
                self.l2a_qi_report_path = None

    @staticmethod
    def can_read(product_name):
        name = os.path.basename(product_name)
        S2L_structure_check = os.path.isdir(os.path.join(product_name, 'GRANULE')) and \
                              ('L2F_' in name or 'LS8_' in name or 'LS9_' in name)
        return name.startswith('S2') or (name.startswith('L2F') and '_S2' in name) or S2L_structure_check

    def get_scene_center_coordinates(self):
        m = mgrs.MGRS()
        lat, lon = m.toLatLon(self.mgrs + '5490045100')
        return lon, lat

    def set_zero_in_band_name(self, band):
        """ Set 0 in band name (ex: B1 -> B01)"""
        if len(band) == 2:
            band = band[0] + '0' + band[1]
        return band

    def _set_radiometric_offset_dic(self, dom: minidom.Document):
        """set radiometric_offset_dic attr with:
        - RADIO_ADD_OFFSET is present in dom (L1)
        - BOA_ADD_OFFSET_VALUES_LIST is present in dom (L2)
        - otherwise to None

        Args:
            dom (minidom.Document): document of L1 or L2 S2 MTD
        """

        # try L2 case first, never present in L1
        radio_add_offset_list = dom.getElementsByTagName('BOA_ADD_OFFSET_VALUES_LIST')
        if len(radio_add_offset_list) == 0:
            # L1 case, never present in L2
            radio_add_offset_list = dom.getElementsByTagName('RADIO_ADD_OFFSET')

        self.radiometric_offset_dic = None
        if len(radio_add_offset_list) > 0:
            log.debug('Radiometric offsets are finded.')
            self.radiometric_offset_dic = {}
            for _, node in enumerate(radio_add_offset_list):
                band_id = node.attributes['band_id'].value
                radio_add_offset = node.childNodes[0].data
                self.radiometric_offset_dic[int(band_id)] = radio_add_offset
