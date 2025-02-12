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

import logging
import re
import sys
import xml.parsers as pars
from typing import NamedTuple
from xml.dom import minidom

import numpy as np
from osgeo import gdal, osr

log = logging.getLogger("Sen2Like")

re_band = re.compile(r'B0?(\d{1,2})$')


def get_angles_band_index(band: str) -> int|None:
    """
    Convert the band index into the S2 angles indexing convention
    B1->B8 : indices from 0 to 7
    B8A : index 8
    B9 -> B12 : indices from 9 to 12
    """
    if band == "B8A":
        return 8
    band_index = re_band.match(band)
    if band_index:
        band_index = int(band_index.group(1))
        if 0 < band_index < 9:
            return band_index - 1
        return band_index
    return None


def from_values_list_to_array(selected_node):
    col_step = selected_node.getElementsByTagName('COL_STEP')[0].childNodes[0].data
    row_step = selected_node.getElementsByTagName('ROW_STEP')[0].childNodes[0].data

    values_list = selected_node.getElementsByTagName('Values_List')[0].getElementsByTagName('VALUES')

    # x_size, y_size , size of the matrix
    x_size = len(values_list[0].childNodes[0].data.split())
    y_size = len(values_list)

    # Create np array of  size (x_size,y_size) for sun zenith values :
    arr = np.empty([x_size, y_size], float)
    for j in range(0, y_size, 1):
        a = np.asarray(values_list[j].childNodes[0].data.split(), float)
        arr[j] = a

    return x_size, y_size, col_step, row_step, arr


def reduce_angle_matrix(x_size, y_size, a_dict):
    # As S2 viewing zenith / azimuth matrix given for different detector
    # As overlapping detector, build  matrix including averaged values where
    # several values from different detectors exist
    # Input :
    #       - a : dictionary (detector, band_ud and array values)
    #       - x_size / y_size size of the matrix
    # Output :
    # ~      - the reduce matrix
    M = np.zeros([x_size, y_size], float)
    #   print('input M :' + str(M[2][6]))
    CPT = np.zeros([x_size, y_size], int)
    for k, u in list(a_dict.items()):
        for i in range(0, x_size, 1):
            for j in range(0, x_size, 1):
                A = u["Values"]
                if not np.isnan(A[i][j]):
                    M[i][j] = A[i][j] + M[i][j]
                    CPT[i][j] += 1
    #                if i == 2 and j == 6 :
    #                    print str(M[i][j])+' '+str(A[i][j])

    N = np.divide(M, CPT)

    # keep it commented for history
    # before, the division had a where clause CPT!=0
    # but it was not working well so we remove it 
    # and then the N matrix have the good final result
    #N[N == 0] = np.nan

    return N


def _get_geo_info(xml_tl_file: str) -> tuple:
    """extract ULX, ULY, SRS as WKT and DOM of MTD_TL XML file

    Args:
        xml_tl_file (str): MTD_TL file path

    Returns:
        tuple: dom, ulx, uly, wkt
    """

    try:
        dom = minidom.parse(xml_tl_file)
    except pars.expat.ExpatError:
        sys.exit(' Invalid XML TL File')

    # Load xmlf file and retrieve projection parameter :
    node_name = 'Tile_Geocoding'  # Level-1C / Level-2A ?
    geocoding_node = dom.getElementsByTagName(node_name)[0]
    epsg_code = geocoding_node.getElementsByTagName('HORIZONTAL_CS_CODE')[0].childNodes[0].data
    geo_position = geocoding_node.getElementsByTagName('Geoposition')[0]
    ulx = geo_position.getElementsByTagName('ULX')[0].childNodes[0].data
    uly = geo_position.getElementsByTagName('ULY')[0].childNodes[0].data

    # Call gdalsrs info to generate wkt for the projection
    # Replaced by gdal python api:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(epsg_code.replace('EPSG:', '')))
    wkt = srs.ExportToWkt()

    return dom, ulx, uly, wkt

class _GeoInfo(NamedTuple):
    x_res: int
    y_res: int
    x_pixel_size: int
    y_pixel_size: int
    ul_x: int
    ul_y: int
    wkt: str


