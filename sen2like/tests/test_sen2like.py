from datetime import datetime

from unittest import TestCase

from sen2like.sen2like import group_product_list
from sen2like.core.product_archive.product_archive import InputProduct
from sen2like.core.products.landsat_8.landsat8 import Landsat8Product
from sen2like.core.products.sentinel_2.sentinel2 import Sentinel2Product

class TestSen2like(TestCase):

    def test_group_product_list(self):

        p1 = InputProduct(date=datetime(2024,10,3), s2l_product_class=Sentinel2Product)
        p2 = InputProduct(date=datetime(2024,10,1), s2l_product_class=Landsat8Product)
        p3 = InputProduct(date=datetime(2024,10,13), s2l_product_class=Landsat8Product)
        p4 = InputProduct(date=datetime(2024,10,24), s2l_product_class=Sentinel2Product)
        p5 = InputProduct(date=datetime(2024,10,11), s2l_product_class=Landsat8Product)
        p6 = InputProduct(date=datetime(2024,10,23), s2l_product_class=Sentinel2Product)

        grouped_products = group_product_list([p1, p2, p3, p4, p5, p6])

        # verify group sort
        self.assertEqual(["S2", "L8/L9"], list(grouped_products.keys()))

        # verify product sort in group
        self.assertEqual([p1, p6, p4], grouped_products["S2"])
        self.assertEqual([p2, p5, p3], grouped_products["L8/L9"])
