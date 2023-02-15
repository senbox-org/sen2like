import os
import unittest

from core.product_archive import tile_db
from core.product_archive.product_selector import _read_polygon_from_json


class TestTileDb(unittest.TestCase):

    def test_mgrs_to_wrs(self):
        res = tile_db.mgrs_to_wrs("31TFJ")
        # [([196, 30], 0.7600012569702809), ([196, 29], 0.41728420731535404), ([197, 29], 0.23638134146149337),
        # ([197, 30], 0.17748451765693712)]
        self.assertEqual(len(res), 4)
        self.assertEqual(res[0], ([196, 30], 0.7600012569702809))
        self.assertEqual(res[1], ([196, 29], 0.41728420731535404))
        self.assertEqual(res[2], ([197, 29], 0.23638134146149337))
        self.assertEqual(res[3], ([197, 30], 0.17748451765693712))

        res = tile_db.mgrs_to_wrs("33TTG",same_utm=True)
        self.assertEqual(len(res), 2)
        res = tile_db.mgrs_to_wrs("33TTG",same_utm=False)
        self.assertEqual(len(res), 3)

    def test_wrs_to_mgrs(self):
        res = tile_db.wrs_to_mgrs("196_30")
        # ['25XDA', '25XEA', '25WEV', '25WDV', '25XDB']
        self.assertEqual(len(res), 5)
        self.assertEqual(res[0], '25XDA')
        self.assertEqual(res[1], '25XEA')
        self.assertEqual(res[2], '25WEV')
        self.assertEqual(res[3], '25WDV')
        self.assertEqual(res[4], '25XDB')

    def test_one_tile_contains_roi(self):
        test_folder_path = os.path.dirname(__file__)
        roi_path_file = os.path.join(test_folder_path, 'Avignon-communes-84-vaucluse.geojson')
        polygon = _read_polygon_from_json(roi_path_file)
        res = tile_db.tiles_contains_roi(polygon)
        self.assertEqual(res[0], "31TFJ")
        self.assertEqual(len(res), 1)

    def test_multiple_tiles_contains_roi(self):
        test_folder_path = os.path.dirname(__file__)
        roi_path_file = os.path.join(test_folder_path, 'on_rome.geojson')
        polygon = _read_polygon_from_json(roi_path_file)
        res = tile_db.tiles_contains_roi(polygon)
        res = sorted(res)
        self.assertEqual(res[0], "32TQM")
        self.assertEqual(res[1], "33TTG")
        self.assertEqual(len(res), 2)

    def test_get_coverage(self):
        # WRS UTM 32 vs MGRS UTM 33
        assert tile_db.get_coverage((192,31), "33TTG", True) == 0
        assert tile_db.get_coverage((192,31), "33TTG", False) != 0

        # WRS UTM 33 vs MGRS UTM 33
        assert tile_db.get_coverage((191,31), "33TTG", True) != 0
        assert tile_db.get_coverage((191,31), "33TTG", False) != 0

        print(tile_db.get_coverage((192,30), "33TTG", True))
        print("-> %s" , tile_db.get_coverage((192,30), "33TTG", False))

if __name__ == '__main__':
    unittest.main()
