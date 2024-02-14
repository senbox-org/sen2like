#! /usr/bin/env python
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

import abc
import logging
import math
import os
import re
from datetime import datetime

import numpy as np
from osgeo import gdal
from shapely.wkt import loads

import version
from core.products.product import S2L_Product
from core.QI_MTD.generic_writer import (
    XmlWriter,
    change_elm,
    chg_elm_with_tag,
    copy_children,
    copy_elements,
    create_child,
    find_element_by_path,
    rm_elm_with_tag,
    search_db,
)
from core.S2L_config import config

log = logging.getLogger('Sen2Like')

# XPATH constant
L2A_TILE_ID_PATH = './General_Info/L2A_TILE_ID'
L1_TILE_ID_PATH  = './General_Info/L1_TILE_ID'
TILE_ID_PATH     = './General_Info/TILE_ID'
GRANULE_PATH     = './General_Info/Product_Info/Product_Organisation/Granule_List/Granule'
GIPP_LIST_PATH   = './Auxiliary_Data_Info/GIPP_List'
QUALITY_INDICATOR_PATH = './Quality_Indicators_Info'
IMAGE_CONTENT_QI_PATH  = './Quality_Indicators_Info/Image_Content_QI'
PIXEL_LEVEL_QI_PATH    = './Quality_Indicators_Info/Pixel_Level_QI'

ISO_DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

_template_dict = {
    "H": {
        "S2": {
            "product": "xml_backbones/MTD_MSIL2H_S2.xml",
            "tile": "xml_backbones/MTD_TL_L2H_S2.xml"
        },
        "Prisma": {
            "product": "xml_backbones/MTD_MSIL2H_S2.xml",
            "tile": "xml_backbones/MTD_TL_L2H_S2.xml"
        },
        "Landsat": {
            "product": "xml_backbones/MTD_OLIL2H_L8.xml",
            "tile": "xml_backbones/MTD_TL_L2H_L8.xml"
        }
    },
    "F": {
        "S2": {
            "product": "xml_backbones/MTD_MSIL2F_S2.xml",
            "tile": "xml_backbones/MTD_TL_L2F_S2.xml"
        },
        "Prisma": {
            "product": "xml_backbones/MTD_MSIL2F_S2.xml",
            "tile": "xml_backbones/MTD_TL_L2F_S2.xml"
        },
        "Landsat": {
            "product": "xml_backbones/MTD_OLIL2F_L8.xml",
            "tile": "xml_backbones/MTD_TL_L2F_L8.xml"
        }
    }
}

