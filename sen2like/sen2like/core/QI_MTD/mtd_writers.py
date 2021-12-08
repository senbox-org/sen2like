#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2020

import datetime as dt
import logging
import math
import os
import re

import gdal
import numpy as np
from shapely.wkt import loads

from core.QI_MTD.generic_writer import MtdWriter, chg_elm_with_tag, change_elm, copy_children, create_child, \
    copy_elements, search_db, rm_elm_with_tag, find_element_by_path
from core.QI_MTD.mtd import metadata
from core.S2L_config import config

log = logging.getLogger('Sen2Like')


class MTD_writer_S2(MtdWriter):

    IMAGE_FORMAT = {
        'COG': 'GEOTIFF',
        'GTIFF': 'GEOTIFF',
        'JPEG2000': 'JPEG2000',
    }

    def __init__(self, backbone_path: str, init_MTD_path: str, H_F='H', outfile: str = None):
        super().__init__(backbone_path, init_MTD_path, H_F)
        self.outfile = outfile

    def manual_replaces(self, product):

        # GENERAL_INFO
        # ------------
        elements_to_copy = ['./General_Info/Product_Info/Datatake',
                            './General_Info/Product_Info/PRODUCT_START_TIME',
                            './General_Info/Product_Info/PRODUCT_STOP_TIME',
                            './General_Info/Product_Info/Query_Options',
                            ]
        copy_elements(elements_to_copy, self.root_in, self.root_out, self.root_bb)

        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_URI',
                   new_value=metadata.mtd.get('product_{}_name'.format(self.H_F)))
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PROCESSING_LEVEL',
                   new_value='Level-2{}'.format(self.H_F))
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_TYPE',
                   new_value='S2MSI2{}'.format(self.H_F))

        pdgs = config.get('PDGS', '9999')
        PDGS = '.'.join([pdgs[:len(pdgs) // 2], pdgs[len(pdgs) // 2:]])
        AC = self.root_in.findall('.//ARCHIVING_CENTRE')
        if AC:
            metadata.mtd['S2_AC'] = AC[0].text
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PROCESSING_BASELINE', new_value=PDGS)
        generation_time = dt.datetime.strftime(metadata.mtd.get('product_creation_date'), '%Y-%m-%dT%H:%M:%S.%f')[
                          :-3] + 'Z'  # -3 to keep only 3 decimals
        change_elm(self.root_out, rpath='./General_Info/Product_Info/GENERATION_TIME', new_value=generation_time)

        self.remove_children('./General_Info/Product_Info/Product_Organisation/Granule_List/Granule')
        for band_path in sorted(set(metadata.mtd.get('bands_path_{}'.format(self.H_F)))):
            adjusted_path = os.path.splitext(re.sub(r'^.*?GRANULE', 'GRANULE', band_path))[0]
            create_child(self.root_out, rpath='./General_Info/Product_Info/Product_Organisation/Granule_List/Granule',
                         tag='IMAGE_FILE', text=adjusted_path)
        grnl_id = \
            find_element_by_path(self.root_in, './General_Info/Product_Info/Product_Organisation/Granule_List/Granule')
        if grnl_id:
            change_elm(self.root_out, rpath='./General_Info/Product_Info/Product_Organisation/Granule_List/Granule',
                       new_value=generate_S2_tile_id(product, self.H_F, metadata.mtd['S2_AC']),
                       attr_to_change='granuleIdentifier')
            change_elm(self.root_out, rpath='./General_Info/Product_Info/Product_Organisation/Granule_List/Granule',
                       new_value=self.IMAGE_FORMAT[config.get('output_format')], attr_to_change='imageFormat')
        else:
            pass  # Fixme

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
        tilecode = product.mtl.mgrs
        if tilecode.startswith('T'):
            tilecode = tilecode[1:]
        footprint = search_db(tilecode, search='MGRS_REF')
        # adding back first element, to get a complete polygon
        fp = footprint.split(' ')
        footprint = ' '.join(fp + [fp[0], fp[1]])
        chg_elm_with_tag(self.root_out, tag='EXT_POS_LIST', new_value=footprint)
        copy_elements(['./Geometric_Info/Coordinate_Reference_System'], self.root_in, self.root_out, self.root_bb)

        # Auxiliary_Data_Info
        # -------------------
        self.remove_children('./Auxiliary_Data_Info/GIPP_List')
        copy_children(self.root_in, './Auxiliary_Data_Info/GIPP_List',
                      self.root_out, './Auxiliary_Data_Info/GIPP_List')
        config_fn = os.path.splitext(os.path.basename(config.parser.config_file))[0]
        create_child(self.root_out, './Auxiliary_Data_Info/GIPP_List', tag="GIPP_FILENAME", text=config_fn,
                     attribs={"version": pdgs, "type": "GIP_S2LIKE"})

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
        gri_elems = self.root_in.findall('.//GRI_FILENAME')
        for gri_elm in gri_elems:
            create_child(self.root_out, './Auxiliary_Data_Info/GRI_List', tag="GRI_FILENAME", text=gri_elm.text)

        # Quality_Indicators_Info
        # -----------------------
        copy_elements(['./Quality_Indicators_Info'], self.root_in, self.root_out, self.root_bb)


class MTD_writer_LS8(MtdWriter):

    IMAGE_FORMAT = {
        'COG': 'GEOTIFF',
        'GTIFF': 'GEOTIFF',
        'JPEG2000': 'JPEG2000',
    }

    def __init__(self, backbone_path: str, H_F='H', outfile: str = None):
        super().__init__(backbone_path, init_MTD_path=None, H_F=H_F)
        self.outfile = outfile

    def manual_replaces(self, product):

        # GENERAL_INFO
        # ------------
        acqdate = dt.datetime.strftime(product.acqdate, '%Y-%m-%dT%H:%M:%S.%fZ')
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_START_TIME', new_value=acqdate)
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_STOP_TIME', new_value=acqdate)

        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_URI',
                   new_value=metadata.mtd.get('product_{}_name'.format(self.H_F)))
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PROCESSING_LEVEL',
                   new_value='Level-2{}'.format(self.H_F))
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PRODUCT_TYPE',
                   new_value=f'{product.sensor}OLI2{self.H_F}')

        pdgs = config.get('PDGS', '9999')
        PDGS = '.'.join([pdgs[:len(pdgs) // 2], pdgs[len(pdgs) // 2:]])
        change_elm(self.root_out, rpath='./General_Info/Product_Info/PROCESSING_BASELINE', new_value=PDGS)
        generation_time = dt.datetime.strftime(metadata.mtd.get('product_creation_date'), '%Y-%m-%dT%H:%M:%S.%f')[
                          :-3] + 'Z'  # -3 to keep only 3 decimals
        change_elm(self.root_out, rpath='./General_Info/Product_Info/GENERATION_TIME', new_value=generation_time)

        change_elm(self.root_out, rpath='./General_Info/Product_Info/Datatake/SPACECRAFT_NAME',
                   new_value=product.mtl.mission)

        change_elm(self.root_out, rpath='./General_Info/Product_Info/Datatake/DATATAKE_SENSING_START',
                   new_value=acqdate)
        change_elm(self.root_out, rpath='./General_Info/Product_Info/Datatake/SENSING_ORBIT_NUMBER',
                   new_value=config.get('relative_orbit'))

        self.remove_children('./General_Info/Product_Info/Product_Organisation/Granule_List/Granule')
        for band_path in sorted(set(metadata.mtd.get('bands_path_{}'.format(self.H_F)))):
            adjusted_path = os.path.splitext(re.sub(r'^.*?GRANULE', 'GRANULE', band_path))[0]
            create_child(self.root_out, rpath='./General_Info/Product_Info/Product_Organisation/Granule_List/Granule',
                         tag='IMAGE_FILE', text=adjusted_path)

        tile_id = generate_LS8_tile_id(product, self.H_F)
        change_elm(self.root_out, rpath='./General_Info/Product_Info/Product_Organisation/Granule_List/Granule',
                   new_value=tile_id, attr_to_change='granuleIdentifier')
        change_elm(self.root_out, rpath='./General_Info/Product_Info/Product_Organisation/Granule_List/Granule',
                   new_value=self.IMAGE_FORMAT[config.get('output_format')], attr_to_change='imageFormat')

        if not config.getboolean('doSbaf'):
            # FIXME : get product image characteristics from origin sensor (LS8 here),
            #         copying from another template fro example
            pass
        U = distance_variation_corr(product.acqdate)
        change_elm(self.root_out, rpath='./General_Info/Product_Image_Characteristics/Reflectance_Conversion/U',
                   new_value=str(U))

        # Geometric_info
        # ---------------
        tilecode = product.mtl.mgrs
        if tilecode.startswith('T'):
            tilecode = tilecode[1:]
        footprint = search_db(tilecode, search='MGRS_REF')
        # adding back first element, to get a complete polygon
        fp = footprint.split(' ')
        footprint = ' '.join(fp + [fp[0], fp[1]])
        chg_elm_with_tag(self.root_out, tag='EXT_POS_LIST', new_value=footprint)

        # Auxiliary_Data_Info
        # -------------------
        self.remove_children('./Auxiliary_Data_Info/GIPP_List', exceptions=['Input_Product_Info'])

        config_fn = os.path.splitext(os.path.basename(config.parser.config_file))[0]
        create_child(self.root_out, './Auxiliary_Data_Info/GIPP_List', tag="GIPP_FILENAME", text=config_fn,
                     attribs={"version": pdgs, "type": "GIP_S2LIKE"})

        # Quality_Indicators_Info
        # -----------------------
        self.remove_children('./Quality_Indicators_Info', exceptions=['Input_Product_Info', 'Cloud_Coverage_Assessment'])
        change_elm(self.root_out, './Quality_Indicators_Info/Input_Product_Info', attr_to_change='type',
                   new_value=product.mtl.mission)
        change_elm(self.root_out, './Quality_Indicators_Info/Input_Product_Info',
                   new_value=product.mtl.landsat_scene_id)
        change_elm(self.root_out, './Quality_Indicators_Info/Cloud_Coverage_Assessment',
                   new_value=product.mtl.cloud_cover)


class MTD_tile_writer_S2(MtdWriter):
    def __init__(self, backbone_path: str, init_MTD_path: str, H_F='H', outfile: str = None):
        super().__init__(backbone_path, init_MTD_path, H_F)
        self.outfile = outfile

    def manual_replaces(self, product):

        # GENERAL_INFO
        # ------------
        copy_elements(['./General_Info/TILE_ID',
                       './General_Info/DATASTRIP_ID',
                       './General_Info/DOWNLINK_PRIORITY',
                       './General_Info/SENSING_TIME',
                       './General_Info/Archiving_Info'],
                      self.root_in, self.root_out, self.root_bb)

        if product.mtl.data_type == 'Level-1C' or 'L1' in product.mtl.data_type:
            l1c_tile_id = find_element_by_path(self.root_in, './General_Info/TILE_ID')[0].text
            l2a_tile_id = "NONE"
        else:
            try:
                l1c_tile_id = find_element_by_path(self.root_in, './General_Info/L1C_TILE_ID')[0].text
            except IndexError:
                l1c_tile_id = None
            try:
                l2a_tile_id = find_element_by_path(self.root_in, './General_Info/TILE_ID')[0].text
            except IndexError:
                l2a_tile_id = None

        tilecode = product.mtl.mgrs
        AC = self.root_in.findall('.//ARCHIVING_CENTRE')
        if AC:
            metadata.mtd['S2_AC'] = AC[0].text

        tile_id = generate_S2_tile_id(product, self.H_F, metadata.mtd['S2_AC'])

        if l1c_tile_id is None:
            self.remove_children('./General_Info/L1_TILE_ID')
        else:
            change_elm(self.root_out, './General_Info/L1_TILE_ID', new_value=l1c_tile_id)
        if l2a_tile_id is None:
            self.remove_children('./General_Info/L2A_TILE_ID')
        else:
            change_elm(self.root_out, './General_Info/L2A_TILE_ID', new_value=l2a_tile_id)
        change_elm(self.root_out, './General_Info/TILE_ID', new_value=tile_id)

        # Geometric_info
        # ---------------
        copy_elements(['./Geometric_Info/Tile_Geocoding/HORIZONTAL_CS_NAME',
                       './Geometric_Info/Tile_Geocoding/HORIZONTAL_CS_CODE'],
                      self.root_in, self.root_out, self.root_bb)

        g = loads(search_db(tilecode, search='UTM_WKT'))
        xMin = int(g.bounds[0])
        yMin = int(g.bounds[1])
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/Geoposition/ULX', new_value=str(xMin))
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/Geoposition/ULY', new_value=str(yMin))

        self.remove_children('./Geometric_Info/Tile_Angles', tag='Viewing_Incidence_Angles_Grids')
        angles_path = os.path.join('GRANULE', metadata.mtd.get('granule_{}_name'.format(self.H_F)), 'QI_DATA',
                                   metadata.mtd.get('ang_filename'))
        change_elm(self.root_out, './Geometric_Info/Tile_Angles/Acquisition_Angles_Filename', new_value=angles_path)

        rm_elm_with_tag(self.root_out, tag='Sun_Angles_Grid')
        rm_elm_with_tag(self.root_out, tag='Viewing_Incidence_Angle_Grid')

        copy_elements(['./Geometric_Info/Tile_Angles/Mean_Sun_Angle'], self.root_in, self.root_out, self.root_bb)
        copy_elements(['./Geometric_Info/Tile_Angles/Mean_Viewing_Incidence_Angle_List'], self.root_in, self.root_out,
                      self.root_bb)

        # Quality indicators info
        # -----------------------
        self.remove_children('./Quality_Indicators_Info/Image_Content_QI')
        copy_children(self.root_in, './Quality_Indicators_Info/Image_Content_QI',
                      self.root_out, './Quality_Indicators_Info/Image_Content_QI')

        # Replace masks with all existing
        self.remove_children('./Quality_Indicators_Info/Pixel_Level_QI', tag='MASK_FILENAME')

        for mask in metadata.mtd.get('masks_{}'.format(self.H_F)):
            create_child(self.root_out, './Quality_Indicators_Info/Pixel_Level_QI', tag=mask.get('tag'),
                         text=mask.get('text'),
                         attribs=mask.get('attribs'))

        try:
            msk_text = find_element_by_path(self.root_in, './Quality_Indicators_Info/Pixel_Level_QI/MASK_FILENAME')[
                0].text
            ini_grn_name = re.search(r'GRANULE/(.*?)/QI_DATA', msk_text).group(1)
        except IndexError:
            ini_grn_name = None
        if ini_grn_name is not None:
            elems = find_element_by_path(self.root_out, './Quality_Indicators_Info/Pixel_Level_QI/MASK_FILENAME')
            for elem in elems:
                elem.text = elem.text.replace(ini_grn_name, metadata.mtd.get('granule_{}_name'.format(self.H_F)))

        rm_elm_with_tag(self.root_out, tag='PVI_FILENAME')
        rm_elm_with_tag(self.root_out, tag='QL_B12118A_FILENAME')
        rm_elm_with_tag(self.root_out, tag='QL_B432_FILENAME')
        # Get all created quicklooks (including PVI)
        for ql in metadata.mtd.get('quicklooks_{}'.format(self.H_F)):
            ql_path = re.search(r'GRANULE(.*)', ql).group()
            band_rootName = metadata.mtd.get(f'band_rootName_{self.H_F}')
            ql_name = re.search(r'{}_(.*)'.format(band_rootName), ql_path).group(1)
            create_child(self.root_out, './Quality_Indicators_Info',
                         tag="{}_FILENAME".format(os.path.splitext(ql_name)[0]), text=ql_path)


class MTD_tile_writer_LS8(MtdWriter):
    def __init__(self, backbone_path: str, H_F='H', outfile: str = None):
        super().__init__(backbone_path, init_MTD_path=None, H_F=H_F)
        self.outfile = outfile

    def manual_replaces(self, product):

        # GENERAL_INFO
        # ------------
        if product.mtl.data_type == 'Level-1C' or 'L1' in product.mtl.data_type:
            l1__tile_id = product.mtl.landsat_scene_id
            l2a_tile_id = "NONE"
        else:
            l1__tile_id = "NONE"
            l2a_tile_id = product.mtl.landsat_scene_id

        tile_id = generate_LS8_tile_id(product, self.H_F)
        change_elm(self.root_out, './General_Info/L1_TILE_ID', new_value=l1__tile_id)
        change_elm(self.root_out, './General_Info/L2A_TILE_ID', new_value=l2a_tile_id)
        change_elm(self.root_out, './General_Info/TILE_ID', new_value=tile_id)

        acqdate = dt.datetime.strftime(product.acqdate, '%Y-%m-%dT%H:%M:%S.%fZ')
        change_elm(self.root_out, './General_Info/SENSING_TIME', new_value=acqdate)

        AC = metadata.hardcoded_values.get('L8_archiving_center')
        change_elm(self.root_out, './General_Info/Archiving_Info/ARCHIVING_CENTRE', new_value=AC)
        change_elm(self.root_out, './General_Info/Archiving_Info/ARCHIVING_TIME',
                   new_value=metadata.hardcoded_values.get('L8_archiving_time'))

        # Geometric_info
        # ---------------
        tilecode = product.mtl.mgrs
        cs_name = '{} / {} {}N'.format(product.mtl.datum, product.mtl.map_projection, product.mtl.utm_zone)
        cs_code = 'EPSG:{}'.format(search_db(tilecode, search='EPSG'))
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/HORIZONTAL_CS_NAME', new_value=cs_name)
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/HORIZONTAL_CS_CODE', new_value=cs_code)

        g = loads(search_db(tilecode, search='UTM_WKT'))
        xMin = int(g.bounds[0])
        yMin = int(g.bounds[1])
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/Geoposition/ULX', new_value=str(xMin))
        change_elm(self.root_out, './Geometric_Info/Tile_Geocoding/Geoposition/ULY', new_value=str(yMin))

        angles_path = os.path.join('GRANULE', metadata.mtd.get('granule_{}_name'.format(self.H_F)), 'QI_DATA',
                                   metadata.mtd.get('ang_filename'))
        change_elm(self.root_out, './Geometric_Info/Tile_Angles/Acquisition_Angles_Filename', new_value=angles_path)

        rm_elm_with_tag(self.root_out, tag='Sun_Angles_Grid')
        rm_elm_with_tag(self.root_out, tag='Viewing_Incidence_Angle_Grid')

        src_ds = gdal.Open(product.mtl.angles_file)
        VAA = np.mean(src_ds.GetRasterBand(1).ReadAsArray().astype(np.float32) / 100.0)
        VZA = np.mean(src_ds.GetRasterBand(2).ReadAsArray().astype(np.float32) / 100.0)
        SAA = np.mean(src_ds.GetRasterBand(3).ReadAsArray().astype(np.float32) / 100.0)
        SZA = np.mean(src_ds.GetRasterBand(4).ReadAsArray().astype(np.float32) / 100.0)

        change_elm(self.root_out, './Geometric_Info/Tile_Angles/Mean_Sun_Angle/ZENITH_ANGLE', new_value=str(SZA))
        change_elm(self.root_out, './Geometric_Info/Tile_Angles/Mean_Sun_Angle/AZIMUTH_ANGLE', new_value=str(SAA))
        change_elm(self.root_out,
                   './Geometric_Info/Tile_Angles/Mean_Viewing_Incidence_Angle_List/Mean_Viewing_Incidence_Angle/ZENITH_ANGLE',
                   new_value=str(VZA))
        change_elm(self.root_out,
                   './Geometric_Info/Tile_Angles/Mean_Viewing_Incidence_Angle_List/Mean_Viewing_Incidence_Angle/AZIMUTH_ANGLE',
                   new_value=str(VAA))

        # Quality indicators info
        # -----------------------
        self.remove_children('./Quality_Indicators_Info/Image_Content_QI')
        create_child(self.root_out, './Quality_Indicators_Info/Image_Content_QI',
                tag="CLOUDY_PIXEL_PERCENTAGE", text=product.mtl.cloud_cover)

        # Replace masks with all existing
        self.remove_children('./Quality_Indicators_Info/Pixel_Level_QI', tag='MASK_FILENAME')

        for mask in metadata.mtd.get('masks_{}'.format(self.H_F)):
            create_child(self.root_out, './Quality_Indicators_Info/Pixel_Level_QI', tag=mask.get('tag'),
                         text=mask.get('text'),
                         attribs=mask.get('attribs'))

        rm_elm_with_tag(self.root_out, tag='PVI_FILENAME')
        rm_elm_with_tag(self.root_out, tag='QL_B12118A_FILENAME')
        rm_elm_with_tag(self.root_out, tag='QL_B432_FILENAME')
        # Get all created quicklooks (including PVI)
        for ql in metadata.mtd.get('quicklooks_{}'.format(self.H_F)):
            ql_path = re.search(r'GRANULE(.*)', ql).group()
            band_rootName = metadata.mtd.get(f'band_rootName_{self.H_F}')
            ql_name = re.search(r'{}_(.*)'.format(band_rootName), ql_path).group(1)
            create_child(self.root_out, './Quality_Indicators_Info',
                         tag="{}_FILENAME".format(os.path.splitext(ql_name)[0]), text=ql_path)


def to_JulianDay(date):
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
    t = date.toordinal() + year1 + fraction
    return t


def distance_variation_corr(date):
    """
    From https://sentinel.esa.int/web/sentinel/technical-guides/sentinel-2-msi/level-1c/algorithm
    :param date:
    :return:
    """
    t0 = 2433283
    t = to_JulianDay(date)
    dt = 1 / math.pow((1 - 0.01672 * math.cos(0.0172 * (t - t0 - 2))), 2)
    return dt


def generate_LS8_tile_id(pd, H_F):
    tilecode = pd.mtl.mgrs
    if not tilecode.startswith('T'):
        tilecode = f"T{tilecode}"
    pdgs = metadata.hardcoded_values.get('PDGS', '9999')
    PDGS = '.'.join([pdgs[:len(pdgs) // 2], pdgs[len(pdgs) // 2:]])
    AC = metadata.hardcoded_values.get('L8_archiving_center')
    AO = metadata.hardcoded_values.get('L8_absolute_orbit')
    acqdate = dt.datetime.strftime(pd.acqdate, '%Y%m%dT%H%M%S')
    tile_id = '_'.join(
        [pd.sensor_name, 'OPER', 'OLI', 'L2{}'.format(H_F), AC, acqdate, 'A{}'.format(AO),
         tilecode, 'N{}'.format(PDGS)])

    return tile_id


def generate_S2_tile_id(product, H_F, AC):
    tilecode = product.mtl.mgrs
    if not tilecode.startswith('T'):
        tilecode = f"T{tilecode}"
    pdgs = metadata.hardcoded_values.get('PDGS', '9999')
    PDGS = '.'.join([pdgs[:len(pdgs) // 2], pdgs[len(pdgs) // 2:]])
    acqdate = dt.datetime.strftime(product.acqdate, '%Y%m%dT%H%M%S')
    if AC.endswith('_'):
        AC = AC[:-1]
    tile_id = '_'.join([product.sensor_name, 'OPER', 'MSI', 'L2{}'.format(H_F), AC, acqdate,
                        'A{}'.format(config.get('absolute_orbit')), tilecode, 'N{}'.format(PDGS)])
    return tile_id