def _save_angle_as_img(dst_file, arr, geo_info: _GeoInfo, description: str):

    # gdal parameter :
    nodata_value = -32768

    # scale between -180 and 180 deg.
    if arr.max() > 180.0:
        arr[arr > 180] = arr[arr > 180] - 360

    target_ds = gdal.GetDriverByName('GTiff').Create(
        dst_file,
        geo_info.x_res,
        geo_info.y_res,
        1,
        gdal.GDT_Int16
    )
    target_ds.SetGeoTransform(
        (geo_info.ul_x, geo_info.x_pixel_size, 0, geo_info.ul_y, 0, -geo_info.y_pixel_size)
    )
    band = target_ds.GetRasterBand(1)
    band.SetNoDataValue(nodata_value)
    band.SetDescription(description)

    arr = np.nan_to_num(arr, nan=nodata_value)
    arr[(arr != nodata_value)] = arr[(arr != nodata_value)] * 100
    # FIXME: keep no data value for nodata when
    # nodata pixel carefully handled by other processing
    # For now, set nodata to 0 to avoid artefact close to swath border
    # mitigation to be in line with 4.4.x
    # see also sentinel2_maja having same trick
    arr[(arr == nodata_value)] = 0

    band.WriteArray(arr.astype(np.int16), 0, 0)  # int16 with scale factor 100
    target_ds.SetProjection(geo_info.wkt)
    band = None
    target_ds = None


def extract_sun_angle(src_file: str, dst_file: str, angle_type: str):
    """Read the 'MTD_TL.xml' file, and read information in <Sun_Angles_Grid>.
    Depending on angle_type value, {'Zenith' , 'Azimuth'}, 
    it selects  <Values_List> in the corresponding xml section
    save image file in dst_file - do not apply resampling

    Args:
        src_file (str): MTD_TL.xml file path
        dst_file (str): destination angle image file path
        angle_type (str): angle type to extract
    """
    dom, ulx, uly, wkt = _get_geo_info(src_file)

    # Load xml file and extract parameter for sun zenith :
    node_name = 'Sun_Angles_Grid'  # Level-1C / Level-2A ?
    sun_angle_node = dom.getElementsByTagName(node_name)[0]

    selected_node = sun_angle_node.getElementsByTagName(angle_type)[0]

    x_size, y_size, col_step, row_step, arr = from_values_list_to_array(selected_node)

    log.debug(' Save in %s', dst_file)

    geo_info = _GeoInfo(
        int(x_size),
        int(y_size),
        int(col_step),
        int(row_step),
        int(ulx),
        int(uly),
        wkt
    )
    _save_angle_as_img(dst_file, arr, geo_info, f'Solar_{angle_type}')


def extract_viewing_angle(src_file: str, dst_file: str, angle_type: str) -> list[str]:
    """Access to MTL and extract viewing angles depending on the angle type for each band

    Args:
        src_file (str): MTD_TL.xml file path
        dst_file (str): destination angle image file path, will be updated for each band
        angle_type (str): angle type to extract

    Returns:
        list[str]: list of file path that have been generated
    """
    out_list = []  # Store the path of all outputs
    log.debug('extact viewing angle')

    dom, ulx, uly, wkt = _get_geo_info(src_file)

    # Load xml file and extract parameter for sun zenith :
    node_name = 'Viewing_Incidence_Angles_Grids'  # Level-1C / Level-2A ?
    viewing_angle_node = dom.getElementsByTagName(node_name)
    
    v_dico = {}

    for cpt in range(0, len(viewing_angle_node), 1):
        band_id = viewing_angle_node[cpt].attributes["bandId"].value
        detector = viewing_angle_node[cpt].attributes["detectorId"].value
        selected_node = viewing_angle_node[cpt].getElementsByTagName(angle_type)[0]
        [x_size, y_size, col_step, row_step, arr] = from_values_list_to_array(selected_node)
        v_dico['_'.join([band_id, detector])] = {"Band_id": str(band_id),
                                  "Detector": str(detector),
                                  "Values": arr}

    for rec in range(0, 13, 1):
        dic = v_dico.copy()
        a = {k: v for k, v in dic.items() if v["Band_id"] == str(rec)}
        arr = reduce_angle_matrix(x_size, y_size, a)

        # Decoding of band number :
        # CF : https: // earth.esa.int / web / sentinel / user - guides / sentinel - 2 - msi / resolutions / radiometric
        # Band 8A <=> Band 9 in the mtl

        dst_file_bd = dst_file.replace('.tif', '_band_' + str(rec + 1) + '.tif')
        out_list.append(dst_file_bd)
        log.debug(' Save in %s',dst_file_bd)

        geo_info = _GeoInfo(
            int(x_size),
            int(y_size),
            int(col_step),
            int(row_step),
            int(ulx),
            int(uly),
            wkt
        )
        _save_angle_as_img(dst_file_bd, arr, geo_info, f'Viewing_{angle_type}_band_{str(rec + 1)}')

        # clean
        arr = None
        a = None

    return out_list
