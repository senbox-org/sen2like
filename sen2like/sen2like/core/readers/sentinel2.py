import glob
import logging
import os
import sys
import shutil
import re
from xml import parsers as pars

import numpy as np
from osgeo import gdal, osr
from skimage.transform import resize as skit_resize
from xml.dom import minidom

from atmcor import get_s2_angles as s2_angles
from core.metadata_extraction import from_date_to_doy
from core.readers.reader import BaseReader
from core.image_file import S2L_ImageFile

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

    # Object for metadata extraction

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
            self.mgrs = self.granule_id.split('_')[1]
        else:
            self.mgrs = self.granule_id.split('_')[-2]

        try:
            mtl_file_name = glob.glob(os.path.join(self.product_path, '*MTD*.xml'))[0]
        except IndexError:
            self.isValid = False
            sys.exit('No MTD product file information found')
        try:
            dom = minidom.parse(mtl_file_name)
        except pars.expat.ExpatError:
            self.isValid = False
            sys.exit('Not well formed MTD product file')

        self.mask_filename = None
        self.nodata_mask_filename = None
        self.aerosol_band = None
        self.aerosol_value = None

        # Getting datastrip and datatake sensing time from DATASTRIP MTD
        datastrip_path = glob.glob(os.path.join(self.product_path, 'DATASTRIP', '*', '*MTD*.xml'))
        datastrip_metadata = datastrip_path[0] if len(datastrip_path) != 0 else None
        if datastrip_metadata:
            dom_ds = minidom.parse(datastrip_metadata)
            self.datastrip_metadata = datastrip_metadata
            self.dt_sensing_start = node_value(dom_ds, 'DATATAKE_SENSING_START')
            self.ds_sensing_start = node_value(dom_ds, 'DATASTRIP_SENSING_START')  # Also equal to str(node_value(dom, 'SENSING_TIME'))  , with dom being the tile mtd

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
            self.sensor = 'MSI'
            self.relative_orbit = node_value(dom, 'SENSING_ORBIT_NUMBER')
            if not datastrip_metadata:
                self.dt_sensing_start = str(node_value(dom, 'PRODUCT_START_TIME'))
            node_name = 'Granule'
            node1 = dom.getElementsByTagName(node_name)
            if len(node1) == 0:
                # manage old S2 format (SAFE not compact)
                node_name = 'Granules'
                node1 = dom.getElementsByTagName(node_name)

            self.scene_classif_band = None
            self.bands = {}
            file_path = None
            ext = '.jp2'
            for node in node1:
                for rec in node.childNodes:
                    if rec.nodeType == 1:  # Select DOM Text Node
                        file_path = rec.childNodes[0].data
                        if self.data_type in ['Level-2A', 'Level-2F', 'Level-2H']:
                            band_id = file_path[-7:]
                        else:
                            band_id = file_path[-3:]

                        if is_compact:
                            file_path = os.path.join(self.product_path, file_path + ext)
                        else:
                            file_path = os.path.join(self.product_path, 'GRANULE', self.granule_id, 'IMG_DATA', file_path + ext)
                        log.debug(f'{band_id} {file_path}')
                        self.bands[band_id] = file_path

            if 'SCL_20m' in self.bands.keys():
                self.scene_classif_band = self.bands['SCL_20m']

            # Collection not applicable for Landsat
            self.collection = ' '
            self.radio_coefficient_dic = {}
            # RESCALING GAIN And OFFSET :
            try:
                self.quantification_value = node_value(dom, 'QUANTIFICATION_VALUE')
            except IndexError:
                self.quantification_value = node_value(dom, 'BOA_QUANTIFICATION_VALUE')
            self.dE_S = node_value(dom, 'U')

            nodes = dom.getElementsByTagName('SOLAR_IRRADIANCE')
            self.band_sequence = []
            for cpt, node in enumerate(nodes):
                band_id = node.attributes['bandId']
                self.band_sequence.append(band_id.value)
                solar_irradiance = node.childNodes[0].data
                self.radio_coefficient_dic[str(cpt)] = {"Band_id": str(band_id),
                                                        "Gain": 0.00001, "Offset": 0.0,
                                                        "Solar_irradiance": solar_irradiance
                                                        }
            self.band_sequence = [np.int(rec) + 1 for rec in self.band_sequence]
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
                self.angles_file = None
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
                self.angles_file = None

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
                    else:
                        # old S2 format
                        maskpath = os.path.join(product_path, 'GRANULE', self.granule_id, 'QI_DATA', maskpath)

                    if node.getAttribute('type') == 'MSK_CLOUDS':
                            self.cloudmask = maskpath
                    elif node.getAttribute('type') == 'MSK_NODATA':
                            band = os.path.splitext(maskpath)[0][-3:]
                            self.nodata_mask[band] = maskpath
                    elif node.getAttribute('type') == 'MSK_DETFOO':
                            band = os.path.splitext(maskpath)[0][-3:]
                            self.detfoo_mask[band] = maskpath
                log.debug(self.cloudmask)
                log.debug(self.nodata_mask)
                log.debug(self.detfoo_mask)
            except IndexError:
                sys.exit(' TILE MTL Parsing Issue ')
        else:
            log.error(' -- Tile file not found --')
            self.isValid = False

        # Absolute orbit is contained in the granule ID as _A00000_
        absolute_orbit = re.compile('A\d{6}_').search(self.granule_id)
        self.absolute_orbit = '000000' if absolute_orbit is None else absolute_orbit.group()[1:-1]

    def get_valid_pixel_mask(self, mask_filename, res=20):
        """
        :param res:
        :param mask_filename:
        :return:
        """

        if self.scene_classif_band:
            log.info(f'Generating validity and nodata masks from SCL band')
            log.debug(f'Read SCL: {self.scene_classif_band}')
            scl = S2L_ImageFile(self.scene_classif_band)
            scl_array = scl.array

            valid_px_mask = np.zeros(scl_array.shape, np.uint8)
            # Consider as valid pixels :
            #                VEGETATION et NOT_VEGETATED (valeurs 4 et 5)
            #                UNCLASSIFIED (7) et SNOW (11) -
            valid_px_mask[scl_array == 4] = 1
            valid_px_mask[scl_array == 5] = 1
            valid_px_mask[scl_array == 7] = 1
            valid_px_mask[scl_array == 11] = 1

            mask = scl.duplicate(mask_filename, array=valid_px_mask)
            mask.write(creation_options=['COMPRESS=LZW'])
            self.mask_filename = mask_filename

            # nodata mask
            mask_filename = os.path.join(os.path.dirname(mask_filename), 'nodata_pixel_mask.tif')
            nodata = np.ones(scl_array.shape, np.uint8)
            nodata[scl_array == 0] = 0
            mask = scl.duplicate(mask_filename, array=nodata)
            mask.write(creation_options=['COMPRESS=LZW'])
            self.nodata_mask_filename = mask_filename

            return True

        # L1C case for instance -> No SCL, but NODATA and CLD mask
        else:
            # Nodata Mask
            nodata_ref_band = 'B01'
            band_path = self.bands[nodata_ref_band]
            log.info(f'Generating nodata mask from band {nodata_ref_band}')
            log.debug(f'Read cloud mask: {band_path}')
            image = S2L_ImageFile(band_path)
            array = image.array
            nodata_mask_filename = os.path.join(os.path.dirname(mask_filename), f'nodata_pixel_mask_{nodata_ref_band}.tif')
            nodata = np.ones(array.shape, np.uint8)
            # shall be 0, but due to compression artefact, threshold increased to 4:
            nodata[array <= 4] = 0

            # resize nodata to output res
            shape = (int(nodata.shape[0] * - image.yRes / res), int(nodata.shape[1] * image.xRes / res))
            log.debug(shape)
            nodata = skit_resize(nodata, shape, order=0, preserve_range=True).astype(np.uint8)

            # save to image
            mask = image.duplicate(nodata_mask_filename, array=nodata, res=res)
            mask.write(creation_options=['COMPRESS=LZW'], nodata_value=None)
            self.nodata_mask_filename = nodata_mask_filename

            if self.cloudmask:
                # Cloud mask
                rname, ext = os.path.splitext(self.cloudmask)
                if ext == '.gml':
                    log.info(f'Generating validity mask from cloud mask')
                    log.debug(f'Read cloud mask: {self.cloudmask}')
                    # Check if any cloud feature in gml
                    dom = minidom.parse(self.cloudmask)
                    nClouds = len(dom.getElementsByTagName('eop:MaskFeature'))

                    # rasterize
                    # make byte mask 0/1, LZW compression
                    if nClouds > 0:
                        outputBounds = [self.ULX, self.LRY, self.LRX, self.ULY]
                        if not os.path.exists(os.path.dirname(mask_filename)):
                            os.makedirs(os.path.dirname(mask_filename))
                        gdal.Rasterize(mask_filename, self.cloudmask, outputType=gdal.GDT_Byte,
                                       creationOptions=['COMPRESS=LZW'],
                                       burnValues=0, initValues=1, outputBounds=outputBounds, outputSRS=self.epsg,
                                       xRes=res, yRes=res)

                        # apply nodata to validity mask
                        dataset = gdal.Open(mask_filename, gdal.GA_Update)
                        array = dataset.GetRasterBand(1).ReadAsArray()
                        array[nodata == 0] = 0
                        dataset.GetRasterBand(1).WriteArray(array)
                        dataset = None
                    else:
                        # no cloud mask, copy nodata mask
                        shutil.copy(self.nodata_mask_filename, mask_filename)
                    log.info('Written: {}'.format(mask_filename))
                    self.mask_filename = mask_filename


            return True

        return False

    def get_angle_images(self, DST=None):
        """
        :param DST: OPptional name of the outptu tif containing all angle images
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
        out_file_list = s2_angles.extract_viewing_angle(self.tile_metadata, dst_file, 'Azimuth')

        dst_file = os.path.join(root_dir, 'VZA.tif')
        out_file_list.extend(s2_angles.extract_viewing_angle(self.tile_metadata, dst_file, 'Zenith'))

        # Solar Angles (SUN_AZ, SUN_ZENITH)
        dst_file = os.path.join(root_dir, 'SAA.tif')
        s2_angles.extract_sun_angle(self.tile_metadata, dst_file, 'Azimuth')
        out_file_list.append(dst_file)

        dst_file = os.path.join(root_dir, 'SZA.tif')
        s2_angles.extract_sun_angle(self.tile_metadata, dst_file, 'Zenith')
        out_file_list.append(dst_file)

        out_vrt_file = os.path.join(root_dir, 'tie_points.vrt')
        gdal.BuildVRT(out_vrt_file, out_file_list, separate=True)

        if DST is not None:
            out_tif_file = DST
        else:
            out_tif_file = os.path.join(root_dir, 'tie_points.tif')
        gdal.Translate(out_tif_file, out_vrt_file, format="GTiff")

        self.angles_file = out_vrt_file
        log.info('SAT_AZ , SAT_ZENITH, SUN_AZ, SUN_ZENITH ')
        log.info('UNIT = DEGREES (scale: x100) :')
        log.info('             ' + out_tif_file)
        self.angles_file = out_tif_file

    @staticmethod
    def can_read(product_name):
        name = os.path.basename(product_name)
        S2L_structure_check = 'L2F_' in name and os.path.isdir(os.path.join(product_name, 'GRANULE'))
        return name.startswith('S2') or (name.startswith('L2F') and '_S2' in name) or S2L_structure_check
