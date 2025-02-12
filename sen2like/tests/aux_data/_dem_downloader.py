import os
import shutil
from dataclasses import dataclass
from unittest import TestCase

from dem.dem_downloader import DemDownloader

LOCAL_TMP = "/tmp/DEM"


@dataclass
class Arguments:
    """argument parser result stub"""

    mgrs_tile_code: str = "33TTG"
    dem_dataset_name: str = "COP-DEM_GLO-90-DGED__2022_1"
    dem_local_url: str = LOCAL_TMP
    server_url: str = "https://prism-dem-open.copernicus.eu/pd-desk-open-access/prismDownload/"


class TestDemDownloader(TestCase):
    """DemDownloader test class"""

    def tearDown(self):
        """clean temp folder"""
        if os.path.exists(LOCAL_TMP):
            shutil.rmtree(LOCAL_TMP)

    def test_north_est(self):
        arg = Arguments()
        dem_downloader = DemDownloader(arg)
        res = dem_downloader.get()
        assert os.path.isfile(res)
        assert res == "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/Copernicus_DSM_90m_33TTG.TIF"
        assert os.path.isfile(
            "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/geocells/Copernicus_DSM_30_N41_00_E011_00_DEM.tif"
        )
        assert os.path.isfile(
            "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/geocells/Copernicus_DSM_30_N41_00_E012_00_DEM.tif"
        )
        assert os.path.isfile(
            "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/geocells/Copernicus_DSM_30_N42_00_E011_00_DEM.tif"
        )
        assert os.path.isfile(
            "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/geocells/Copernicus_DSM_30_N42_00_E012_00_DEM.tif"
        )

        # no additional download but create temp mosaic
        res = dem_downloader.get()
        assert res == "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/Copernicus_DSM_90m_33TTG.TIF"

    def test_north_west(self):
        arg = Arguments()
        arg.mgrs_tile_code = "12SYH"
        dem_downloader = DemDownloader(arg)
        res = dem_downloader.get()
        assert os.path.isfile(res)
        assert res == "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/Copernicus_DSM_90m_12SYH.TIF"
        assert os.path.isfile(
            "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/geocells/Copernicus_DSM_30_N37_00_W109_00_DEM.tif"
        )
        assert os.path.isfile(
            "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/geocells/Copernicus_DSM_30_N37_00_W108_00_DEM.tif"
        )
        assert os.path.isfile(
            "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/geocells/Copernicus_DSM_30_N38_00_W109_00_DEM.tif"
        )
        assert os.path.isfile(
            "/tmp/DEM/COP-DEM_GLO-90-DGED__2022_1/geocells/Copernicus_DSM_30_N38_00_W108_00_DEM.tif"
        )

    def test_unknow(self):
        arg = Arguments()
        arg.mgrs_tile_code = "12SY"
        dem_downloader = DemDownloader(arg)
        self.assertRaises(ValueError, dem_downloader.get)
