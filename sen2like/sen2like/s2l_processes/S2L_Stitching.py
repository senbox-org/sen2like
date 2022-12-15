import logging
import os

from osgeo import gdal
import numpy as np
import shutil

from core import S2L_config
from core.product_archive.product_archive import InputProductArchive
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from grids import mgrs_framing
from s2l_processes.S2L_Process import S2L_Process
import core.product_archive.tile_db as tile_db

log = logging.getLogger("Sen2Like")


class S2L_Stitching(S2L_Process):
    # Margin for stitched image, to prevent no data after geometric process
    margin = 10
    tile_coverage = 0.5

    def initialize(self):
        self.downloader = InputProductArchive(S2L_config.config)
        self.new_product = None

    def output_file(self, product, band=None, image=None, extension=None):
        if band is None and image is not None:
            return os.path.join(S2L_config.config.get('wd'), product.name, image.rootname + extension)
        return S2L_Process.output_file(self, product, band, extension)

    @property
    def tile(self):
        return S2L_config.config.get('tile', '31TFJ')

    def acquisition(self, product, row_offset=1):
        start_date = product.acqdate.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = product.acqdate.replace(hour=23, minute=59, second=59)
        if product.sensor in ('L8', 'L9'):
            if product.mtl.row is not None:
                row = int(product.mtl.row) + row_offset
            else:
                row = product.mtl.row
                log.debug(f"Search product on path [{product.mtl.path}, {row}]")
            urls = [(self.downloader.construct_url("Landsat8", path=product.mtl.path,
                                                   row=row, start_date=start_date,
                                                   end_date=end_date, cloud_cover=100), None)]
        else:
            log.debug("Search product on same tile [{}]".format(self.tile))
            urls = [(self.downloader.construct_url("Sentinel2", tile=self.tile, start_date=start_date,
                                                   end_date=end_date, cloud_cover=100), None)]
        log.debug(f'Urls: {urls}')
        new_products = self.downloader.get_products_from_urls(urls, start_date=start_date, end_date=end_date,
                                                              exclude=[product],
                                                              processing_level=product.processing_level(product.name))
        return new_products

    def _get_s2_new_product(self, product):
        log.debug("Product is located on {}".format(product.mtl.mgrs))
        new_products = self.acquisition(product)
        log.debug("Products on same date:")
        log.debug(new_products)
        if len(new_products):
            self.new_product = new_products[0]
        else:
            log.debug("No product found for stitching")
            self.new_product = None

    def _get_l8_new_product(self, product):
        products = []
        log.debug("Product is located on [%s, %s]", product.mtl.path, product.mtl.row)
        log.debug(tile_db.get_coverage((product.mtl.path, product.mtl.row), product.mtl.mgrs))
        # Get previous_acquisition and test eligibility
        for row_offset in [-1, 1]:
            new_products = self.acquisition(product, row_offset=row_offset)
            log.debug("products for row_offset: %s", row_offset)
            log.debug([p.path for p in new_products])
            if len(new_products):
                coverage = tile_db.get_coverage((product.mtl.path, int(product.mtl.row) + row_offset), product.mtl.mgrs)
                log.debug(coverage)
                if coverage > 0.001:
                    products.append((new_products[0], coverage))

        if len(products) > 0:
            products = sorted(products, key=lambda t: t[1], reverse=True)
            self.new_product = products[0][0]
            log.info("Product found for stitching %s:", self.new_product.path)
        else:
            log.info("No product found for stitching")
            self.new_product = None

    def get_new_product(self, product):
        if product.sensor in ('L8', 'L9'):
            self._get_l8_new_product(product)
        elif product.sensor == 'S2':
            self._get_s2_new_product(product)
        else:
            log.info("Product type not supported by stitching: %s", product.sensor)
            self.new_product = None

    def reframe(self, image, product, band=None, dtype=None):
        # Add margin
        margin = int(S2L_config.config.get('reframe_margin', self.margin))
        log.debug(f"Using {margin} as margin.")
        product_image = mgrs_framing.reframe(image, self.tile,
                                             filepath_out=self.output_file(product, band, image, "_PREREFRAMED"),
                                             order=0, margin=margin, dtype=dtype, compute_offsets=True)
        if S2L_config.config.getboolean('generate_intermediate_products'):
            product_image.write(creation_options=['COMPRESS=LZW'], DCmode=True)  # digital count
        return product_image

    def stitch(self, product, product_image, new_product_image, band=None):
        # Stitch images
        merged_array = product_image.array.copy()
        np.copyto(merged_array, new_product_image.array, where=product_image.array == 0)

        stitched_product_image = new_product_image.duplicate(array=merged_array,
                                                             filepath=self.output_file(product, band, product_image,
                                                                                       "_STITCHED"))
        return stitched_product_image

    @staticmethod
    def stitch_multi(product, product_file, new_product_file):
        ds_product_src = gdal.Open(product_file)
        ds_new_product_src = gdal.Open(new_product_file)

        filepath_out = os.path.join(S2L_config.config.get('wd'), product.name, 'tie_points_STITCHED.TIF')
        for i in range(1, ds_product_src.RasterCount + 1):
            array_product = ds_product_src.GetRasterBand(i).ReadAsArray()
            array_new_product = ds_new_product_src.GetRasterBand(i).ReadAsArray()
            np.copyto(array_product, array_new_product, where=array_product == 0)

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
        ds_new_product_src = None
        ds_dst = None
        return filepath_out

    def preprocess(self, product: S2L_Product):
        self.get_new_product(product)
        if self.new_product is None:
            return
        # Stitch validity mask and angles
        product_validity_masks = []
        product_nodata_masks = []
        product_angles = []
        product_ndvi = []
        for _product in [product, self.new_product.s2l_product_class(self.new_product.path)]:
            is_mask_valid = True
            # Validity mask
            if _product.mask_filename is None:
                is_mask_valid = _product.get_valid_pixel_mask(
                    os.path.join(S2L_config.config.get("wd"),
                                 _product.name, 'valid_pixel_mask.tif'),
                    product.roi_filename)
            if is_mask_valid:
                product_validity_masks.append(self.reframe(S2L_ImageFile(_product.mask_filename), _product))
                product_nodata_masks.append(self.reframe(S2L_ImageFile(_product.nodata_mask_filename), _product))
            # Angles
            if _product.angles_file is None:
                _product.get_angle_images(os.path.join(S2L_config.config.get("wd"), _product.name, 'tie_points.tif'))
            filepath_out = os.path.join(S2L_config.config.get('wd'), _product.name, 'tie_points_PREREFRAMED.TIF')
            if product.sensor != 'S2':
                mgrs_framing.reframeMulti(_product.angles_file, self.tile, filepath_out=filepath_out, order=0)
                product_angles.append(filepath_out)
            else:
                shutil.copyfile(_product.angles_file, filepath_out)
                product_angles.append(filepath_out)
            # NDVI
            if S2L_config.config.get('nbar_methode') == 'VJB':
                if _product.ndvi_filename is None:
                    _product.get_ndvi_image(os.path.join(S2L_config.config.get("wd"), _product.name, 'ndvi.tif'))
                product_ndvi.append(self.reframe(S2L_ImageFile(_product.ndvi_filename), _product))

        if None not in product_validity_masks:
            stitched_mask = self.stitch(product, product_validity_masks[0], product_validity_masks[1])
            stitched_mask.write(creation_options=['COMPRESS=LZW'])
            product.mask_filename = stitched_mask.filepath

        if None not in product_nodata_masks:
            stitched_mask = self.stitch(product, product_nodata_masks[0], product_nodata_masks[1])
            stitched_mask.write(creation_options=['COMPRESS=LZW'])
            product.nodata_mask_filename = stitched_mask.filepath

        if len(product_ndvi) > 0 and None not in product_ndvi:
            stitched_ndvi = self.stitch(product, product_ndvi[0], product_ndvi[1])
            stitched_ndvi.write(DCmode=True, creation_options=['COMPRESS=LZW'])
            product.ndvi_filename = stitched_ndvi.filepath

        stitched_angles = self.stitch_multi(product, product_angles[0], product_angles[1])
        product.angles_file = stitched_angles

        # Stitch reference band (needed by geometry module)
        band = S2L_config.config.get('reference_band', 'B04')
        if S2L_config.config.getboolean('doMatchingCorrection') and S2L_config.config.get('refImage'):
            image = product.get_band_file(band)
            self.process(product, image, band)

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        log.info('Start')
        if self.new_product is None:
            log.info("None product found for stitching.")
            log.info('End')
            return image

        # Reframe products
        product_image = self.reframe(image, product, band, dtype=np.float32)
        new_product = self.new_product.s2l_product_class(self.new_product.path)
        new_product_image = self.reframe(new_product.get_band_file(band), new_product, band, dtype=np.float32)
        stitched_product_image = self.stitch(product, product_image, new_product_image, band)
        stitched_product_image.write(creation_options=['COMPRESS=LZW'], DCmode=True)

        product.filenames[band] = stitched_product_image.filepath

        # Todo: Update metadata

        log.info('End')
        return stitched_product_image
