"""An interface for accessing the Copernicus 90m DEM."""

import itertools
import logging
import os
import tarfile
import tempfile
import urllib.request
import zipfile
from urllib.error import HTTPError

from osgeo import gdal
from osgeo import ogr

from core.S2L_config import S2L_Config
import core.product_archive.tile_db as tile_db

logging.basicConfig(
    level=logging.DEBUG,
)

LOGGER = logging.getLogger('Sen2Like')


def res_to_arcsec(resolution):
    return resolution // 3


def dem_file_from_tar(members):
    for tarinfo in members:
        if os.path.splitext(tarinfo.name)[1] == '.tif':
            tarinfo.name = os.path.basename(tarinfo.name)
            yield tarinfo


def is_local(url: str) -> bool:
    """Determine if url is a local or distant location.

    :param url: The url to test
    :return: True if url is local, False otherwise
    """
    for prefix in ["http", "https", "ftp"]:
        if url.startswith("{}://".format(prefix)):
            return False
    return True


def progress(downloaded, block_size, data_size):
    """Display download progression.

    :param downloaded: Amount of data already downloaded.
    :param block_size: Size of a data block.
    :param data_size: Total size of data to download.
    """
    percentage = downloaded * block_size / data_size
    end = ''
    if percentage > 100:
        percentage = 100.0
        end = '\n'
    print(f'\r{percentage:.2%}...', end=end)


