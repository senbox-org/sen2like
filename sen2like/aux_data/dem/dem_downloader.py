#! /usr/bin/env python
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

"""An interface for accessing the Copernicus 90m DEM."""

import itertools
import logging
import os
import re
import tarfile
import urllib.request
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, RawTextHelpFormatter
from tempfile import TemporaryDirectory
from urllib.error import HTTPError

from core.product_archive import tile_db
from osgeo import gdal, ogr

LOGGER = logging.getLogger("Sen2Like")

# Apply proposed patch https://github.com/senbox-org/sen2like/pull/2
# for CVE-2007-4559 Patch


def is_within_directory(directory, target):
    abs_directory = os.path.abspath(directory)
    abs_target = os.path.abspath(target)

    prefix = os.path.commonprefix([abs_directory, abs_target])

    return prefix == abs_directory


def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
    for member in tar.getmembers():
        member_path = os.path.join(path, member.name)
        if not is_within_directory(path, member_path):
            raise Exception("Attempted Path Traversal in Tar File")

    tar.extractall(path, members, numeric_owner=numeric_owner)


# EO Patch


def res_to_arcsec(resolution: int):
    return resolution // 3


def dem_file_from_tar(tar_file: tarfile.TarFile):
    for tarinfo in tar_file:
        # only extract file *_DEM.tif
        # example Copernicus_DSM_30_N42_00_E011_00_DEM.tif
        if re.match(".*_DEM.tif", tarinfo.name):
            tarinfo.name = os.path.basename(tarinfo.name)
            yield tarinfo


def is_local(url: str) -> bool:
    """Determine if url is a local or distant location.

    Args:
        url (str): The url to test

    Returns:
        bool: True if url is local, False otherwise
    """
    for prefix in ["http", "https", "ftp"]:
        if url.startswith(f"{prefix}://"):
            return False
    return True


def progress(downloaded, block_size, data_size):
    """Display download progression.

    Args:
        downloaded: Amount of data already downloaded.
        block_size: Size of a data block.
        data_size: Total size of data to download.
    """
    percentage = downloaded * block_size / data_size
    end = ""
    if percentage > 100:
        percentage = 100.0
        end = "\n"
    print(f"\r{percentage:.2%}...", end=end)


# DEM dataset name expression to extract resolution, type of DEM, year and rev
DATASET_EXPR = re.compile(r"COP-DEM_GLO-(\d{2})-(DGED|DTED)__(\d{4})_(\d{1})")


class HelpFormatter(RawTextHelpFormatter, ArgumentDefaultsHelpFormatter):
    """Custom argparser formatter"""

    pass


