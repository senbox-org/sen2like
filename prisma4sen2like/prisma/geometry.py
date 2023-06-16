# -*- coding: utf-8 -*-
# Copyright (c) 2023 ESA.
#
# This file is part of Prisma4sen2like.
# See https://github.com/senbox-org/sen2like/prisma4sen2like for further info.
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
"""Geometry module to reframe and reproject into MGRS UTM"""
import logging
import os
from dataclasses import asdict, dataclass

from osgeo import gdal
from sen2like.grids import MGRSGeoInfo

logger = logging.getLogger()


@dataclass
class LatLong:
    lat: float
    lon: float


@dataclass
class VrtRasterBand:
    band_number: int
    datatype: str
    band: int
    srcfile: str
    xsize: int
    ysize: int


VRT_RASTER_BAND_TEMPLATE = """
    <VRTRasterBand band="{band_number}" dataType="{datatype}">
        <SimpleSource>
            <SourceFilename relativeToVRT="1">{srcfile}</SourceFilename>
            <SourceBand>{band}</SourceBand>
            <SourceProperties RasterXSize="{xsize}" RasterYSize="{ysize}" DataType="{datatype}"/>
            <SrcRect xOff="0" yOff="0" xSize="{xsize}" ySize="{ysize}"/>
            <DstRect xOff="0" yOff="0" xSize="{xsize}" ySize="{ysize}"/>
        </SimpleSource>
    </VRTRasterBand>"""


VRT_TEMPLATE = """
<VRTDataset RasterXSize="{xsize}" RasterYSize="{ysize}">
    <SRS>EPSG:4326</SRS>
    <BlockXSize>256</BlockXSize> <!-- (GDAL >= 3.7) see https://gdal.org/drivers/raster/vrt.html#creation-options -->
    <BlockYSize>256</BlockYSize> <!-- (GDAL >= 3.7) see https://gdal.org/drivers/raster/vrt.html#creation-options -->
    {vrt_raster_band_list}
    <metadata domain="GEOLOCATION">
        <mdi key="GEOREFERENCING_CONVENTION">CENTER_PIXEL</mdi>
        <mdi key="X_DATASET">{lonfile}</mdi>
        <mdi key="X_BAND">1</mdi>
        <mdi key="Y_DATASET">{latfile}</mdi>
        <mdi key="Y_BAND">1</mdi>
        <mdi key="Z_DATASET">{altfile}</mdi>
        <mdi key="Z_BAND">1</mdi>
        <mdi key="LINE_STEP">1</mdi>
        <mdi key="PIXEL_STEP">1</mdi>
        <mdi key="PIXEL_OFFSET">0</mdi>
        <mdi key="LINE_OFFSET">0</mdi>
    </metadata>
</VRTDataset>"""


