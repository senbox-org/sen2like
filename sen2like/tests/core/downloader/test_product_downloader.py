import datetime
import os
from unittest import TestCase

from core.products.landsat_8.landsat8 import Landsat8Product
from core.products.sentinel_2.sentinel2 import Sentinel2Product
from sen2like.core.product_archive.product_archive import InputProductArchive, InputProduct

configuration_file = os.path.join(os.path.dirname(__file__), '..', '..', 'conf', 'conf.ini')


class TestProductDownloader(TestCase):

    def setUp(self) -> None:
        self.downloader = InputProductArchive(configuration_file)

    def test_filter_and_sort_products(self):
        # No hours, two products
        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          reader=Landsat8Product, tile_coverage=10)
        p2 = InputProduct(path="S2A_MSIL1C_20170420T103021_N0204_R108_T31TFJ_20170420T103454.SAFE",
                          date=datetime.datetime(2020, 4, 30), reader=Sentinel2Product, tile_coverage=100)
        self.assertEqual([p2, p1], self.downloader.filter_and_sort_products([p1, p2]))
        self.assertEqual([p2, p1], self.downloader.filter_and_sort_products([p2, p1]))

        # No hours multiple products
        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          reader=Landsat8Product, tile_coverage=10)
        p2 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          reader=Landsat8Product, tile_coverage=20)
        p3 = InputProduct(path="S2A_MSIL1C_20170420T103021_N0204_R108_T31TFJ_20170420T103454.SAFE",
                          date=datetime.datetime(2020, 4, 30), reader=Sentinel2Product, tile_coverage=100)
        self.assertEqual([p3, p2], self.downloader.filter_and_sort_products([p1, p2, p3]))
        self.assertEqual([p3, p2], self.downloader.filter_and_sort_products([p3, p2, p1]))
        self.assertEqual([p3, p2], self.downloader.filter_and_sort_products([p2, p1, p3]))

        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          reader=Landsat8Product, tile_coverage=10)
        p2 = InputProduct(path="LC08_L1TP_196030_20200429_20200429_01_T1", date=datetime.datetime(2020, 4, 29),
                          reader=Landsat8Product, tile_coverage=20)
        p3 = InputProduct(path="S2A_MSIL1C_20170420T103021_N0204_R108_T31TFJ_20170420T103454.SAFE",
                          date=datetime.datetime(2020, 4, 30), reader=Sentinel2Product, tile_coverage=100)
        self.assertEqual([p2, p3, p1], self.downloader.filter_and_sort_products([p1, p2, p3]))
        self.assertEqual([p2, p3, p1], self.downloader.filter_and_sort_products([p3, p2, p1]))
        self.assertEqual([p2, p3, p1], self.downloader.filter_and_sort_products([p2, p1, p3]))

        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          reader=Landsat8Product, tile_coverage=20)
        p2 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          reader=Landsat8Product, tile_coverage=10)
        p3 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          reader=Landsat8Product, tile_coverage=30)
        self.assertEqual([p3], self.downloader.filter_and_sort_products([p1, p2, p3]))
        self.assertEqual([p3], self.downloader.filter_and_sort_products([p3, p2, p1]))
        self.assertEqual([p3], self.downloader.filter_and_sort_products([p2, p1, p3]))

        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          reader=Landsat8Product, tile_coverage=20)
        p2 = InputProduct(path="LC08_L1TP_196030_20200429_20200429_01_T1", date=datetime.datetime(2020, 4, 29),
                          reader=Landsat8Product, tile_coverage=10)
        p3 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30),
                          reader=Landsat8Product, tile_coverage=30)
        self.assertEqual([p2, p3], self.downloader.filter_and_sort_products([p1, p2, p3]))
        self.assertEqual([p2, p3], self.downloader.filter_and_sort_products([p3, p2, p1]))
        self.assertEqual([p2, p3], self.downloader.filter_and_sort_products([p2, p1, p3]))

        # With hour
        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 10, 11),
                          reader=Landsat8Product,
                          tile_coverage=20)
        p2 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 11, 12),
                          reader=Landsat8Product,
                          tile_coverage=10)
        p3 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 9, 8),
                          reader=Landsat8Product,
                          tile_coverage=30)
        self.assertEqual([p3], self.downloader.filter_and_sort_products([p1, p2, p3]))
        self.assertEqual([p3], self.downloader.filter_and_sort_products([p3, p2, p1]))
        self.assertEqual([p3], self.downloader.filter_and_sort_products([p2, p1, p3]))

        p1 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 10, 10),
                          reader=Landsat8Product,
                          tile_coverage=20)
        p2 = InputProduct(path="LC08_L1TP_196030_20200429_20200429_01_T1", date=datetime.datetime(2020, 4, 29, 10, 10),
                          reader=Landsat8Product,
                          tile_coverage=10)
        p3 = InputProduct(path="LC08_L1TP_196030_20200430_20200430_01_T1", date=datetime.datetime(2020, 4, 30, 9, 10),
                          reader=Landsat8Product,
                          tile_coverage=30)
        self.assertEqual([p2, p3], self.downloader.filter_and_sort_products([p1, p2, p3]))
        self.assertEqual([p2, p3], self.downloader.filter_and_sort_products([p3, p2, p1]))
        self.assertEqual([p2, p3], self.downloader.filter_and_sort_products([p2, p1, p3]))
