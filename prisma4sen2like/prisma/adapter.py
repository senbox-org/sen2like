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
"""Reader Adapter module

The purpose of the adapter is to adapt any input product to the sen2like product interface

This design aims to show how sen2like could be refactored to improve its design.
ProductAdapter should be a abstract class. 
Each concrete ProductAdapter is dedicated to / use a specific product reader.

"""
import datetime
import logging
import os
from dataclasses import dataclass

import numpy as np
from geometry import VrtRasterBand, ortho_rectify, reframe_band_file
from mgrs_util import get_mgrs_geo_info, get_tile
from numpy.typing import NDArray
from PIL import Image
from prisma_product import PrismaProduct
from sen2like.image_file import S2L_ImageFile

logger = logging.getLogger(__name__)

# NOMINAL S2 IMAGE RES :
# B02 B03 B04 B08 TCI = 10
# B05 B06 B07 B8A B11 B12 = 20
# B01 B09 B10 = 60

# PRISMA RESOLUTION
# NOMINAL S2 IMAGE RES :
# B02 B03 B04 B05 B06 B07 B08 B8A B11 B12 TCI = 30
# B01 B09 B10 = 60

IMAGES_RES = {
    "B01": 60,
    # "B01": 30,
    "B02": 30,
    "B03": 30,
    "B04": 30,
    "B05": 30,
    "B06": 30,
    "B07": 30,
    "B08": 30,
    "B8A": 30,
    # "B09": 60,
    "B09": 30,
    # "B10": 60,
    "B10": 30,
    "B11": 30,
    "B12": 30,
    "TCI": 30,
}

RASTER_BAND_INDEX = {
    "B01": 1,
    "B02": 2,
    "B03": 3,
    "B04": 4,
    "B05": 5,
    "B06": 6,
    "B07": 7,
    "B08": 8,
    "B8A": 9,
    "B09": 10,
    "B10": 11,
    "B11": 12,
    "B12": 13,
}

BAND_IMAGE_TYPE = "uint16"
TCI_IMAGE_TYPE = "uint8"


def interpolate_gps_position(v):
    u = np.unique(v)
    indice = []
    for rec in u[1:]:
        i = np.where(v == rec)[0][0]
        indice.append(i)
    x_0 = np.linspace(1, v.shape[0], v.shape[0])
    # linear interpolation :
    x = np.array(indice)
    y = u[1:]
    [p, o] = np.polyfit(x, y, deg=1)

    return p * x_0 + o


@dataclass
class MeanAngle:
    """Geometric_Info/Tile_Angles/Mean_Sun_Angle info"""

    zenith_angle: float
    azimuth_angle: float


@dataclass
class AngleGrid:
    """
    Geometric_Info/Tile_Angles/Sun_Angles_Grid info/Zenith|Azimuth/Values_List
    Geometric_Info/Tile_Angles/Viewing_Incidence_Angles_Grids/Zenith|Azimuth/Values_List
    """

    zenith_angle: NDArray
    azimuth_angle: NDArray


@dataclass(unsafe_hash=True)
class MaskFileDef:
    type_attr: str
    band_id_attr: str  # 0 to 12 (0 -> B01, 1 -> B02, ... 8 -> B8A, 9 -> B09), if None, B00
    value: str