class DemDownloader:
    """Manage DEM.

    Deduce the tile(s) that is(are) needed for covering the input extent (e.g. MGRS tile extent),
    Resolve the filenames of the tiles using latitude and longitude information (e.g. “w145/n69.dt1”),
    Download the tiles from a public server if not present on local archive,
    Mosaic the tiles, resample (if requested), and crop the tile to fit the input extent.
    """

    def __init__(self, args, in_resolution: int = 90, resolution: int = 90):
        self.config = args
        self.mgrs_tile_code: str = args.mgrs_tile_code
        self._mgrs_def: dict = {}
        self.resolution: int = resolution
        self.in_resolution: int = in_resolution
        self.temp_directory: TemporaryDirectory = None
        self._dem_output: str = ""
        self.cross_dateline: bool = False

    @property
    def dem_output(self) -> str:
        """Get DEM file for mgrs extent."""
        if not self._dem_output:
            self._dem_output = os.path.join(
                self.config.dem_local_url,
                self.config.dem_dataset_name,
                f"Copernicus_DSM_{self.resolution}m_{self.mgrs_tile_code}.TIF",
            )
            LOGGER.info("DEM out: %s", self._dem_output)

        return self._dem_output

    @property
    def mgrs_def(self) -> dict:
        """retrieve MGRS def from tile_db

        Raises:
            ValueError: if MGRS tile does not exists

        Returns:
            dict: MGRS def having keys:
            'index', 'TILE_ID', 'EPSG', 'UTM_WKT', 'MGRS_REF', 'LL_WKT', 'geometry'
        """
        if not self._mgrs_def:
            self._mgrs_def = tile_db.get_mgrs_def(self.mgrs_tile_code)
            if self._mgrs_def is None:
                LOGGER.error("Cannot get MGRS definition for tile %s", self.mgrs_tile_code)
                raise ValueError(f"Does tile {self.mgrs_tile_code} exists?")

        return self._mgrs_def

    def get(self) -> str:
        """Retrieve DEM file if exists, otherwise create it.

        Returns:
            str: path to the DEM file, empty if DEM cannot be produced
        """
        if os.path.isfile(self.dem_output):
            LOGGER.info("DEM file for tile %s: %s", self.mgrs_tile_code, self.dem_output)
            return self.dem_output

        LOGGER.info("No local DEM available for tile %s.", self.mgrs_tile_code)

        self.temp_directory = TemporaryDirectory()

        locations = self.compute_tile_extent()
        dem_files = self.resolve_dem_file_urls(locations)

        self.get_src_dem_tiles(dem_files)
        if len(dem_files) == 0:
            LOGGER.error("Error while processing tile %s. DEM is invalid.", self.mgrs_tile_code)
            return ""

        self.create_mgrs_dem(list(dem_files.values()))

        LOGGER.info("DEM file for tile %s: %s", self.mgrs_tile_code, self.dem_output)

        return self.dem_output

    def get_tile_extent(self, utm: bool) -> tuple:
        """Retrieve MGRS tile extend in LatLon or UTM coordinates

        Args:
            utm (bool): have UTM coordinates or not

        Returns:
            tuple: extent as minX, maxX, minY, maxY
        """
        tile_geometry = ogr.CreateGeometryFromWkt(self.mgrs_def["UTM_WKT" if utm else "LL_WKT"])
        return tile_geometry.GetEnvelope()

    def compute_tile_extent(self) -> list[tuple[str, str]]:
        """Deduce the tile(s) that is(are) needed for covering the input extent (e.g. MGRS tile extent).

        Returns:
            list[tuple[str,str]]: List of latitudes, longitudes prefixed by direction (N/S E/W)
            corresponding to dem tiles.
        """
        locations = None
        extent = self.get_tile_extent(False)
        LOGGER.debug("Extent: %s", extent)
        if extent:
            lon_min, lon_max, lat_min, lat_max = extent

            lat_min = int(lat_min if lat_min > 0 else lat_min - 1)
            lat_max = int(lat_max + 1 if lat_max > 0 else lat_max)
            latitudes = range(lat_min, lat_max)
            LOGGER.debug(latitudes)

            # For now assume we never have this case.
            # to fix it, retrieve code history to see how it was made, 
            # but it was not working well
            self.cross_dateline = False
            lon_min = int(lon_min)
            lon_max = int(lon_max + 1)
            if self.cross_dateline:
                longitudes = list(range(-180, lon_min)) + list(range(lon_max - 1, 180))
            else:
                longitudes = range(lon_min, lon_max)
            LOGGER.debug(longitudes)

            latitudes = [
                f"N{latitude}" if (0 < latitude <= 90) else f"S{abs(latitude-1)}"
                for latitude in latitudes
            ]
            longitudes = [
                f"E{longitude:03}" if (0 < longitude <= 180) else f"W{abs(longitude-1):03}"
                for longitude in longitudes
            ]
            LOGGER.debug(latitudes)
            LOGGER.debug(longitudes)

            locations = list(itertools.product(latitudes, longitudes))
            LOGGER.debug(locations)
        else:
            LOGGER.error("Error while computing tile extent.")
        return locations

    def resolve_dem_file_urls(self, locations: list[tuple[str, str]], local=True) -> dict:
        """Resolve the file url of the tiles using latitude and longitude information.
        Urls can be local file path or remote url.

        Args:
            locations (list[tuple[str,str]]): List of latitudes, longitudes prefixed by direction (N/S E/W)
            local (bool, optional): resolve local or remote source dem tile url. Defaults to True.

        Returns:
            dict: urls indexed by lat lon
        """

        arcsec = res_to_arcsec(self.in_resolution)
        dem_product_name = "Copernicus_DSM_{arcsec:02}_{latitude}_00_{longitude}_00"

        if local:
            url = os.path.join(
                self.config.dem_local_url,
                self.config.dem_dataset_name,
                "geocells",
                "{dem_product_name}_DEM.tif",
            )
        else:
            url = self.config.server_url + "{dem_dataset_name}/{dem_product_name}.tar"

        output_files = {}

        if locations is not None:
            for latitude, longitude in locations:
                dem_url = url.format(
                    dem_dataset_name=self.config.dem_dataset_name, dem_product_name=dem_product_name
                )
                # format `{dem_product_name}` put in dem_url by previous instruction
                dem_url = dem_url.format(arcsec=arcsec, latitude=latitude, longitude=longitude)

                LOGGER.debug(dem_url)
                output_files[latitude, longitude] = dem_url

        return output_files

    def get_src_dem_tiles(self, tile_urls: dict) -> bool:
        """
        Update `tile_urls` with founded tiles from.
        If a tile is not found locally, try to download it.
        If not downloaded (and so not locally founded), the corresponding url is remove from `tile_urls`

        Args:
            tile_urls (dict): tiles urls indexed by lat lon
        """
        LOGGER.info("Trying to retrieve or download DEM for tile %s", self.mgrs_tile_code)

        exclude = []
        for location, tile_file in tile_urls.items():
            if not os.path.isfile(tile_file):
                output_dir = os.path.dirname(tile_file)
                self.download_tile(location, output_dir)
                # After download file must exist
                if not os.path.isfile(tile_file):
                    LOGGER.warning("Unable to download tile for %s, exclude it.", location)
                    exclude.append(location)
        for location in exclude:
            tile_urls.pop(location)

    def download_tile(self, location: tuple, output_dir: str):
        """
        Download the tiles from a public server in a temp dir,
        then extract dem tif file in the local geocell archive

        Args:
            location (tuple): tile lat lon location
            output_dir (str): destination directory
        """
        urls = self.resolve_dem_file_urls([location], local=False)
        for dem_url in urls.values():
            tmp_file = os.path.join(self.temp_directory.name, os.path.basename(dem_url))
            try:
                LOGGER.info("Downloading file to %s", tmp_file)
                local_dem, _ = urllib.request.urlretrieve(dem_url, tmp_file, reporthook=progress)
                LOGGER.info("File correctly downloaded")
            except HTTPError as err:
                LOGGER.error("Cannot get file %s : %s", dem_url, err)
            else:
                LOGGER.info("Extract file %s", local_dem)
                with tarfile.open(local_dem) as tar_file:
                    safe_extract(tar_file, path=output_dir, members=dem_file_from_tar(tar_file))

    def _create_dem_mosaic(self, dem_mosaic_file: str, dem_files: list[str]):
        """Create DEM mosaic from source DEM tile

        Args:
            dem_mosaic_file (str): mosaic destination file path
            dem_files (list[str]): list of sources dem tile file path
        """
        LOGGER.info("Creating DEM mosaic...")
        no_data = -20000
        try:
            # Mosaic
            if self.cross_dateline:
                gdal.SetConfigOption("CENTER_LONG", "180")

            options = gdal.WarpOptions(
                dstNodata=no_data, outputType=gdal.GDT_Int16, dstSRS="EPSG:4326"
            )

            dataset = gdal.Warp(dem_mosaic_file, dem_files, options=options)

            # Replace no-data by 0
            dem_band = dataset.GetRasterBand(1)
            dem_arr = dem_band.ReadAsArray()
            dem_arr[dem_arr == no_data] = 0
            dem_band.WriteArray(dem_arr)
            dem_band.FlushCache()
            dataset = None

            gdal.SetConfigOption("CENTER_LONG", "0")
            LOGGER.debug("DEM mosaic: %s", dem_mosaic_file)
        except Exception as exception:
            LOGGER.fatal(exception, exc_info=True)
            LOGGER.fatal("error using gdalwarp")
            raise

    def _reframe_dem(self, dem_mosaic_file: str):
        """Reframe the dem mosaic in the target MGRS tile projected in the MGRS tile UTM

        Args:
            dem_mosaic_file (str): mosaic file path
        """
        LOGGER.info("Cropping and projecting DEM...")

        extent = self.get_tile_extent(True)
        os.makedirs(os.path.dirname(self.dem_output), exist_ok=True)
        options = gdal.WarpOptions(
            dstSRS=f"EPSG:{self.mgrs_def['EPSG']}",
            xRes=self.resolution,
            yRes=self.resolution,
            resampleAlg="cubicspline",
            outputType=gdal.GDT_Int16,
            outputBounds=(extent[0], extent[2], extent[1], extent[3]),
        )

        try:
            gdal.Warp(self.dem_output, dem_mosaic_file, options=options)
        except Exception as exception:
            LOGGER.fatal(exception, exc_info=True)
            LOGGER.fatal("error using gdalwarp")
            raise

    def create_mgrs_dem(self, dem_files: list[str]):
        """Create the DEM.

        Args:
            dem_files (list[str]): list of source dem files to use to create the DEM
        """

        dem_mosaic = os.path.join(
            self.temp_directory.name,
            f"Copernicus_{self.mgrs_tile_code}_{self.resolution}_mosaic.tif",
        )

        self._create_dem_mosaic(dem_mosaic, dem_files)
        # Crop to MGRS and reproject
        self._reframe_dem(dem_mosaic)


