# -*- coding: utf-8 -*-
import logging
import re
import sys
import xml.parsers as pars
from typing import Union
from xml.dom import minidom

import numpy as np
from osgeo import gdal, osr

log = logging.getLogger("Sen2Like")

re_band = re.compile(r'B0?(\d{1,2})$')


def get_angles_band_index(band: str) -> Union[int, None]:
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
    arr = np.empty([x_size, y_size], np.float)
    for j in range(0, y_size, 1):
        a = np.asarray(values_list[j].childNodes[0].data.split(), np.float)
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
    M = np.zeros([x_size, y_size], np.float)
    #   print('input M :' + str(M[2][6]))
    CPT = np.zeros([x_size, y_size], np.float)
    for k, u in list(a_dict.items()):
        for i in range(0, x_size, 1):
            for j in range(0, x_size, 1):
                A = u["Values"]
                if A[i][j] == A[i][j]:  # test if value is not nan
                    M[i][j] = A[i][j] + M[i][j]
                    CPT[i][j] += 1
    #                if i == 2 and j == 6 :
    #                    print str(M[i][j])+' '+str(A[i][j])

    N = np.divide(M, CPT, where=(CPT != 0))
    N[N == 0] = np.nan
    return N


def extract_sun_angle(src_file, dst_file, angle_type):
    # Open the 'MTD_TL.xml' file, and read information in     <Sun_Angles_Grid>
    # Depending on angle_type value, {'Zenith' , 'Azimuth'  }
    # select  <Values_List> in  the corresponding xml section
    # save image file in dst_file - do not apply resampling

    xml_tl_file = src_file
    try:
        dom = minidom.parse(xml_tl_file)
    except pars.expat.ExpatError:
        sys.exit(' Invalid XML TL File')

    # gdal parameter :
    NoData_value = -9999

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

    # Load xml file and extract parameter for sun zenith :
    node_name = 'Sun_Angles_Grid'  # Level-1C / Level-2A ?
    sun_angle_node = dom.getElementsByTagName(node_name)[0]

    selected_node = sun_angle_node.getElementsByTagName(angle_type)[0]

    x_size, y_size, col_step, row_step, arr = from_values_list_to_array(selected_node)

    # scale between -180 and 180 deg.
    if arr.max() > 180.0:
        arr[arr > 180] = arr[arr > 180] - 360

    # Create gdal dataset
    x_res = np.int(x_size)
    y_res = np.int(y_size)

    x_pixel_size = np.int(col_step)
    y_pixel_size = np.int(row_step)

    log.debug(' Save in {}'.format(dst_file))
    target_ds = gdal.GetDriverByName('GTiff').Create(dst_file, x_res, y_res, 1, gdal.GDT_Int16)
    target_ds.SetGeoTransform((np.int(ulx), x_pixel_size, 0, np.int(uly), 0, -y_pixel_size))
    band = target_ds.GetRasterBand(1)
    band.SetNoDataValue(NoData_value)
    band.SetDescription('Solar_' + angle_type)
    band.WriteArray((arr * 100).astype(np.int16), 0, 0)  # int16 with scale factor 100
    target_ds.SetProjection(wkt)


def extract_viewing_angle(src_file, dst_file, angle_type):
    # Access to MTL and extract vieing angles depending on the angletype
    # Return the list of files that have been generated, out_list
    out_list = []  # Store the path of all outputs
    log.debug('extact viewing angle')
    xml_tl_file = src_file
    try:
        dom = minidom.parse(xml_tl_file)
    except pars.expat.ExpatError:
        sys.exit(' Invalid XML TL File')

    # gdal parameter :
    NoData_value = -9999

    # Load xmlf file and retrieve projection parameter :
    node_name = 'Tile_Geocoding'  # Level-1C / Level-2A?
    geocoding_node = dom.getElementsByTagName(node_name)[0]
    epsg_code = geocoding_node.getElementsByTagName('HORIZONTAL_CS_CODE')[0].childNodes[0].data
    geo_position = geocoding_node.getElementsByTagName('Geoposition')[0]
    ulx = geo_position.getElementsByTagName('ULX')[0].childNodes[0].data
    uly = geo_position.getElementsByTagName('ULY')[0].childNodes[0].data
    # Call gdalsrs info to generate wkt for the projection :
    # Replaced by gdal python api:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(epsg_code.replace('EPSG:', '')))
    wkt = srs.ExportToWkt()

    # Load xml file and extract parameter for sun zenith :
    node_name = 'Viewing_Incidence_Angles_Grids'  # Level-1C / Level-2A ?
    viewing_angle_node = dom.getElementsByTagName(node_name)
    v_dico = {}
    for cpt in range(0, len(viewing_angle_node), 1):
        band_id = viewing_angle_node[cpt].attributes["bandId"].value
        detector = viewing_angle_node[cpt].attributes["detectorId"].value
        selected_node = viewing_angle_node[cpt].getElementsByTagName(angle_type)[0]
        [x_size, y_size, col_step, row_step, arr] = from_values_list_to_array(selected_node)
        v_dico.update({str(cpt): {"Band_id": str(band_id),
                                  "Detector": str(detector),
                                  "Values": arr}})

    for rec in range(0, 13, 1):
        dic = v_dico.copy()
        a = {k: v for k, v in list(dic.items()) if v["Band_id"] == str(rec)}
        arr = reduce_angle_matrix(x_size, y_size, a)

        # scale between -180 and 180 deg.
        if arr.max() > 180.0:
            arr[arr > 180] = arr[arr > 180] - 360

        # Create gdal dataset
        x_res = np.int(x_size)
        y_res = np.int(y_size)

        x_pixel_size = np.int(col_step)
        y_pixel_size = np.int(row_step)

        # Decoding of band number :
        # CF : https: // earth.esa.int / web / sentinel / user - guides / sentinel - 2 - msi / resolutions / radiometric
        # Band 8A <=> Band 9 in the mtl

        dst_file_bd = dst_file.replace('.tif', '_band_' + str(rec + 1) + '.tif')
        out_list.append(dst_file_bd)
        log.debug(' Save in {}'.format(dst_file_bd))
        target_ds = gdal.GetDriverByName('GTiff').Create(dst_file_bd, x_res, y_res, 1, gdal.GDT_Int16)
        target_ds.SetGeoTransform((np.int(ulx), x_pixel_size, 0, np.int(uly), 0, -y_pixel_size))
        band = target_ds.GetRasterBand(1)
        band.SetNoDataValue(NoData_value)
        band.SetDescription('Viewing_' + angle_type + '_band_' + str(rec + 1))  # This sets the band name!
        target_ds.GetRasterBand(1).WriteArray((arr * 100).astype(np.int16), 0, 0)  # int16 with scale factor 100
        target_ds.SetProjection(wkt)
        band = None
        target_ds = None
        arr = None
        a = None

    return out_list