class ProductAdapter:
    """Input product reader class Adapter (mainly for for Sen2LikeProduct)"""

    def __init__(self, product: PrismaProduct, work_dir: str, classi_res: float):
        self._product = product
        self._mask_files = {}
        self._wd = work_dir
        self._classi_res = classi_res
        self._classi_file = None
        self._lat_lon_alt_grid = None
        # possible masks for prisma
        self._mask_function_lookup = {MaskFileDef("MSK_CLASSI", None, "MSK_CLASSI_B00.tif"): self._get_classi_mask_file}
        # band file path indexed by band name
        self._band_files = {}
        self._viewing_zenith_angle = None
        self._viewing_azimuth_angle = None
        self._tile_info = None

    @property
    def spacecraft(self):
        return "Prisma"

    @property
    def archiving_center(self):
        return self._product.processing_centre.ljust(4, "_")

    @property
    def processing_center(self):
        return self._product.processing_centre.ljust(4, "_")

    @property
    def processing_time(self):
        return self._product.processing_date.as_datetime

    @property
    def reception_station(self):
        return self._product.acquisition_station.ljust(4, "_")

    @property
    def datatake_sensing_time(self) -> datetime:
        return self._product.scene_center_date

    @property
    def tile_sensing_time(self) -> datetime:
        return self._product.scene_center_date

    @property
    def tile_number(self) -> str:
        # get tile from scene center using mgrs
        _scene_center = self._product.scene_center_coordinates
        return get_tile(self._product.scene_center_coordinates)

    @property
    def product_start_time(self) -> datetime:
        return self._product.product_start_time.as_datetime

    @property
    def product_stop_time(self) -> datetime:
        return self._product.product_stop_time.as_datetime

    @property
    def datatake_sensing_start(self) -> datetime:
        return self._product.product_start_time.as_datetime

    @property
    def datastrip_sensing_start(self) -> datetime:
        return self._product.product_start_time.as_datetime

    @property
    def datastrip_sensing_stop(self) -> datetime:
        return self._product.product_stop_time.as_datetime

    @property
    def granule_sensing_start(self) -> datetime:
        return self._product.product_start_time.as_datetime

    @property
    def granule_sensing_stop(self) -> datetime:
        return self._product.product_stop_time.as_datetime

    @property
    def sensing_orbit_number(self) -> int:
        # TODO
        return 99

    @property
    def absolute_orbit_number(self) -> int:
        # TODO
        return 28524

    @property
    def sensing_orbit_direction(self) -> str:
        # TODO
        return "DESCENDING"

    @property
    def platform(self) -> str:
        return "S2P"

    @property
    def shot_level(self) -> str:
        return "L1C"

    @property
    def processing_level(self) -> str:
        return "Level-1C"

    @property
    def station(self) -> str:
        # TODO
        # NOTE : maybe rename, what station is it ? processing, receiving ?
        return "XXXX"

    @property
    def sun_earth_correction(self) -> float:
        return self._product.sun_earth_correction

    # ##############################################
    # GRANULE/TILE Geometric_Info

    # TODO Tile_Geocoding
    #   <HORIZONTAL_CS_NAME>WGS84 / UTM zone 12N</HORIZONTAL_CS_NAME>
    #   <HORIZONTAL_CS_CODE>EPSG:32612</HORIZONTAL_CS_CODE>

    # Tile_Angles

    @property
    def mean_sun_angle(self) -> MeanAngle:
        return MeanAngle(self._product.sun_zenith_angle, self._product.sun_azimuth_angle)

    @property
    def mean_viewing_angle(self) -> MeanAngle:
        return MeanAngle(self._viewing_zenith_angle, self._viewing_azimuth_angle)

    @property
    def sun_angle_grid(self) -> AngleGrid:
        """Geometric_Info/Tile_Angles/Sun_Angles_Grid info"""
        return AngleGrid(
            np.full((23, 23), self._product.sun_zenith_angle), np.full((23, 23), self._product.sun_azimuth_angle)
        )

    # ##############################################
    # GRANULE/TILE Quality_Indicators_Info
    @property
    def cloudy_pixel_percentage(self) -> float:
        return self._product.cloudy_pixel_percentage

    @property
    def degraded_msi_data_percentage(self) -> float:
        # TODO
        return 0.0

    @property
    def snow_pixel_percentage(self) -> float:
        # TODO
        return 0.0

    @property
    def pvi_filename(self) -> str:
        # TODO
        return ""

    @property
    def tile_info(self):
        if not self._tile_info:
            self._tile_info = get_mgrs_geo_info(self.tile_number)
        return self._tile_info

    def get_band_file(self, band_name: str) -> str:
        # check if already generated
        band_file_path = self._band_files.get(band_name, None)
        if band_file_path:
            return band_file_path

        logger.info("Generate image file for band %s", band_name)

        # Reproject and reframe

        lat, lon, alt = self._lat_lon_alt_grid

        vrt_param = VrtRasterBand(
            1,
            "float32",
            RASTER_BAND_INDEX.get(band_name),
            self._product.raster,
            1000,
            1000,
        )

        out_file = os.path.join(self._wd, band_name + "_reframe.tif")
        reframe_band_file(lat, lon, alt, vrt_param, IMAGES_RES.get(band_name), out_file, self.tile_info)

        # apply gain + offset
        image = S2L_ImageFile(out_file)
        # load it
        image.read()
        out_file = os.path.join(self._wd, band_name + ".tif")
        image.duplicate(out_file).write(nodata_value=0)

        logger.info("Image file for band %s generated in %s", band_name, out_file)
        self._band_files[band_name] = out_file
        return out_file

    def get_mask_file(self, mask_file_def: MaskFileDef) -> str | None:
        """Get mask file path from the given definition

        Args:
            mask_file_def (MaskFileDef): mask definition

        Returns:
            str|None: mask file path. None if not exists
        """
        func = self._mask_function_lookup.get(mask_file_def, None)
        if func:
            return func()
        return None

    def _extract_mask(self, grid, values: list[int], output_file_path: str) -> NDArray:
        # need to rotate original grid counterclockwise
        mask = np.rot90(grid, k=-1)
        dest_mask = np.zeros(mask.shape).astype("uint8")
        # set pixel with given values to 1
        for val in values:
            dest_mask[mask == val] = 1
            logger.debug(dest_mask[dest_mask == val])

        logger.debug("NB maked px %s", len(dest_mask[dest_mask >= 1]))

        logger.debug("maked px %s", dest_mask[dest_mask >= 1])

        image = Image.fromarray(dest_mask)
        image.save(output_file_path)
        return dest_mask

    @property
    def _lat_lon_grid_files(self):
        if self._lat_lon_alt_grid:
            return self._lat_lon_alt_grid

        logger.info("Extract Lat Lon grids")

        lat_lon_grids = self._product.lat_lon_grids
        # need to rotate original grid conterclockwize
        lat_grid = np.rot90(lat_lon_grids[0], k=-1)
        lon_grid = np.rot90(lat_lon_grids[1], k=-1)

        # lat grid file
        prod_lat = os.path.join(self._wd, "lat.tif")
        image = Image.fromarray(lat_grid)
        image.save(prod_lat)

        # lon grid file
        prod_lon = os.path.join(self._wd, "lon.tif")
        image = Image.fromarray(lon_grid)
        image.save(prod_lon)

        # alt grid file
        alt_grid = np.zeros(lat_grid.shape)
        prod_alt = os.path.join(self._wd, "alt.tif")
        image = Image.fromarray(alt_grid)
        image.save(prod_alt)

        self._lat_lon_alt_grid = (prod_lat, prod_lon, prod_alt)

        return self._lat_lon_alt_grid

    def _get_classi_mask_file(self):
        if self._classi_file:
            return self._classi_file

        self._classi_file = os.path.join(self._wd, "classi_mask_ortho.tif")
        logger.info("Extract MSK_CLASSI in %s", self._classi_file)

        # cloud mask
        cloud_mask_file = os.path.join(self._wd, "cloud_mask.tif")
        logger.info("Extract cloud px to %s", cloud_mask_file)
        # keep only pixel with 1 (cloud)
        cloud_mask = self._extract_mask(self._product.cloud_mask_grid, [1], cloud_mask_file)

        # snow mask
        snow_mask_file = os.path.join(self._wd, "snow_mask.tif")
        logger.info("Extract snow px to %s", snow_mask_file)
        # keep only pixel with 1 (snow)
        snow_mask = self._extract_mask(self._product.land_mask_grid, [1], snow_mask_file)

        # dummy cirrus mask, needed for MASK_CLASSI
        cirrus_mask = np.zeros(cloud_mask.shape).astype("uint8")
        cirrus_mask_file = os.path.join(self._wd, "cirrus_mask.tif")
        image = Image.fromarray(cirrus_mask)
        image.save(cirrus_mask_file)

        # create VRT input band params
        cloud_raster_param = VrtRasterBand(1, "Byte", 1, cloud_mask_file, cloud_mask.shape[1], cloud_mask.shape[0])
        snow_raster_param = VrtRasterBand(2, "Byte", 1, snow_mask_file, snow_mask.shape[1], snow_mask.shape[0])
        cirrus_raster_param = VrtRasterBand(3, "Byte", 1, cirrus_mask_file, cirrus_mask.shape[1], cirrus_mask.shape[0])

        lat_lon_grid_files = self._lat_lon_grid_files

        ortho_rectify(
            lat_lon_grid_files[0],
            lat_lon_grid_files[1],
            lat_lon_grid_files[2],
            [cloud_raster_param, snow_raster_param, cirrus_raster_param],
            cloud_mask.shape,
            self._classi_file,
            self._classi_res,
            self.tile_info,
            is_mask=True,
        )

        logger.info("Extract MSK_CLASSI finished")
        return self._classi_file

    def _compute_orbital_model(self):
        # self.product = h5py.File(f_name, 'r')
        # Pourquoi 3 x 1000 (x , y, z) x 1000  ?, une valeur chaque ligne
        # C = np.array(self.product['KDP_AUX/LOS_Vnir'])
        # plt.plot(C[:,0])
        # plt.plot(C[:,1])
        # plt.plot(C[:,2])

        # list(self._product.product["Info/Ancillary"])
        u = np.array(self._product.product["Info/Ancillary/StarTracker2/Time_day_ss"])

        # list(self._product.product["Info/Ancillary/GyroData"])

        # list(self._product.product["Info/Ancillary/PVSdata/Wgs84_pos_x"])
        # list(self._product.product["Info/Ancillary/PVSdata/Wgs84_pos_y"])
        # list(self._product.product["Info/Ancillary/PVSdata/Wgs84_pos_z"])

        """'
        GPS     Data, taken     from Anc1Hz message     Float.GPS     Position[m]     x - component
        of     the     S / C     position     expressed     in the     WGS84     ECEF     reference
        frame.     Range: -10 ^ 7 + 10 ^ 7     IEEE     float     32     standard
        Bit[31] = sign,     Bit[30:23] = exp ,     Bit[22:0] = mantissa
        """

        pos_x = interpolate_gps_position(np.array(list(self._product.product["Info/Ancillary/PVSdata/Wgs84_pos_x"])))
        pos_y = interpolate_gps_position(np.array(list(self._product.product["Info/Ancillary/PVSdata/Wgs84_pos_y"])))
        pos_z = interpolate_gps_position(np.array(list(self._product.product["Info/Ancillary/PVSdata/Wgs84_pos_z"])))

        lat_lon_grids = self._product.lat_lon_grids

        lat = np.pi / 180.0 * np.rot90(lat_lon_grids[0], k=-1)
        lon = np.pi / 180.0 * np.rot90(lat_lon_grids[1], k=-1)

        shape = lat.shape

        # a : major radius of the earth, 6378100 m
        a = 6378100
        # e : eccentricity,  0.017
        e = 0.017

        N = np.divide(a, np.power(1 - (e * e * np.sin(lat) * np.sin(lat)), 0.5))

        # Poistion vector of imaging point
        p = np.array([N * np.cos(lat) * np.cos(lon), N * np.cos(lat) * np.sin(lon), (1 - e * e) * N * np.sin(lat)])

        # n: top vertical line (normal)
        n = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])

        # xb: position of the satellite (ECEF), clip to be within image frame
        # xb = np.array([pos_x[60:-60], pos_y[60:-60], pos_z[60:-60]])
        # lxb = (np.tile(xb, shape[1])).reshape(3, shape[0], shape[1])
        M_pos_x = np.rot90((np.tile(pos_x[60:-60], 1000).reshape(1000, 1000)), -1)
        M_pos_y = np.rot90((np.tile(pos_y[60:-60], 1000).reshape(1000, 1000)), -1)
        M_pos_z = np.rot90((np.tile(pos_z[60:-60], 1000).reshape(1000, 1000)), -1)
        lxb = np.array([M_pos_x, M_pos_y, M_pos_z])

        # d: directionnal vector from imaging point :
        d = lxb - p

        # compute zenith
        res = np.sum(d * n, 0)
        res2 = np.power(np.sum(d * d, 0), 0.5)
        r = res / res2
        zenith = (np.arccos(res / res2)) * 180 / np.pi
        # zenith -> off nadir

        # compute azimuth:
        # consider directionnal vector (d)

        # l: unit vector in x axis direction in ECR
        l = np.array([-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)])
        # m: unit vector in y axis direction in ECR
        m = np.array([-np.sin(lon), np.cos(lon), np.zeros([shape[0], shape[1]])])

        x = np.sum(l * d, 0)
        y = np.sum(m * d, 0)
        # azimuth = np.arctan(y / x) * 180.0 / np.pi
        azimuth = np.degrees(np.arctan(y / x))

        azimuth[azimuth < 0] = azimuth[azimuth < 0] + 360

        self._viewing_zenith_angle = np.mean(zenith)
        self._viewing_azimuth_angle = np.mean(azimuth)

    @property
    def viewing_angle_grid(self) -> AngleGrid:
        # _viewing_zenith_angle and _viewing_azimuth_angle
        # are computed by _compute_orbital_model
        if not self._viewing_zenith_angle:
            self._compute_orbital_model()

        return AngleGrid(np.full((23, 23), self._viewing_zenith_angle), np.full((23, 23), self._viewing_azimuth_angle))