def ortho_rectify(
    prod_lat: str,
    prod_lon: str,
    prod_alt: str,
    sources: list[VrtRasterBand],
    shape: (int, int),
    dest_file: str,
    dest_res: float,
    tile_info: MGRSGeoInfo,
    dst_nodata: int = 0,
    is_mask: bool = False,
):
    """Project and reframe source band rasters in MGRS tile.

    Args:
        prod_lat (str): latitude grid file
        prod_lon (str): longitude grid file
        prod_alt (str): altitude grid file
        sources (list[VrtRasterBand]): source band params
        shape (int, int): shape of the input
        dest_file (str): destination file
        dest_res (float): destination pixel resolution
        tile_info (MGRSGeoInfo): destination MGRS tile definition.
        dst_nodata (int, optional): no data value to fill output if needed. Defaults to 0.
        is_mask (bool, optional): if set to true (mask), nearest interpolation is preferred than bicubic. Defaults to False.
    """

    logger.info("Orthorectification of product band.")

    ysize, xsize = shape

    file_parts = os.path.splitext(dest_file)

    # vrt creation
    vrt_file = dest_file.replace(file_parts[1], ".vrt")

    vrt_raster_band_list = ""
    for vrt_src in sources:
        vrt_raster_band_list += VRT_RASTER_BAND_TEMPLATE.format(**asdict(vrt_src))

    vrt_content = VRT_TEMPLATE.format(
        xsize=xsize,
        ysize=ysize,
        vrt_raster_band_list=vrt_raster_band_list,
        altfile=prod_alt,
        latfile=prod_lat,
        lonfile=prod_lon,
    )

    logger.debug(vrt_content)
    with open(vrt_file, "w") as fid:
        fid.write(vrt_content)

    # warp
    resample_alg = "near" if is_mask else "bilinear"
    # resampleAlg = "bilinear"

    logger.info(
        "Reframe to MRGS tile %s with EPSG %s with resample %s", tile_info.tile_id, tile_info.epsg, resample_alg
    )

    options = gdal.WarpOptions(
        # options=f"-s_srs EPSG:4326 -t_srs EPSG:{tile_info.epsg} -tr {dest_res} {dest_res} -te {tile_info.geometry.bounds[0]} {tile_info.geometry.bounds[1]} {tile_info.geometry.bounds[2]} {tile_info.geometry.bounds[3]} -r {resample_alg}",  # -ovr NONE",# -dstnodata {dst_nodata} ",#-r {resampleAlg}",
        resampleAlg=resample_alg,
        creationOptions=["COMPRESS=LZW"],
        srcSRS="EPSG:4326",
        dstSRS="EPSG:" + tile_info.epsg,
        xRes=dest_res,
        yRes=dest_res,
        # dstNodata=dst_nodata,
        outputBounds=tile_info.geometry.bounds,
        # overviewLevel="NONE"
    )

    gdal.Warp(dest_file, vrt_file, options=options)

    # Read final image
    # data = io.imread(output_name, cv2.IMREAD_GRAYSCALE)
    # return data, output_name
    src_ds = gdal.Open(dest_file)
    # src_ds = gdal.Open("/tmp/prisma_dev/1680773663593/classi_mask_ortho_jeudi.jp2")
    data = src_ds.GetRasterBand(1)
    data_array = data.ReadAsArray()
    logger.info(f"NB cloudy px: {len(data_array[data_array == 1])}")
    print(data_array[data_array >= 1])
    # data = src_ds.GetRasterBand(2)
    # data_array = data.ReadAsArray()
    # logger.info(f"NB snowy px: {len(data_array[data_array == 1])}")


def reframe_band_file(prod_lat, prod_lon, prod_alt, vrt_param, output_res, output_file, tile_info):
    file_parts = os.path.splitext(output_file)
    # vrt creation
    vrt_file = output_file.replace(file_parts[1], ".vrt")

    vrt_content = VRT_TEMPLATE.format(
        xsize=1000,
        ysize=1000,
        vrt_raster_band_list=VRT_RASTER_BAND_TEMPLATE.format(**asdict(vrt_param)),
        altfile=prod_alt,
        latfile=prod_lat,
        lonfile=prod_lon,
    )

    logger.debug(vrt_content)
    with open(vrt_file, "w") as fid:
        fid.write(vrt_content)

    options = gdal.WarpOptions(
        # options=f"-s_srs EPSG:4326 -t_srs EPSG:{tile_info.epsg} -tr {output_res} {output_res} -te {tile_info.geometry.bounds[0]} {tile_info.geometry.bounds[1]} {tile_info.geometry.bounds[2]} {tile_info.geometry.bounds[3]}",# -ot UInt16",  # -ovr NONE",# -dstnodata {dst_nodata} ",#-r {resampleAlg}",
        resampleAlg="bilinear",
        creationOptions=["COMPRESS=LZW"],
        srcSRS="EPSG:4326",
        dstSRS="EPSG:" + tile_info.epsg,
        xRes=output_res,
        yRes=output_res,
        dstNodata="nan",
        outputBounds=tile_info.geometry.bounds,
        # overviewLevel="NONE"
    )

    gdal.Warp(output_file, vrt_file, options=options)