class S2LProductMtdWriter(XmlWriter, abc.ABC):
    """Abstract Product level MTD writer
    """

    IMAGE_FORMAT = {
        'COG': 'GEOTIFF',
        'GTIFF': 'GEOTIFF',
        'JPEG2000': 'JPEG2000',
    }

    def __init__(self, sensor: str, input_xml_path: str, H_F='H', outfile: str = None):
        super().__init__(_template_dict[H_F][sensor]["product"], input_xml_path, H_F=H_F)
        self.outfile = outfile

    def manual_replaces(self, product: S2L_Product):
        """Do commons replacements in template ('self.root_out'),
        then call 'self._specific_replaces' to finish to fill the final document ('self.root_out')
        Set :
        - ./General_Info/Product_Info/PRODUCT_URI
        - ./General_Info/Product_Info/PROCESSING_LEVEL
        - ./General_Info/Product_Info/PROCESSING_BASELINE
        - ./General_Info/Product_Info/GENERATION_TIME
        - ./General_Info/Product_Info/Product_Organisation/Granule_List/Granule
        - ./General_Info/Product_Image_Characteristics/BOA_ADD_OFFSET_VALUES_LIST
        - .Geometric_Info/Product_Footprint/Product_Footprint/Global_Footprint/EXT_POS_LIST>

        Args:
            product (S2L_Product): concerned product
        """

        metadata = product.metadata
        
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_URI',
                   new_value=metadata.mtd.get(f'product_{self.H_F}_name'))
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PROCESSING_LEVEL',
                   new_value=f'Level-2{self.H_F}')
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PROCESSING_BASELINE',
                   new_value=version.baseline_dotted)

        generation_time = datetime.strftime(metadata.mtd.get('product_creation_date'), '%Y-%m-%dT%H:%M:%S.%f')[
            :-3] + 'Z'  # -3 to keep only 3 decimals
        change_elm(self.root_out, rpath='./General_Info/Product_Info/GENERATION_TIME', new_value=generation_time)

        self.remove_children(GRANULE_PATH)
        for band_path in sorted(set(metadata.mtd.get(f'bands_path_{self.H_F}'))):
            adjusted_path = os.path.splitext(re.sub(r'^.*?GRANULE', 'GRANULE', band_path))[0]
            create_child(self.root_out, rpath=GRANULE_PATH, tag='IMAGE_FILE_2HF', text=adjusted_path)

        tile_id = self._generate_tile_id(product)
        change_elm(self.root_out, rpath=GRANULE_PATH, new_value=tile_id, attr_to_change='granuleIdentifier')
        change_elm(self.root_out, rpath=GRANULE_PATH,
                   new_value=self.IMAGE_FORMAT[config.get('output_format')], attr_to_change='imageFormat')

        # Add BOA_ADD_OFFSET for each L2 bands
        offset = int(config.get('offset'))
        boa_offset_list_elem = './General_Info/Product_Image_Characteristics/BOA_ADD_OFFSET_VALUES_LIST'
        for band_id in range(0, 13):
            create_child(self.root_out, rpath=boa_offset_list_elem, tag='BOA_ADD_OFFSET',
                         text=str(-offset), attribs={"band_id": str(band_id)})

        #  Geometric_info
        # ---------------
        tile_code = product.mgrs
        if tile_code.startswith('T'):
            tile_code = tile_code[1:]

        footprint = search_db(tile_code, search='MGRS_REF')

        # adding back first element, to get a complete polygon
        fp = footprint.split(' ')
        footprint = ' '.join(fp + [fp[0], fp[1]])
        chg_elm_with_tag(self.root_out, tag='EXT_POS_LIST', new_value=footprint)

        self._specific_replaces(product)

    @abc.abstractmethod
    def _generate_tile_id(self, product: S2L_Product):
        """Get product tile id, mission dependant

        Args:
            product (S2L_Product): Product for which tile is created
        """
        # deliberately empty

    @abc.abstractmethod
    def _specific_replaces(self, product: S2L_Product):
        """Mission specific MTD changes to apply to the product level MTD template to have final MTD file
        Call at the end of 'manual_replaces'

        Args:
            product (S2L_Product): Product for which product level MTD is processed
        """
        # deliberately empty


class Sentinel2ToS2LProductMtdWriter(S2LProductMtdWriter):
    """Writer of S2H/F Product MTD file for product created from S2 product
    """

    def _generate_tile_id(self, product: S2L_Product):
        return _generate_sentinel2_tile_id(product, self.H_F, product.metadata.mtd['S2_AC'])

    def _specific_replaces(self, product: S2L_Product):

        # GENERAL_INFO
        # ------------
        elements_to_copy = ['./General_Info/Product_Info/Datatake',
                            './General_Info/Product_Info/PRODUCT_START_TIME',
                            './General_Info/Product_Info/PRODUCT_STOP_TIME',
                            './General_Info/Product_Info/Query_Options',
                            ]
        copy_elements(elements_to_copy, self.root_in, self.root_out, self.root_bb)

        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_TYPE',
                   new_value=f'S2MSI2{self.H_F}')

        archive_center = self.root_in.findall('.//ARCHIVING_CENTRE')
        if archive_center:
            product.metadata.mtd['S2_AC'] = archive_center[0].text

        # If Sbaf is done, we keep the values inside the backbone (S2A values)
        if not config.getboolean('doSbaf'):
            # copy_elements(['./General_Info/Product_Image_Characteristics/Special_Values',
            #                './General_Info/Product_Image_Characteristics/Image_Display_Order',
            #                './General_Info/Product_Image_Characteristics/Reflectance_Conversion',
            #                './General_Info/Product_Image_Characteristics/Spectral_Information_List'],
            #               self.root_in, self.root_out, self.root_bb)
            pass
            # FIXME : get product image characteristics from origin sensor (S2 here),
            #         copying from another template for example (see commented lines above)
        copy_elements(['./General_Info/Product_Image_Characteristics/Reflectance_Conversion/U'], self.root_in,
                      self.root_out)

        #  Geometric_info
        # ---------------
        copy_elements(['./Geometric_Info/Coordinate_Reference_System'], self.root_in, self.root_out, self.root_bb)

        # Auxiliary_Data_Info
        # -------------------
        self.remove_children(GIPP_LIST_PATH)
        copy_children(self.root_in, GIPP_LIST_PATH,
                      self.root_out, GIPP_LIST_PATH)
        config_fn = os.path.splitext(os.path.basename(config.parser.config_file))[0]
        create_child(self.root_out, GIPP_LIST_PATH, tag="GIPP_FILENAME", text=config_fn,
                     attribs={"version": version.baseline, "type": "GIP_S2LIKE"})

        for tag in ['PRODUCTION_DEM_TYPE',
                    'IERS_BULLETIN_FILENAME',
                    'ECMWF_DATA_REF',
                    'SNOW_CLIMATOLOGY_MAP',
                    'ESACCI_WaterBodies_Map',
                    'ESACCI_LandCover_Map',
                    'ESACCI_SnowCondition_Map_Dir']:
            elem = find_element_by_path(self.root_in, './Auxiliary_Data_Info/' + tag)

            if len(elem) != 0:
                new_value = elem[0].text
            else:
                new_value = "NONE"

            change_elm(self.root_out, rpath='./Auxiliary_Data_Info/' + tag, new_value=new_value)

        # Fill GRI_List
        for gri_elm in self.root_in.findall('.//GRI_FILENAME'):
            create_child(self.root_out, './Auxiliary_Data_Info/GRI_List', tag="GRI_FILENAME", text=gri_elm.text)

        # Quality_Indicators_Info
        # -----------------------
        copy_elements([QUALITY_INDICATOR_PATH], self.root_in, self.root_out, self.root_bb)


