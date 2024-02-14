import datetime
import os
from unittest import TestCase

from core.products.landsat_8.landsat8 import Landsat8Product
from core.products.sentinel_2.sentinel2 import Sentinel2Product
from sen2like.core.product_archive.product_archive import InputProductArchive, InputProduct
from core.S2L_config import config

configuration_file = os.path.join(os.path.dirname(__file__), 'config.ini')


class TestProductDownloader(TestCase):

    def setUp(self) -> None:
        if not config.initialize(configuration_file):
            raise Exception
        self.downloader = InputProductArchive(config)

    def test_filter_and_sort_products(self):
        # No hours, two products
        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          s2l_product_class=Landsat8Product, tile_coverage=10)
        p2 = InputProduct(path="S2A_MSIL1C_20170420T103021_N0204_R108_T31TFJ_20170420T103454.SAFE",
                          date=datetime.datetime(2020, 4, 30), s2l_product_class=Sentinel2Product, tile_coverage=100)
        self.assertEqual([p2, p1], self.downloader._filter_and_sort_products([p1, p2], "31TFJ"))
        self.assertEqual([p2, p1], self.downloader._filter_and_sort_products([p2, p1], "31TFJ"))

        # No hours multiple products
        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          s2l_product_class=Landsat8Product, tile_coverage=10)
        p2 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          s2l_product_class=Landsat8Product, tile_coverage=20)
        p3 = InputProduct(path="S2A_MSIL1C_20170420T103021_N0204_R108_T31TFJ_20170420T103454.SAFE",
                          date=datetime.datetime(2020, 4, 30), s2l_product_class=Sentinel2Product, tile_coverage=100)
        self.assertEqual([p3, p2], self.downloader._filter_and_sort_products([p1, p2, p3], "31TFJ"))
        self.assertEqual([p3, p2], self.downloader._filter_and_sort_products([p3, p2, p1], "31TFJ"))
        self.assertEqual([p3, p2], self.downloader._filter_and_sort_products([p2, p1, p3], "31TFJ"))

        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          s2l_product_class=Landsat8Product, tile_coverage=10)
        p2 = InputProduct(path="LC08_L1TP_196030_20200429_20200429_01_T1", date=datetime.datetime(2020, 4, 29),
                          s2l_product_class=Landsat8Product, tile_coverage=20)
        p3 = InputProduct(path="S2A_MSIL1C_20170420T103021_N0204_R108_T31TFJ_20170420T103454.SAFE",
                          date=datetime.datetime(2020, 4, 30), s2l_product_class=Sentinel2Product, tile_coverage=100)
        self.assertEqual([p2, p3, p1], self.downloader._filter_and_sort_products([p1, p2, p3], "31TFJ"))
        self.assertEqual([p2, p3, p1], self.downloader._filter_and_sort_products([p3, p2, p1], "31TFJ"))
        self.assertEqual([p2, p3, p1], self.downloader._filter_and_sort_products([p2, p1, p3], "31TFJ"))

        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          s2l_product_class=Landsat8Product, tile_coverage=20)
        p2 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          s2l_product_class=Landsat8Product, tile_coverage=10)
        p3 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          s2l_product_class=Landsat8Product, tile_coverage=30)
        self.assertEqual([p3], self.downloader._filter_and_sort_products([p1, p2, p3], "31TFJ"))
        self.assertEqual([p3], self.downloader._filter_and_sort_products([p3, p2, p1], "31TFJ"))
        self.assertEqual([p3], self.downloader._filter_and_sort_products([p2, p1, p3], "31TFJ"))

        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          s2l_product_class=Landsat8Product, tile_coverage=20)
        p2 = InputProduct(path="LC08_L1TP_196030_20200429_20200429_01_T1", date=datetime.datetime(2020, 4, 29),
                          s2l_product_class=Landsat8Product, tile_coverage=10)
        p3 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          s2l_product_class=Landsat8Product, tile_coverage=30)
        self.assertEqual([p2, p3], self.downloader._filter_and_sort_products([p1, p2, p3], "31TFJ"))
        self.assertEqual([p2, p3], self.downloader._filter_and_sort_products([p3, p2, p1], "31TFJ"))
        self.assertEqual([p2, p3], self.downloader._filter_and_sort_products([p2, p1, p3], "31TFJ"))

        # With hour
        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 10, 11),
                          s2l_product_class=Landsat8Product,
                          tile_coverage=20)
        p2 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 11, 12),
                          s2l_product_class=Landsat8Product,
                          tile_coverage=10)
        p3 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 9, 8),
                          s2l_product_class=Landsat8Product,
                          tile_coverage=30)
        self.assertEqual([p3], self.downloader._filter_and_sort_products([p1, p2, p3], "31TFJ"))
        self.assertEqual([p3], self.downloader._filter_and_sort_products([p3, p2, p1], "31TFJ"))
        self.assertEqual([p3], self.downloader._filter_and_sort_products([p2, p1, p3], "31TFJ"))

        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 10, 10),
                          s2l_product_class=Landsat8Product,
                          tile_coverage=20)
        p2 = InputProduct(path="LC08_L1TP_196030_20200429_20200429_01_T1", date=datetime.datetime(2020, 4, 29, 10, 10),
                          s2l_product_class=Landsat8Product,
                          tile_coverage=10)
        p3 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 9, 10),
                          s2l_product_class=Landsat8Product,
                          tile_coverage=30)
        self.assertEqual([p2, p3], self.downloader._filter_and_sort_products([p1, p2, p3], "31TFJ"))
        self.assertEqual([p2, p3], self.downloader._filter_and_sort_products([p3, p2, p1], "31TFJ"))
        self.assertEqual([p2, p3], self.downloader._filter_and_sort_products([p2, p1, p3], "31TFJ"))