class DemDownloader:
    """Manage DEM.

    Deduce the tile(s) that is(are) needed for covering the input extent (e.g. MGRS tile extent),
    Resolve the filenames of the tiles using latitude and longitude information (e.g. “w145/n69.dt1”),
    Download the tiles from a public server if not present on local archive,
    Mosaic the tiles, resample (if requested), and crop the tile to fit the input extent.

    TODO:
      * Manage International Date Line
      * Check mosaic
      * Check DEM file
    """

    def __init__(self, configuration):
        self.configuration = S2L_Config(configuration)
        self.mgrs_tile = None
        self.tile_geometry = None
        self.resolution = None
        self.in_resolution = None
        self.temp_directory = None
        self._dem_output = None
        self.hcs_code = None
        self.cross_dateline = False

    @property
    def dem_output(self):
        """Get DEM file for mgrs extent."""
        if self._dem_output is None:
            dem_parameters = self.configuration.get_section('DemDownloader')
            self._dem_output = os.path.join(
                self.configuration.get('dem_local_url', '').format(**dem_parameters, **self.__dict__))
        return self._dem_output

    def get(self, mgrs_tile, hcs_code='EPSG:32632', in_resolution=90, resolution=60):
        self.mgrs_tile = mgrs_tile
        self.in_resolution = in_resolution
        self.resolution = resolution
        self.hcs_code = hcs_code
        self.tile_geometry = None
        self._dem_output = None
        self.tile_geometry = None
        self.temp_directory = None
        self.cross_dateline = False

        if os.path.isfile(self.dem_output):
            LOGGER.info('DEM file for tile %s: %s', self.mgrs_tile, self.dem_output)
            return self.dem_output

        LOGGER.warning('No DEM available for tile %s.', self.mgrs_tile)

        if not self.configuration.getboolean('download_if_unavailable'):
            return None

        return self.process(mgrs_tile)

    def process(self, mgrs_tile):
        LOGGER.info("Trying to download DEM for tile %s", self.mgrs_tile)

        self.temp_directory = tempfile.TemporaryDirectory()

        locations = self.compute_tile_extent()
        dem_files = self.resolve_dem_filenames(locations)
        if not self.check_tiles(dem_files):
            LOGGER.error("Error while processing tile %s. DEM is invalid.", mgrs_tile)
        else:
            dem_file = self.create_dem(dem_files)
            if dem_file is None:
                LOGGER.error("Invalid DEM for tile: %s", self.mgrs_tile)
            else:
                LOGGER.info("DEM file for tile %s: %s", self.mgrs_tile, dem_file)
                return dem_file
        return None

    def extent(self, utm):
        tile_wkt = tile_db.mgrs_to_wkt(self.mgrs_tile, utm=utm)
        if tile_wkt is None:
            LOGGER.error("Cannot get geometry for tile %s", self.mgrs_tile)
        self.tile_geometry = ogr.CreateGeometryFromWkt(tile_wkt)
        return self.tile_geometry.GetEnvelope()

    def compute_tile_extent(self):
        """Deduce the tile(s) that is(are) needed for covering the input extent (e.g. MGRS tile extent).

        :param mgrs_tile: Input extent.
        :return: List of latitudes, longitudes corresponding to dem tiles.
        """
        locations = None
        extent = self.extent(False)
        LOGGER.debug("Extent: %s", extent)
        if extent:
            lon_min, lon_max, lat_min, lat_max = extent

            lat_min = int(lat_min if lat_min > 0 else lat_min - 1)
            lat_max = int(lat_max + 1 if lat_max > 0 else lat_max)
            latitudes = range(lat_min, lat_max)
            LOGGER.debug(latitudes)

            self.cross_dateline = abs(lon_min) > abs(lon_max)
            lon_min = int(lon_min)
            lon_max = int(lon_max + 1)
            if self.cross_dateline:
                longitudes = list(range(-180, lon_min)) + list(range(lon_max - 1, 180))
            else:
                longitudes = range(lon_min, lon_max)
            LOGGER.debug(longitudes)

            latitudes = [f"{'N' if (0 < latitude <= 90) else 'S'}{abs(latitude)}" for latitude in latitudes]
            longitudes = [f"{'E' if (0 < longitude <= 180) else 'W'}{abs(longitude):03}" for longitude in longitudes]
            LOGGER.debug(latitudes)
            LOGGER.debug(longitudes)

            locations = list(itertools.product(latitudes, longitudes))
            LOGGER.debug(locations)
        else:
            LOGGER.error("Error while computing tile extent.")
        return locations

    def resolve_dem_filenames(self, locations, local=True) -> dict:
        """Resolve the filenames of the tiles using latitude and longitude information."""
        output_files = {}
        arcsec = res_to_arcsec(self.in_resolution)

        # Read configuration
        dem_parameters = self.configuration.get_section('DemDownloader')

        if locations is not None:
            for latitude, longitude in locations:
                dem_url = dem_parameters['dem_tmp_local_url' if local else 'dem_server_url'].format(**locals(),
                                                                                                    **dem_parameters,
                                                                                                    **self.__dict__)
                dem_url = dem_url.format(**locals())
                LOGGER.debug(dem_url)
                output_files[latitude, longitude] = dem_url

        return output_files

    def check_tiles(self, tile_urls: dict) -> bool:
        """Check if tiles exist on local storage.

        :param tile_urls: The tile urls to check.
        """
        exclude = []
        for location, tile_file in tile_urls.items():
            if not os.path.isfile(tile_file):
                self.download_tile(location, tile_file)
                # After download file must exist
                if not os.path.isfile(tile_file):
                    exclude.append(location)
        for location in exclude:
            tile_urls.pop(location)
        return True

    def download_tile(self, location: tuple, output_file: str):
        """Download the tiles from a public server if not present on local archive,

        :return: The tile if correctly downloaded else None.
        """
        urls = self.resolve_dem_filenames([location], local=False)
        for dem_url in urls.values():
            tmp_file = os.path.join(self.temp_directory.name, os.path.basename(dem_url))
            try:
                LOGGER.info('Downloading file to %s', tmp_file)
                local_dem, _ = urllib.request.urlretrieve(dem_url, tmp_file, reporthook=progress)
                LOGGER.info('File correctly downloaded')
            except HTTPError as err:
                LOGGER.error('Cannot get file %s : %s', dem_url, err)
            else:
                output_dir = os.path.dirname(output_file)
                if local_dem.endswith('.zip'):
                    LOGGER.info('Unzipping file...')
                    with zipfile.ZipFile(local_dem) as zip_file:
                        zip_file.extractall(output_dir)
                    LOGGER.info('DEM extracted to %s', output_dir)
                elif local_dem.endswith('.tar'):
                    LOGGER.info('Untarring file...')
                    with tarfile.open(local_dem) as tar_file:
                        tar_file.extractall(path=output_dir, members=dem_file_from_tar(tar_file))
                else:
                    LOGGER.error("Unknown archive format: %s", output_file)

    def create_dem(self, dem_files):
        dem_files = list(dem_files.values())
        output_folder = os.path.dirname(dem_files[0])

        dem_src = os.path.join(output_folder, f'Copernicus_{self.mgrs_tile}_{self.resolution}_mosaic.tif')
        LOGGER.info('Creating DEM mosaic...')
        no_data = -20000
        try:
            # Mosaic
            if self.cross_dateline:
                gdal.SetConfigOption('CENTER_LONG', '180')
            options = gdal.WarpOptions(dstNodata=no_data, outputType=gdal.GDT_Int16, dstSRS='EPSG:4326')
            ds = gdal.Warp(dem_src, dem_files, options=options)

            # Replace no-data by 0
            dem_band = ds.GetRasterBand(1)
            dem_arr = dem_band.ReadAsArray()
            dem_arr[dem_arr == no_data] = 0
            dem_band.WriteArray(dem_arr)
            dem_band.FlushCache()
            ds = None

            gdal.SetConfigOption('CENTER_LONG', '0')
            LOGGER.debug('DEM mosaic: %s', dem_src)
        except Exception as e:
            LOGGER.fatal(e, exc_info=True)
            LOGGER.fatal('error using gdalwarp')
        else:
            # Crop and reproject
            LOGGER.info('Cropping and projecting DEM...')

            extent = self.extent(True)
            os.makedirs(os.path.dirname(self.dem_output), exist_ok=True)
            options = gdal.WarpOptions(
                dstSRS=self.hcs_code, xRes=self.resolution, yRes=self.resolution,
                resampleAlg='cubicspline', outputType=gdal.GDT_Int16,
                outputBounds=(extent[0], extent[2], extent[1], extent[3]))
            try:
                gdal.Warp(self.dem_output, dem_src, options=options)
            except Exception as e:
                LOGGER.fatal(e, exc_info=True)
                LOGGER.fatal('error using gdalwarp')
            else:
                return self.dem_output

        return None


if __name__ == '__main__':
    dem_downloader = DemDownloader(r'..//conf/config.ini')
    dem = dem_downloader.get('32TNS', in_resolution=90, resolution=90, hcs_code="EPSG:32632")
    dem = dem_downloader.get('01KAB', in_resolution=90, resolution=90, hcs_code="EPSG:3142")