if __name__ == "__main__":
    DESCRIPTION = """
    Create DEM for a MGRS Tile.
    The generated DEM is TIF file in the MGRS extend and its projected in the MGRS tile EPSG (UTM).
    """

    _arg_parser = ArgumentParser(formatter_class=HelpFormatter, description=DESCRIPTION)

    _arg_parser.add_argument(
        dest="mgrs_tile_code",
        help="MGRS Tile code for witch to generate DEM, example 31TFJ",
        metavar="MGRS_TILE_CODE",
        type=str,
    )

    _arg_parser.add_argument(
        dest="dem_dataset_name",
        help="DEM dataset name, example COP-DEM_GLO-90-DGED__2022_1",
        metavar="DEM_DATASET_NAME",
        type=str,
    )

    _arg_parser.add_argument(
        dest="dem_local_url",
        help="""Base output folder for generated DEM, example /data/AUX_DATA/
Generated files are stored as follow :
/data/AUX_DATA/{DEM_DATASET_NAME}/Copernicus_DSM_{resolution}m_{MGRS_TILE_CODE}.TIF
        """,
        metavar="DEM_LOCAL_URL",
        type=str,
    )

    _arg_parser.add_argument(
        "--server_url",
        dest="server_url",
        help="DEM server base URL",
        required=False,
        type=str,
        default="https://prism-dem-open.copernicus.eu/pd-desk-open-access/prismDownload/",
        metavar="SERVER_URL",
    )

    _arg_parser.add_argument(
        "--debug",
        "-d",
        dest="debug",
        action="store_true",
        default=False,
        help="Enable Debug mode",
    )

    _args = _arg_parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if _args.debug else logging.INFO,
    )

    # verify dataset
    match = DATASET_EXPR.match(_args.dem_dataset_name)
    if match is None:
        raise ValueError(
            f"""
            Invalid dataset name: {_args.dem_dataset_name}.
            For more details, see https://sentinels.copernicus.eu/web/sentinel/-/copernicus-dem-new-direct-data-download-access
            """
        )

    res = int(match.group(1))
    dem_downloader = DemDownloader(_args, in_resolution=res, resolution=res)
    dem = dem_downloader.get()