class LandsatToS2LProductMtdWriter(S2LProductMtdWriter):
    """Writer of S2H/F Product MTD file for product created from LS product
    """

    # Redefine constructor to DELIBERATELY Force
    # - "Landsat" for sensor
    # - "None" for input_xml_path
    # And have a similar constructor contract
    def __init__(self, sensor: str, input_xml_path: str, H_F='H', outfile: str = None):
        super().__init__("Landsat", None, H_F, outfile)

    def _generate_tile_id(self, product: S2L_Product):
        return _generate_landsat8_tile_id(product, self.H_F)

    def _specific_replaces(self, product: S2L_Product):

        # GENERAL_INFO
        # ------------
        acq_date = datetime.strftime(product.acqdate, ISO_DATE_TIME_FORMAT)
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_START_TIME', new_value=acq_date)
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_STOP_TIME', new_value=acq_date)
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_TYPE',
                   new_value=f'{product.sensor}OLI2{self.H_F}')
        change_elm(self.root_out, rpath='./General_Info/Product_Info/Datatake/SPACECRAFT_NAME',
                   new_value=product.mtl.mission)
        change_elm(self.root_out, rpath='./General_Info/Product_Info/Datatake/DATATAKE_SENSING_START',
                   new_value=acq_date)
        change_elm(self.root_out, rpath='./General_Info/Product_Info/Datatake/SENSING_ORBIT_NUMBER',
                   new_value=product.mtl.relative_orbit)

        if not config.getboolean('doSbaf'):
            # FIXME : get product image characteristics from origin sensor (LS8 here),
            #         copying from another template fro example
            pass

        U = _distance_variation_corr(product.acqdate)
        change_elm(self.root_out, rpath='./General_Info/Product_Image_Characteristics/Reflectance_Conversion/U',
                   new_value=str(U))

        # Auxiliary_Data_Info
        # -------------------
        self.remove_children(GIPP_LIST_PATH)

        config_fn = os.path.splitext(os.path.basename(config.parser.config_file))[0]
        create_child(self.root_out, GIPP_LIST_PATH, tag="GIPP_FILENAME", text=config_fn,
                     attribs={"version": version.baseline, "type": "GIP_S2LIKE"})

        # Quality_Indicators_Info
        # -----------------------
        self.remove_children(QUALITY_INDICATOR_PATH, exceptions=['Cloud_Coverage_Assessment'])
        change_elm(self.root_out, './Quality_Indicators_Info/Cloud_Coverage_Assessment',
                   new_value=product.mtl.cloud_cover)


_product_mtl_writer_class_dict = {
    "S2": Sentinel2ToS2LProductMtdWriter,
    "Prisma": Sentinel2ToS2LProductMtdWriter,
    "L8": LandsatToS2LProductMtdWriter,
    "L9": LandsatToS2LProductMtdWriter,
}


def get_product_mtl_writer_class(sensor: str) -> S2LProductMtdWriter:
    """Return concrete S2LProductMtdWriter from a sensor

    Args:
        sensor (str): sensor from which retrieve concrete S2LProductMtdWriter

    Returns:
        S2LProductMtdWriter: product mtd writer corresponding to the sensor
    """
    return _product_mtl_writer_class_dict[sensor]


