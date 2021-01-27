from unittest import TestCase

from core.products import get_product


class TestLandsat8Product(TestCase):
    def get_best_product(self, products, reference):
        reader = get_product(products[0])
        self.assertEqual([reference], reader.best_product(products))

    def test_best_product(self):
        files = ['/eodata/Landsat-8/OLI_TIRS/L1GT/2020/03/02/LC08_L1GT_197029_20200302_20200314_01_T2']
        self.get_best_product(files, files[0])
        files = ['/eodata/Landsat-8/OLI_TIRS/L1GT/2020/03/02/LC08_L1GT_197029_20200302_20200314_01_RT']
        self.get_best_product(files, files[0])
        files = ['/eodata/Landsat-8/OLI_TIRS/L1GT/2020/03/02/LC08_L1GT_197029_20200302_20200314_01_T1']
        self.get_best_product(files, files[0])
        files = ['/eodata/Landsat-8/OLI_TIRS/L1GT/2020/03/02/LC08_L1GT_197029_20200302_20200314_01']
        self.get_best_product(files, files[0])
        files = ['/eodata/Landsat-8/OLI_TIRS/L1GT/2020/03/02/LC08_L1GT_197029_20200302_20200314_01_RT',
                 '/eodata/Landsat-8/OLI_TIRS/L1GT/2020/03/02/LC08_L1GT_197029_20200302_20200414_01_T1']
        self.get_best_product(files, files[1])
        files = ['/eodata/Landsat-8/OLI_TIRS/L1GT/2020/03/02/LC08_L1GT_197029_20200302_20200314_01_RT',
                 '/eodata/Landsat-8/OLI_TIRS/L1GT/2020/03/02/LC08_L1GT_197029_20200302_20200514_01_T2']
        self.get_best_product(files, files[1])
