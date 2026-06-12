"""Tests for SMAC coefficient loading (S2L_Atmcor / atmcor.smac).

Checks that SMAC coefficients can be loaded for Sentinel-2 A/B/C (new
per-platform column format), that S2D falls back to the S2A coefficients,
and that the legacy per-band format still loads for Landsat-8.
"""

import inspect
from unittest import TestCase

from atmcor.smac import smac
from core.products.landsat_8.landsat8 import Landsat8Product
from core.products.sentinel_2.sentinel2 import Sentinel2Product
from s2l_processes.S2L_Atmcor import get_smac_coefficients

# All Sentinel-2 bands present as columns in the new-format coefficient files
S2_BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B10", "B11", "B12"]

# Attributes that smac.smac_inv() reads from a coeff object; every loaded
# coeff must expose all of them.
SMAC_INV_ATTRS = sorted(
    line.split("= coef.")[1].strip()
    for line in inspect.getsource(smac.smac_inv).splitlines()
    if "= coef." in line
)


class _FakeMtl:
    def __init__(self, product_name="", mission=""):
        self.product_name = product_name
        self.mission = mission


class _DummyS2Product(Sentinel2Product):
    """Minimal Sentinel2Product: only what get_smac_filename needs (no I/O)."""

    def __init__(self, sensor_name):
        # sensor_name is derived from mtl.product_name[:3]
        self.mtl = _FakeMtl(product_name=f"{sensor_name}_MSIL1C_dummy")


class _DummyLandsat8Product(Landsat8Product):
    """Minimal Landsat8Product for get_smac_filename (wavelength is a class attr)."""

    def __init__(self, mission="LANDSAT_8"):
        self.mtl = _FakeMtl(mission=mission)


class TestSmacCoefficientLoading(TestCase):
    def _assert_loads_all_attrs(self, coef):
        for attr in SMAC_INV_ATTRS:
            self.assertTrue(hasattr(coef, attr), f"missing SMAC coefficient {attr!r}")

    def test_sentinel2_a_b_c_load_all_bands(self):
        """S2A/S2B/S2C coefficients load for every band with all attributes."""
        for sensor in ("S2A", "S2B", "S2C"):
            product = _DummyS2Product(sensor)
            for band in S2_BANDS:
                coef_file = get_smac_coefficients(product, band)
                self.assertIsNotNone(coef_file, f"{sensor}/{band}: no coefficient file found")
                self.assertTrue(coef_file.endswith(f"Coef_{sensor}_CONTINENTAL.dat"))
                coef = smac.coeff(coef_file, band)
                self._assert_loads_all_attrs(coef)

    def test_sentinel2_band_column_selection(self):
        """The correct band column is read (locked to verified S2A B04/B8A values)."""
        product = _DummyS2Product("S2A")
        coef_b04 = smac.coeff(get_smac_coefficients(product, "B04"), "B04")
        self.assertAlmostEqual(coef_b04.ah2o, -0.0034756, places=6)
        self.assertAlmostEqual(coef_b04.taur, 0.0453, places=6)
        self.assertEqual(coef_b04.sr, coef_b04.taur)

        # A different band reads a different column -> different coefficients
        coef_b8a = smac.coeff(get_smac_coefficients(product, "B8A"), "B8A")
        self.assertAlmostEqual(coef_b8a.ah2o, -0.0003958029, places=6)
        self.assertNotEqual(coef_b04.ah2o, coef_b8a.ah2o)

    def test_sentinel2_platforms_have_distinct_coefficients(self):
        """S2A and S2C use different coefficient files with different values."""
        coef_a = smac.coeff(get_smac_coefficients(_DummyS2Product("S2A"), "B04"), "B04")
        coef_c = smac.coeff(get_smac_coefficients(_DummyS2Product("S2C"), "B04"), "B04")
        self.assertNotEqual(coef_a.ah2o, coef_c.ah2o)

    def test_sentinel2_d_uses_s2a_coefficients(self):
        """S2D has no dedicated file and falls back to the S2A coefficients."""
        s2d = _DummyS2Product("S2D")
        s2a = _DummyS2Product("S2A")
        d_file = get_smac_coefficients(s2d, "B04")
        a_file = get_smac_coefficients(s2a, "B04")
        self.assertTrue(d_file.endswith("Coef_S2A_CONTINENTAL.dat"))
        self.assertEqual(d_file, a_file)

        coef_d = smac.coeff(d_file, "B04")
        coef_a = smac.coeff(a_file, "B04")
        for attr in SMAC_INV_ATTRS:
            self.assertEqual(getattr(coef_d, attr), getattr(coef_a, attr))

    def test_unknown_band_raises(self):
        """An unknown band raises a clear error for the new-format files."""
        coef_file = get_smac_coefficients(_DummyS2Product("S2A"), "B04")
        with self.assertRaises(ValueError):
            smac.coeff(coef_file, "B99")

    def test_l8_legacy_format_loads(self):
        """Landsat-8 still loads the legacy per-band coefficient format.

        Named "l8" (not "landsat8") so it is not deselected by the CI's
        `-k 'not test_landsat ...'` filter, which targets heavier tests.
        """
        product = _DummyLandsat8Product()
        for band in ("B02", "B03", "B04", "B05"):
            coef_file = get_smac_coefficients(product, band)
            self.assertIsNotNone(coef_file, f"L8/{band}: no coefficient file found")
            self.assertTrue(coef_file.endswith("_1.dat"))
            coef = smac.coeff(coef_file)
            self._assert_loads_all_attrs(coef)