class S2LTileMtdWriter(XmlWriter, abc.ABC):
    """Abstract Tile level MTD writer
    """

    def __init__(self, sensor: str, input_xml_path: str, H_F='H', outfile: str = None):
        super().__init__(_template_dict[H_F][sensor]["tile"], input_xml_path, H_F=H_F)
        self.outfile = outfile

    def manual_replaces(self, product: S2L_Product):

        metadata = product.metadata

        tile = loads(search_db(product.mgrs, search='UTM_WKT'))
        ul_x = int(tile.bounds[0])
        ul_y = int(tile.bounds[3])
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/Geoposition/ULX', new_value=str(ul_x))
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/Geoposition/ULY', new_value=str(ul_y))

        angles_path = os.path.join('GRANULE', metadata.mtd.get(f'granule_{self.H_F}_name'), 'QI_DATA',
                                   metadata.mtd.get('ang_filename'))
        change_elm(self.root_out, './Geometric_Info/Tile_Angles/Acquisition_Angles_Filename', new_value=angles_path)

        rm_elm_with_tag(self.root_out, tag='Sun_Angles_Grid')
        rm_elm_with_tag(self.root_out, tag='Viewing_Incidence_Angle_Grid')

        # Replace masks with all existing
        self.remove_children(PIXEL_LEVEL_QI_PATH, tag='MASK_FILENAME')

        for mask in metadata.mtd.get(f'masks_{self.H_F}'):
            create_child(self.root_out, PIXEL_LEVEL_QI_PATH, tag=mask.get('tag'),
                         text=mask.get('text'),
                         attribs=mask.get('attribs'))

        rm_elm_with_tag(self.root_out, tag='PVI_FILENAME')
        rm_elm_with_tag(self.root_out, tag='QL_B12118A_FILENAME')
        rm_elm_with_tag(self.root_out, tag='QL_B432_FILENAME')

        # Get all created quicklooks (including PVI)
        for ql in metadata.mtd.get(f'quicklooks_{self.H_F}'):
            ql_path = re.search(r'GRANULE(.*)', ql).group()
            band_root_name = metadata.mtd.get(f'band_rootName_{self.H_F}')
            ql_name = re.search(r'{}_(.*)'.format(band_root_name), ql_path).group(1)
            create_child(self.root_out, QUALITY_INDICATOR_PATH,
                         tag=f"{os.path.splitext(ql_name)[0]}_FILENAME", text=ql_path)

        self._specific_replaces(product)

    @abc.abstractmethod
    def _specific_replaces(self, product: S2L_Product):
        """Mission specific MTD changes to apply to the Tile level MTD template to have final MTD file
        Call at the end of 'manual_replaces'

        Args:
            product (S2L_Product): Product for which tile level MTD is processed
        """
        # deliberately empty


