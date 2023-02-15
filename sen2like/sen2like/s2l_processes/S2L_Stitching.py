"""
Stitching processing bloc module
Stitching is made only with image coming from same acquisition,
meaning product with acquisition directly before or after the current product acquisition
"""
import logging
import os

from osgeo import gdal
import numpy as np

from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


class S2L_Stitching(S2L_Process):

    def _output_file(self, product, band=None, image=None, extension=None):
        if band is None and image is not None:
            return os.path.join(S2L_config.config.get('wd'), product.name, image.rootname + extension)
        return self.output_file(product, band, extension)

    @property
    def tile(self):
        return S2L_config.config.get('tile', '31TFJ')

    def stitch(self, product, product_image, related_product_image, band=None, dtype=None):
        # Stitch images
        if dtype:
            # product image band case
            merged_array = product_image.array.astype(dtype)
            np.copyto(merged_array, related_product_image.array.astype(merged_array.dtype), where=product_image.array == 0)
        else:
            # aux data case
            merged_array = product_image.array.copy()
            np.copyto(merged_array, related_product_image.array, where=product_image.array == 0)

        stitched_product_image = product_image.duplicate(array=merged_array,
                                                             filepath=self._output_file(product, band, product_image,
                                                                                       "_STITCHED"))
        return stitched_product_image

    @staticmethod
    def stitch_multi(product, product_file, related_product_file):
        ds_product_src = gdal.Open(product_file)
        ds_related_product_src = gdal.Open(related_product_file)

        filepath_out = os.path.join(S2L_config.config.get('wd'), product.name, 'tie_points_STITCHED.TIF')
        for i in range(1, ds_product_src.RasterCount + 1):
            array_product = ds_product_src.GetRasterBand(i).ReadAsArray()
            array_related_product = ds_related_product_src.GetRasterBand(i).ReadAsArray()
            np.copyto(array_product, array_related_product, where=array_product == 0)

            if i == 1:
                # write with gdal
                driver = gdal.GetDriverByName('GTiff')
                ds_dst = driver.Create(filepath_out, bands=ds_product_src.RasterCount,
                                       xsize=ds_product_src.RasterXSize, ysize=ds_product_src.RasterYSize,
                                       eType=gdal.GDT_Int16)
                ds_dst.SetProjection(ds_product_src.GetProjection())
                ds_dst.SetGeoTransform(ds_product_src.GetGeoTransform())

            # write band
            ds_dst.GetRasterBand(i).WriteArray(array_product)
        ds_dst.FlushCache()
        ds_product_src = None
        ds_related_product_src = None
        ds_dst = None
        return filepath_out

    def preprocess(self, product: S2L_Product):
        """If product have an interrelated product then
        - Reframe product and its related one aux data files, stich them
        - Run the stitching process on reference band if doMatchingCorrection needed by Geometry module

        Args:
            product (S2L_Product): product to preprocess
        """

        if product.related_product is None:
            return

        related_product = product.related_product

        # stitch
        if None not in [product.mask_filename, related_product.mask_filename]:
            stitched_mask = self.stitch(product, S2L_ImageFile(product.mask_filename), S2L_ImageFile(related_product.mask_filename))
            stitched_mask.write(creation_options=['COMPRESS=LZW'])
            product.mask_filename = stitched_mask.filepath

        if None not in [product.nodata_mask_filename, related_product.nodata_mask_filename]:
            stitched_mask = self.stitch(product, S2L_ImageFile(product.nodata_mask_filename), S2L_ImageFile(related_product.nodata_mask_filename))
            stitched_mask.write(creation_options=['COMPRESS=LZW'])
            product.nodata_mask_filename = stitched_mask.filepath

        if product.ndvi_filename is not None and related_product.ndvi_filename is not None:
            stitched_ndvi = self.stitch(product, S2L_ImageFile(product.ndvi_filename), S2L_ImageFile(related_product.ndvi_filename))
            stitched_ndvi.write(DCmode=True, creation_options=['COMPRESS=LZW'])
            product.ndvi_filename = stitched_ndvi.filepath

        stitched_angles = self.stitch_multi(product, product.angles_file, related_product.angles_file)
        product.angles_file = stitched_angles

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        log.info('Start')
        if product.related_product is None:
            log.info("None product found for stitching.")
            log.info('End')
            return image

        # stitch products band image
        related_image = product.related_product.related_image
        stitched_product_image = self.stitch(product, image, related_image, band, np.float32)
        stitched_product_image.write(creation_options=['COMPRESS=LZW'], DCmode=True)

        product.filenames[band] = stitched_product_image.filepath

        # Todo: Update metadata

        log.info('End')
        return stitched_product_image