class Sentinel2ToS2LTileMtdWriter(S2LTileMtdWriter):
    """Writer of S2H/F Tile MTD file for product created from S2 product
    """

    def _specific_replaces(self, product: S2L_Product):

        metadata = product.metadata

        # GENERAL_INFO
        # ------------
        copy_elements([TILE_ID_PATH,
                       './General_Info/DATASTRIP_ID',
                       './General_Info/DOWNLINK_PRIORITY',
                       './General_Info/SENSING_TIME',
                       './General_Info/Archiving_Info'],
                      self.root_in, self.root_out, self.root_bb)

        if product.mtl.data_type == 'Level-1C' or 'L1' in product.mtl.data_type:
            l1c_tile_id = find_element_by_path(self.root_in, TILE_ID_PATH)[0].text
            l2a_tile_id = "NONE"
        else:
            try:
                l1c_tile_id = find_element_by_path(self.root_in, './General_Info/L1C_TILE_ID')[0].text
            except IndexError:
                l1c_tile_id = None
            try:
                l2a_tile_id = find_element_by_path(self.root_in, TILE_ID_PATH)[0].text
            except IndexError:
                l2a_tile_id = None

        archive_center = self.root_in.findall('.//ARCHIVING_CENTRE')
        if archive_center:
            metadata.mtd['S2_AC'] = archive_center[0].text

        tile_id = _generate_sentinel2_tile_id(product, self.H_F, metadata.mtd['S2_AC'])

        if l1c_tile_id is None:
            self.remove_children(L1_TILE_ID_PATH)
        else:
            change_elm(self.root_out, L1_TILE_ID_PATH, new_value=l1c_tile_id)

        if l2a_tile_id is None:
            self.remove_children(L2A_TILE_ID_PATH)
        else:
            change_elm(self.root_out, L2A_TILE_ID_PATH, new_value=l2a_tile_id)

        change_elm(self.root_out, TILE_ID_PATH, new_value=tile_id)

        # Geometric_info
        # ---------------
        copy_elements(['./Geometric_Info/Tile_Geocoding/HORIZONTAL_CS_NAME',
                       './Geometric_Info/Tile_Geocoding/HORIZONTAL_CS_CODE'],
                      self.root_in, self.root_out, self.root_bb)

        copy_elements(['./Geometric_Info/Tile_Angles/Mean_Sun_Angle'], self.root_in, self.root_out, self.root_bb)
        copy_elements(['./Geometric_Info/Tile_Angles/Mean_Viewing_Incidence_Angle_List'], self.root_in, self.root_out,
                      self.root_bb)

        # Quality indicators info
        # -----------------------
        self.remove_children(IMAGE_CONTENT_QI_PATH)
        copy_children(self.root_in, IMAGE_CONTENT_QI_PATH,
                      self.root_out, IMAGE_CONTENT_QI_PATH)

        try:
            msk_text = find_element_by_path(self.root_in, './Quality_Indicators_Info/Pixel_Level_QI/MASK_FILENAME')[
                0].text
            ini_grn_name = re.search(r'GRANULE/(.*?)/QI_DATA', msk_text).group(1)
        except IndexError:
            ini_grn_name = None
        if ini_grn_name is not None:
            elems = find_element_by_path(self.root_out, './Quality_Indicators_Info/Pixel_Level_QI/MASK_FILENAME')
            for elem in elems:
                elem.text = elem.text.replace(ini_grn_name, metadata.mtd.get(f'granule_{self.H_F}_name'))


class LandsatToS2LTileMtdWriter(S2LTileMtdWriter):
    """Writer of S2H/F Tile MTD file for product created from LS product
    """

    # Redefine constructor to DELIBERATELY Force
    # - "Landsat" for sensor
    # - "None" for input_xml_path
    # And have a similar constructor contract
    def __init__(self, sensor: str, input_xml_path: str, H_F='H', outfile: str = None):
        super().__init__("Landsat", None, H_F, outfile)

    def _specific_replaces(self, product: S2L_Product):

        # GENERAL_INFO
        # ------------
        if product.mtl.data_type == 'Level-1C' or 'L1' in product.mtl.data_type:
            l1__tile_id = product.mtl.landsat_scene_id
            l2a_tile_id = "NONE"
        else:
            l1__tile_id = "NONE"
            l2a_tile_id = product.mtl.landsat_scene_id

        tile_id = _generate_landsat8_tile_id(product, self.H_F)
        change_elm(self.root_out, L1_TILE_ID_PATH, new_value=l1__tile_id)
        change_elm(self.root_out, L2A_TILE_ID_PATH, new_value=l2a_tile_id)
        change_elm(self.root_out, TILE_ID_PATH, new_value=tile_id)

        acq_date = datetime.strftime(product.acqdate, ISO_DATE_TIME_FORMAT)
        change_elm(self.root_out, './General_Info/SENSING_TIME', new_value=acq_date)

        archive_center = product.metadata.hardcoded_values.get('L8_archiving_center')
        change_elm(self.root_out, './General_Info/Archiving_Info/ARCHIVING_CENTRE', new_value=archive_center)
        change_elm(self.root_out, './General_Info/Archiving_Info/ARCHIVING_TIME',
                   new_value=datetime.strftime(product.file_date, ISO_DATE_TIME_FORMAT))

        # Geometric_info
        # ---------------
        cs_name = f'{product.mtl.datum} / {product.mtl.map_projection} {product.mtl.utm_zone}N'
        cs_code = f'EPSG:{search_db(product.mgrs, search="EPSG")}'
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/HORIZONTAL_CS_NAME', new_value=cs_name)
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/HORIZONTAL_CS_CODE', new_value=cs_code)

        src_ds = gdal.Open(product.angles_file)
        viewing_azimuth_angle = np.mean(src_ds.GetRasterBand(1).ReadAsArray().astype(np.float32) / 100.0)
        viewing_zenith_angle = np.mean(src_ds.GetRasterBand(2).ReadAsArray().astype(np.float32) / 100.0)
        azimuth_angle = np.mean(src_ds.GetRasterBand(3).ReadAsArray().astype(np.float32) / 100.0)
        zenith_angle = np.mean(src_ds.GetRasterBand(4).ReadAsArray().astype(np.float32) / 100.0)

        change_elm(self.root_out, './Geometric_Info/Tile_Angles/Mean_Sun_Angle/ZENITH_ANGLE', new_value=str(zenith_angle))
        change_elm(self.root_out, './Geometric_Info/Tile_Angles/Mean_Sun_Angle/AZIMUTH_ANGLE', new_value=str(azimuth_angle))
        change_elm(
            self.root_out,
            './Geometric_Info/Tile_Angles/Mean_Viewing_Incidence_Angle_List/Mean_Viewing_Incidence_Angle/ZENITH_ANGLE',
            new_value=str(viewing_zenith_angle))
        change_elm(
            self.root_out,
            './Geometric_Info/Tile_Angles/Mean_Viewing_Incidence_Angle_List/Mean_Viewing_Incidence_Angle/AZIMUTH_ANGLE',
            new_value=str(viewing_azimuth_angle))

        # Quality indicators info
        # -----------------------
        self.remove_children(IMAGE_CONTENT_QI_PATH)
        create_child(self.root_out, IMAGE_CONTENT_QI_PATH,
                tag="CLOUDY_PIXEL_PERCENTAGE", text=product.mtl.cloud_cover)


_tile_mtl_writer_class_dict = {
    "S2": Sentinel2ToS2LTileMtdWriter,
    "Prisma": Sentinel2ToS2LTileMtdWriter,
    "L8": LandsatToS2LTileMtdWriter,
    "L9": LandsatToS2LTileMtdWriter,
}


def get_tile_mtl_writer_class(sensor: str) -> S2LTileMtdWriter:
    """Return concrete S2LTileMtdWriter from a sensor

    Args:
        sensor (str): sensor from which retrieve concrete S2LTileMtdWriter

    Returns:
        S2LTileMtdWriter: tile mtd writer corresponding to the sensor
    """
    return _tile_mtl_writer_class_dict[sensor]


def _to_julian_day(date):
    """
    Computes Julian day from datetime.datetime date
    :param date:
    :return:
    """
    year1 = 1721424.5
    # Need to compute days fraction because .toordinal only computes floor(days)
    hh = date.hour
    mm = date.minute
    ss = date.second
    ms = date.microsecond
    fraction = hh / 24 + mm / (24 * 60) + ss / (24 * 60 * 60) + ms / (24 * 60 * 60 * 10 ** 6)
    return date.toordinal() + year1 + fraction


def _distance_variation_corr(date):
    """
    From https://sentinel.esa.int/web/sentinel/technical-guides/sentinel-2-msi/level-1c/algorithm
    :param date:
    :return:
    """
    t0 = 2433283
    julian_day = _to_julian_day(date)
    return 1 / math.pow((1 - 0.01672 * math.cos(0.0172 * (julian_day - t0 - 2))), 2)


def _generate_landsat8_tile_id(product: S2L_Product, H_F):
    tile_code = product.mgrs
    if not tile_code.startswith('T'):
        tile_code = f"T{tile_code}"

    archive_center = product.metadata.hardcoded_values.get('L8_archiving_center')
    acq_date = datetime.strftime(product.acqdate, '%Y%m%dT%H%M%S')

    # LS8_OPER_OLI_TL L2H_ZZZ__20171114T102408_A000000_T31TFJ_N04.02
    tile_id = '_'.join(
        [product.sensor_name, 'OPER', 'OLI', 'TL', f'L2{H_F}', archive_center, acq_date, f'A{product.absolute_orbit}', tile_code,
         f'N{version.baseline_dotted}'])

    return tile_id


def _generate_sentinel2_tile_id(product: S2L_Product, H_F, archive_center):

    tile_code = product.mgrs
    if not tile_code.startswith('T'):
        tile_code = f"T{tile_code}"

    acq_date = datetime.strftime(product.acqdate, '%Y%m%dT%H%M%S')

    # S2A_OPER_MSI_TL_L2H_SGS__20171030T104754_A012303_T31TFJ_N04.02
    tile_id = '_'.join(
        [product.sensor_name, 'OPER', 'MSI', 'TL', f'L2{H_F}', archive_center, acq_date, f'A{product.absolute_orbit}',
         tile_code, f'N{version.baseline_dotted}'])

    return tile_id
