"""Input product file extractor module for the needs of the S2L output product
This is where the business is to create files like mask for output product from input product
"""
import abc
import datetime
import logging
import os

from dataclasses import dataclass
from typing import Optional
from xml.dom import minidom

import numpy as np

from fmask import landsatangles
from fmask import config as fmask_config
from osgeo import gdal
from rios import fileinfo
from skimage.morphology import square, erosion
from skimage.transform import resize as skit_resize

from atmcor import get_s2_angles as s2_angles

from core.image_file import S2L_ImageFile
from core.readers.reader import BaseReader
from core.readers.sentinel2 import Sentinel2MTL
from core.readers.landsat import LandsatMTL
from core.readers.sentinel2_maja import Sentinel2MajaMTL
from core.readers.landsat_maja import LandsatMajaMTL
from core.file_extractor.landsat_utils import downsample_coarse_image, make_angles_image

log = logging.getLogger("Sen2Like")

NO_DATA_MASK_FILE_NAME = 'nodata_pixel_mask.tif'
ANGLE_IMAGE_FILE_NAME = 'tie_points.tif'


@dataclass
class MaskImage:
    """Dataclass to write mask file having:
    - 'mask_array' content
    - 'mask_filename' as full name (full path) to write it
    - 'resolution' as output resolution
    - 'orig_image' is the S2_Image used to write the mask,
    it should be the orig file from witch the mask is extracted/generated.
    'orig_image' can be None, in this case, 'write' function have no effect
    """
    orig_image: S2L_ImageFile
    mask_array: np.ndarray
    mask_filename: str
    resolution: int

    def write(self):
        """Write the mask in 'mask_filename' using 'orig_image'"""
        if self.orig_image:
            mask = self.orig_image.duplicate(self.mask_filename, array=self.mask_array, res=self.resolution)
            mask.write(creation_options=['COMPRESS=LZW'])
            log.info('Written: %s', self.mask_filename)
        else:
            log.warning('Cannot write: %s, please verify it have been written', self.mask_filename)
            # this case happen in Sentinel2MTL._create_valid_mask_form_l1c_gml,
            # the mask is already created and written
            # shall we find a way to not write it and create it here ?


@dataclass
class ImageMasks:
    """'MaskImage' container for validity and no data mask
    """
    no_data_mask: MaskImage
    validity_mask: MaskImage

    def write(self):
        """Write image masks using 'MaskImage.write'"""
        self.no_data_mask.write()
        self.validity_mask.write()


@dataclass
class MaskInfo:
    """Mask information having info to compute valid and nodata pixel percentage"""
    mask_size: int
    nb_valid_pixel: int
    nb_nodata_pixel: int

    def get_valid_pixel_percentage(self) -> float:
        """get valid pixel percentage considering nodata

        Returns:
            float: valid pixel percentage
        """
        return (self.nb_valid_pixel * 100) / (self.mask_size - self.nb_nodata_pixel)

    def get_nodata_pixel_percentage(self) -> float:
        """get nodata pixel percentage

        Returns:
            float: valid pixel percentage
        """
        return (self.nb_nodata_pixel * 100) / self.mask_size


class InputFileExtractor(abc.ABC):
    """Abstract class for input product file extractor for the needs of S2L product.
    For example, it has the responsibility to create validity mask of S2L product
    from masks or SCL file of input product
    """

    def __init__(self, input_product: BaseReader):
        self._input_product: BaseReader = input_product

    @abc.abstractmethod
    def _get_valid_pixel_mask(self, mask_filename: str) -> ImageMasks:
        """Create validity mask and nodata pixel mask.
        nodata pixel mask name is nodata_pixel_mask.tif in the same folder of the valid pixel mask

        Args:
            mask_filename (str): valid pixel mask file path

        Returns:
            ImageMasks: generated mask container
        """

    @abc.abstractmethod
    def get_angle_images(self, out_file: str = None) -> str:
        """ Generate angles image with following band order :
        SAT_AZ , SAT_ZENITH, SUN_AZ, SUN_ZENITH
        The unit is RADIANS

        Args:
            out_file (str, optional): Name of the output tif containing all angles images. Defaults to None.

        Returns:
            str: output filename, if 'out_file' is None implementation should set to 'ANGLE_IMAGE_FILE_NAME' in the input product folder
        """

    def get_valid_pixel_mask(self, mask_filename, roi_file_path: str = None) -> Optional[ImageMasks]:
        """Create validity mask and nodata pixel mask.
        nodata pixel mask name is nodata_pixel_mask.tif in the same folder of the valid pixel mask.
        `MaskInfo` are save in the current instance

        Args:
            mask_filename (str): valid pixel mask file path
            roi_file_path (str): path to roi file to apply to the mask for roi-based-mode. Default to None

        Returns:
            ImageMasks: generated mask container
        """

        image_masks = self._get_valid_pixel_mask(mask_filename)
        if not image_masks:
            return None

        image_masks.write()

        # ROI based mode : apply ROI masks
        if roi_file_path:
            image_masks = self._apply_roi(image_masks, roi_file_path)

        return image_masks

    def _apply_roi(self, image_masks: ImageMasks, roi_file_path: str) -> ImageMasks:
        """Apply ROI for ROI based capabilities on masks.
        Update 'MaskImage.mask_array' of 'MaskImage' in 'image_masks'

        Returns:
            ImageMasks: Updated image mask after applying ROI to the masks
        """

        log.info("Apply ROI file %s ", roi_file_path)
        for mask in [image_masks.validity_mask, image_masks.no_data_mask]:
            log.info("Apply ROI to mask %s ", mask.mask_filename)
            src_mask_dataset = gdal.Open(mask.mask_filename)
            geo_transform = src_mask_dataset.GetGeoTransform()
            ul_x = geo_transform[0]
            x_res = geo_transform[1]
            ul_y = geo_transform[3]
            y_res = geo_transform[5]
            res = mask.resolution
            proj = src_mask_dataset.GetProjection()
            if res is None:
                # native geometry (default)
                res = x_res

            lr_x = ul_x + (src_mask_dataset.RasterXSize * x_res)
            lr_y = ul_y + (src_mask_dataset.RasterYSize * y_res)

            cutline_blend = 0  # on utilise 4 normalement.
            output_bounds = [ul_x, lr_y, lr_x, ul_y]
            options = gdal.WarpOptions(outputType=gdal.GDT_Byte,
                                       creationOptions=['COMPRESS=LZW'], outputBounds=output_bounds,
                                       dstSRS=proj,
                                       targetAlignedPixels=True, xRes=res, yRes=res, dstNodata=0,
                                       cutlineDSName=roi_file_path,
                                       cutlineBlend=cutline_blend,
                                       warpOptions=['NUM_THREADS=ALL_CPUS'], multithread=True)

            mask_dest_path = mask.mask_filename
            try:
                dataset = gdal.Warp(
                    mask_dest_path,
                    src_mask_dataset,
                    options=options)

                # Update current 'MaskImage.mask_array' with new mask
                mask.mask_array = dataset.GetRasterBand(1).ReadAsArray()
                dataset = None

            except RuntimeError:
                log.error("Cannot apply ROI to mask %s", mask_dest_path)

            # close src dataset
            src_mask_dataset = None

        return image_masks


class S2FileExtractor(InputFileExtractor):
    """'InputFileExtractor' implementation for S2 L1C/L2A products
    """

    def __init__(self, input_product: Sentinel2MTL):
        super().__init__(input_product)

    def _create_masks_from_scl(self, mask_filename: str, res: int) -> ImageMasks:
        """Create validity mask and nodata pixel mask from LSC image.
        Consider as valid pixels :
            - VEGETATION and NOT_VEGETATED (values 4 et 5)
            - UNCLASSIFIED (7)

        Args:
            mask_filename (str): validity mask file name
            res (int): output mask resolution

        Returns:
            ImageMasks: mask container for future writing
        """
        log.info('Generating validity and nodata masks from SCL band')
        log.debug('Read SCL: %s', self._input_product.scene_classif_band)
        scl = S2L_ImageFile(self._input_product.scene_classif_band)
        scl_array = scl.array
        if scl.xRes != res:
            shape = (int(scl_array.shape[0] * - scl.yRes / res),
                     int(scl_array.shape[1] * scl.xRes / res))
            log.debug(shape)
            scl_array = skit_resize(scl_array, shape, order=0, preserve_range=True).astype(np.uint8)

        valid_px_mask = np.zeros(scl_array.shape, np.uint8)
        # Consider as valid pixels :
        #                VEGETATION and NOT_VEGETATED (values 4 et 5)
        #                UNCLASSIFIED (7)
        valid_px_mask[scl_array == 4] = 1
        valid_px_mask[scl_array == 5] = 1
        valid_px_mask[scl_array == 7] = 1
        # valid_px_mask[scl_array == 11] = 1

        validity_mask = MaskImage(scl, valid_px_mask, mask_filename, res)

        # nodata mask
        nodata = np.ones(scl_array.shape, np.uint8)
        nodata[scl_array == 0] = 0

        nodata_mask_filename = os.path.join(os.path.dirname(mask_filename), NO_DATA_MASK_FILE_NAME)

        no_data_mask = MaskImage(scl, nodata, nodata_mask_filename, res)

        return ImageMasks(no_data_mask, validity_mask)

    def _create_nodata_mask_from_l1c(self, image: S2L_ImageFile, nodata_mask_filename: str, res: int) -> MaskImage:
        """Create the nodata 'MaskImage' from L1C S2L_ImageFile

        Args:
            image (S2L_ImageFile): L1C S2L_ImageFile from witch extract the nodata mask
            nodata_mask_filename (str): output path of the nodata pixel mask
            res (int): output mask resolution

        Returns:
            MaskImage: nodata mask container
        """
        array = image.array
        nodata = np.ones(array.shape, np.uint8)
        # shall be 0, but due to compression artefact, threshold increased to 4:
        nodata[array <= 4] = 0

        # resize nodata to output res
        shape = (int(nodata.shape[0] * - image.yRes / res),
                 int(nodata.shape[1] * image.xRes / res))
        log.debug(shape)

        # Reference band for nodata : B01 (60 m)
        # dilate no data mask with 120 m thanks to erosion (2 pixels at 60 m)
        # to be sure to avoid artefact during fusion of S2 + LS (no stitching case)
        # TODO: create a nodata mask specific to the band to be processed + find a way to have a common nodata mask for every bands
        # TODO: set nodata pixels to Nan in the image band array to optimize scipy resampling/interprolation processes
        nodata = erosion(nodata, square(5))

        nodata = skit_resize(nodata, shape, order=0, preserve_range=True).astype(np.uint8)

        return MaskImage(image, nodata, nodata_mask_filename, res)

    def _create_valid_mask_form_l1c_gml(self, mask_filename: str, nodata_mask: MaskImage, res: int) -> MaskImage:
        """Create valid pixel mask FILE from the current cloud mask.
        Current cloud mask MUST be a gml file.
        The nodata mask is applied to the generated valid mask

        Args:
            mask_filename (str): validity mask output file path
            nodata_mask (MaskImage): nodata mask to apply to the validity mask
            res (int): output mask resolution

        Returns:
            MaskImage: valid mask container
        """
        log.info('Generating validity mask from cloud mask')
        log.debug('Read cloud mask: %s', self._input_product.cloudmask)
        # Check if any cloud feature in gml
        dom = minidom.parse(self._input_product.cloudmask)
        nb_cloud = len(dom.getElementsByTagName('eop:MaskFeature'))

        # rasterize
        # make byte mask 0/1, LZW compression
        valid_px_mask = None
        if nb_cloud > 0:
            output_bounds = [self._input_product.ULX, self._input_product.LRY,
                             self._input_product.LRX, self._input_product.ULY]

            if not os.path.exists(os.path.dirname(mask_filename)):
                os.makedirs(os.path.dirname(mask_filename))

            gdal.Rasterize(mask_filename, self._input_product.cloudmask, outputType=gdal.GDT_Byte,
                           creationOptions=['COMPRESS=LZW'],
                           burnValues=0, initValues=1, outputBounds=output_bounds, outputSRS=self._input_product.epsg,
                           xRes=res, yRes=res)

            # apply nodata to validity mask
            dataset = gdal.Open(mask_filename, gdal.GA_Update)
            valid_px_mask = dataset.GetRasterBand(1).ReadAsArray()
            valid_px_mask[nodata_mask.mask_array == 0] = 0
            dataset.GetRasterBand(1).WriteArray(valid_px_mask)
            dataset = None
            log.info('Written: %s', mask_filename)
            return MaskImage(None, valid_px_mask, mask_filename, res)
        else:
            # no cloud mask, copy nodata mask
            return MaskImage(nodata_mask.orig_image, nodata_mask.mask_array, mask_filename, res)

    def _create_valid_mask_form_l1c_jp2(
            self, mask_filename: str, image: S2L_ImageFile, nodata: np.ndarray, res: int) -> MaskImage:
        """Create valid pixel 'MaskImage' from the current cloud mask.
        Current cloud mask MUST be a jp2 file.
        The nodata mask is applied to the generated valid mask

        Args:
            mask_filename (str): output path of the valid pixel mask
            image (S2L_ImageFile): S2L_ImageFile
            nodata (np.ndarray): nodata mask
            res (int): output mask resolution

        Returns:
            MaskImage: valid mask container
        """
        log.info('Generating validity mask from cloud mask, baseline 4.0')
        log.debug('mask filename: %s', mask_filename)

        log.debug('Read cloud mask: %s', self._input_product.cloudmask)
        dataset = gdal.Open(self._input_product.cloudmask, gdal.GA_ReadOnly)
        clm_1 = dataset.GetRasterBand(1).ReadAsArray()
        clm_2 = dataset.GetRasterBand(2).ReadAsArray()
        clm_3 = dataset.GetRasterBand(3).ReadAsArray()
        tot = clm_1 + clm_2 + clm_3
        valid_px_mask = np.zeros(clm_1.shape, np.uint8)
        valid_px_mask[tot == 0] = 1
        # resize valid_px  to output res:
        shape = (int(valid_px_mask.shape[0] * - image.yRes / res),
                 int(valid_px_mask.shape[1] * image.xRes / res))
        valid_px_mask = skit_resize(valid_px_mask, shape, order=0, preserve_range=True).astype(np.uint8)
        # Applied no data mask:
        valid_px_mask[nodata == 0] = 0

        # This is the way to close dataset
        dataset = None

        return MaskImage(image, valid_px_mask, mask_filename, res)

    def _create_masks_from_l1c(self, mask_filename, res) -> ImageMasks:
        """Create validity mask and nodata pixel mask from L1C image.
        Use gml or jp2 cloud mask to get valid pixels
        Args:
            mask_filename (str): file path of the output valid pixel mask
            res (int): output mask resolution

        Returns:
            ImageMasks: masks container for future writing
        """
        # Nodata Mask
        nodata_ref_band = 'B01'
        band_path = self._input_product.bands[nodata_ref_band]
        log.info('Generating nodata mask from band %s', nodata_ref_band)
        log.debug('Read band file: %s', band_path)
        image = S2L_ImageFile(band_path)
        # we do not use NO_DATA_MASK_FILE_NAME
        nodata_mask_filename = os.path.join(os.path.dirname(mask_filename),
                                            f'nodata_pixel_mask_{nodata_ref_band}.tif')
        nodata_mask = self._create_nodata_mask_from_l1c(image, nodata_mask_filename, res)

        validity_mask = None
        if self._input_product.cloudmask:
            # Cloud mask
            ext = os.path.splitext(self._input_product.cloudmask)[1]
            if ext == '.gml':
                validity_mask = self._create_valid_mask_form_l1c_gml(mask_filename, nodata_mask, res)

            elif ext == '.jp2':
                validity_mask = self._create_valid_mask_form_l1c_jp2(mask_filename, image, nodata_mask.mask_array, res)

        if not validity_mask:
            # consider all valid
            validity_mask = MaskImage(None, np.ones(image.array, np.uint8), mask_filename, res)

        return ImageMasks(nodata_mask, validity_mask)

    def _get_valid_pixel_mask(self, mask_filename: str) -> ImageMasks:
        """Create validity mask and nodata pixel mask.
        nodata pixel mask name is nodata_pixel_mask.tif in the same folder of the valid pixel mask

        Args:
            mask_filename (str): valid pixel mask file path

        Returns:
            ImageMasks: masks container for future writing
        """
        res = 20
        image_masks = None
        log.debug('get valid pixel mask')
        if self._input_product.scene_classif_band:
            image_masks = self._create_masks_from_scl(mask_filename, res)
        # L1C case for instance -> No SCL, but NODATA and CLD mask
        else:
            log.debug('L1C Case')
            image_masks = self._create_masks_from_l1c(mask_filename, res)

        return image_masks

    def get_angle_images(self, out_file: str = None) -> str:
        """See 'InputFileExtractor._get_angle_images'
        """
        # TODO : maybe refactor to :
        # not read multiple times mtl_file_name (multiple usage of extract_viewing_angle and extract_sun_angle)
        # - change root_dir in working dir it out_file is None
        if out_file is not None:
            root_dir = os.path.dirname(out_file)
        else:
            root_dir = os.path.dirname(self._input_product.tile_metadata)

        # Viewing Angles (SAT_AZ / SAT_ZENITH)
        dst_file = os.path.join(root_dir, 'VAA.tif')
        out_file_list = s2_angles.extract_viewing_angle(self._input_product.tile_metadata, dst_file, 'Azimuth')

        dst_file = os.path.join(root_dir, 'VZA.tif')
        out_file_list.extend(s2_angles.extract_viewing_angle(self._input_product.tile_metadata, dst_file, 'Zenith'))

        # Solar Angles (SUN_AZ, SUN_ZENITH)
        dst_file = os.path.join(root_dir, 'SAA.tif')
        s2_angles.extract_sun_angle(self._input_product.tile_metadata, dst_file, 'Azimuth')
        out_file_list.append(dst_file)

        dst_file = os.path.join(root_dir, 'SZA.tif')
        s2_angles.extract_sun_angle(self._input_product.tile_metadata, dst_file, 'Zenith')
        out_file_list.append(dst_file)

        out_vrt_file = os.path.join(root_dir, 'tie_points.vrt')
        gdal.BuildVRT(out_vrt_file, out_file_list, separate=True)

        if out_file is not None:
            out_tif_file = out_file
        else:
            out_tif_file = os.path.join(root_dir, ANGLE_IMAGE_FILE_NAME)

        gdal.Translate(out_tif_file, out_vrt_file, format="GTiff")

        # TODO: strange, see with the team
        # self.angles_file = out_vrt_file
        log.info('SAT_AZIMUTH, SAT_ZENITH, SUN_AZIMUTH, SUN_ZENITH')
        log.info('UNIT = DEGREES (scale: x100)')
        log.info('Angles file: %s', out_tif_file)
        return out_tif_file


class LandsatFileExtractor(InputFileExtractor):

    def __init__(self, input_product: LandsatMTL):
        super().__init__(input_product)

    def _create_masks_from_bqa(self, mask_filename: str) -> ImageMasks:
        """Create validity mask and nodata pixel mask from BQA image.
        Consider as valid pixels :
            - TODO

        Args:
            mask_filename (str): validity mask file name

        Returns:
            ImageMasks: masks container for future writing
        """
        log.info('Generating validity and nodata masks from BQA band')
        log.debug('Read cloud mask: %s', self._input_product.bqa_filename)
        bqa = S2L_ImageFile(self._input_product.bqa_filename)
        bqa_array = bqa.array

        # Process Pixel valid 'pre collection
        # Process Land Water Mask 'collection 1
        if self._input_product.collection != 'Pre Collection':
            threshold = 2720  # No land sea mask given with Collection products
            log.debug(threshold)
        else:
            threshold = 20480

        # TODO: Check threshold, 20480  not good for C-2
        if self._input_product.collection_number == '02':
            threshold = 21824

        valid_px_mask = np.zeros(bqa_array.shape, np.uint8)
        valid_px_mask[bqa_array <= threshold] = 1
        valid_px_mask[bqa_array == 1] = 0  # Remove background
        valid_px_mask[bqa_array > threshold] = 0

        validity_mask = MaskImage(bqa, valid_px_mask, mask_filename, None)

        # nodata mask (not good when taking it from BQA)
        # Reference band for nodata : First band to process (usually B01)
        if self._input_product.data_type == 'L2A':
            image_filename = self._input_product.surf_image_list[0]
        else:
            image_filename = self._input_product.dn_image_list[0]
        image = S2L_ImageFile(image_filename)
        
        nodata = image.array.clip(0, 1).astype(np.uint8)

        
        # dilate nodata mask 60 m thanks to erosion (2 pixels at 30 m)
        # avoid black border on L2H/F
        # TODO: create a nodata mask specific to the band to be processed + find a way to have a common nodata mask for every bands
        # TODO: set nodata pixels to Nan in the image band array to optimize scipy resampling/interprolation processes
        nodata = erosion(nodata, square(5))

        nodata_mask_filename = os.path.join(
            os.path.dirname(mask_filename), NO_DATA_MASK_FILE_NAME)

        no_data_mask = MaskImage(image, nodata, nodata_mask_filename, None)

        return ImageMasks(no_data_mask, validity_mask)

    def _create_masks_from_scl(self, mask_filename: str) -> ImageMasks:
        """Create validity mask and nodata pixel mask from LSC image.
        Consider as valid pixels :
            - VEGETATION and NOT_VEGETATED (values 4 et 5)
            - UNCLASSIFIED (7)
            - SNOW (11) - EXCLUDED

        Args:
            mask_filename (str): validity mask file name

        Returns:
            ImageMasks: masks container for future writing
        """
        log.info('Generating validity and nodata masks from SCL band')
        log.debug('Read SCL: %s', self._input_product.scene_classif_band)
        scl = S2L_ImageFile(self._input_product.scene_classif_band)
        scl_array = scl.array
        res = 30
        if scl.xRes != res:
            shape = (int(scl_array.shape[0] * - scl.yRes / res), int(scl_array.shape[1] * scl.xRes / res))
            log.debug(shape)
            scl_array = skit_resize(scl_array, shape, order=0, preserve_range=True).astype(np.uint8)

        valid_px_mask = np.zeros(scl_array.shape, np.uint8)
        # Consider as valid pixels :
        #                VEGETATION et NOT_VEGETATED (values 4 et 5)
        #                UNCLASSIFIED (7)
        #                excluded SNOW (11) -
        valid_px_mask[scl_array == 4] = 1
        valid_px_mask[scl_array == 5] = 1
        valid_px_mask[scl_array == 7] = 1
        valid_px_mask[scl_array == 11] = 0

        validity_mask = MaskImage(scl, valid_px_mask, mask_filename, None)

        # nodata mask
        nodata = np.ones(scl_array.shape, np.uint8)
        nodata[scl_array == 0] = 0

        nodata_mask_filename = os.path.join(
            os.path.dirname(mask_filename), NO_DATA_MASK_FILE_NAME)

        no_data_mask = MaskImage(scl, nodata, nodata_mask_filename, None)

        return ImageMasks(no_data_mask, validity_mask)

    def _get_valid_pixel_mask(self, mask_filename: str) -> ImageMasks:
        """Create validity mask and nodata pixel mask from QA or SCL image.
        nodata pixel mask name is nodata_pixel_mask.tif in the same folder of the valid pixel mask.
        Depending on collection / processing level, provide the cloud / sea mask.
        Args:
            mask_filename (str): valid pixel mask file path

        Returns:
            ImageMasks: masks container for future writing
        """

        # Open QA Image
        image_masks = None
        if self._input_product.bqa_filename:
            image_masks = self._create_masks_from_bqa(mask_filename)

        elif self._input_product.scl:
            image_masks = self._create_masks_from_scl(mask_filename)

        return image_masks

    def get_angle_images(self, out_file: str = None) -> str:
        """See 'InputFileExtractor._get_angle_images'
        """

        # downsample factor
        downsample_factor = 10

        if out_file is None:
            out_file = os.path.join(self._input_product.product_path, ANGLE_IMAGE_FILE_NAME)

        mtl_info = fmask_config.readMTLFile(self._input_product.mtl_file_name)
        image = self._input_product.reflective_band_list[0]

        # downsample image for angle computation
        coarse_res_image = downsample_coarse_image(image, os.path.dirname(out_file), downsample_factor)

        img_info = fileinfo.ImageInfo(coarse_res_image)
        corners = landsatangles.findImgCorners(coarse_res_image, img_info)
        nadir_line = landsatangles.findNadirLine(corners)
        extent_sun_angles = landsatangles.sunAnglesForExtent(img_info, mtl_info)
        sat_azimuth = landsatangles.satAzLeftRight(nadir_line)

        # do not use fmask function but internal custom function
        make_angles_image(coarse_res_image, out_file, nadir_line, extent_sun_angles, sat_azimuth)

        log.info('SAT_AZ , SAT_ZENITH, SUN_AZ, SUN_ZENITH ')
        log.info('UNIT = DEGREES (scale: x100) :')
        log.info('             %s', out_file)
        return out_file


class S2MajaFileExtractor(InputFileExtractor):

    def __init__(self, input_product: Sentinel2MajaMTL):
        super().__init__(input_product)

    def _create_nodata_mask(self, nodata_mask_file_path: str, mask_band_id: str, resolution_id: str) -> MaskImage:
        """Create no data 'MaskImage'

        Args:
            nodata_mask_file_path (str): nodata mask file path
            mask_band_id (str): nodata mask band identifier
            resolution_id (str): edge mask identifier

        Returns:
            MaskImage: created nodata mask
        """
        log.info('Read validity and nodata masks')
        log.debug('Read mask: %s', mask_band_id)

        edge = S2L_ImageFile(os.path.join(self._input_product.product_path,
                             self._input_product.edge_mask[resolution_id]))
        edge_arr = edge.array

        defective = S2L_ImageFile(os.path.join(self._input_product.product_path,
                                  self._input_product.nodata_mask[mask_band_id]))
        defective_arr = defective.array

        nodata = np.zeros(edge_arr.shape, np.uint8)
        nodata[edge_arr == 1] = 1
        nodata[defective_arr == 1] = 1

        del edge_arr
        del defective_arr

        return MaskImage(edge, nodata, nodata_mask_file_path, None)

    def _create_valid_pixel_mask(
            self, mask_filename: str, nodata: np.ndarray, mask_band_id: str, resolution_id: str) -> MaskImage:
        """Create the valid pixel 'MaskImage'

        Args:
            mask_filename (str): output path of the valid pixel mask
            nodata (np.ndarray): nodata mask
            mask_band_id (str): saturation mask band identifier
            resolution_id (str): cloud mask identifier

        Returns:
            MaskImage: the valid pixel mask
        """
        cloud = S2L_ImageFile(os.path.join(
            self._input_product.product_path, self._input_product.cloud_mask[resolution_id]))
        cloud_arr = cloud.array
        saturation = S2L_ImageFile(os.path.join(
            self._input_product.product_path, self._input_product.saturation_mask[mask_band_id]))
        saturation_arr = saturation.array

        valid_px_mask = np.ones(cloud_arr.shape, np.uint8)
        valid_px_mask[cloud_arr == 1] = 0
        valid_px_mask[cloud_arr == 2] = 0
        valid_px_mask[cloud_arr == 4] = 0
        valid_px_mask[cloud_arr == 8] = 0
        valid_px_mask[saturation_arr == 1] = 0
        valid_px_mask[nodata == 1] = 0

        return MaskImage(cloud, valid_px_mask, mask_filename, None)

    def _get_valid_pixel_mask(self, mask_filename: str) -> ImageMasks:
        """Create validity mask and nodata pixel mask.
        nodata pixel mask name is nodata_pixel_mask.tif in the same folder of the valid pixel mask

        Args:
            mask_filename (str): valid pixel mask file path

        Returns:
            ImageMasks: generated mask container
        """
        res = 20
        resolution_id = self._input_product.resolutions.get(res)
        mask_band_id = self._input_product.classif_band.get(res)

        nodata_mask_filename = os.path.join(
            os.path.dirname(mask_filename), NO_DATA_MASK_FILE_NAME)

        no_data_mask = self._create_nodata_mask(
            nodata_mask_filename, mask_band_id, resolution_id)

        validity_max = self._create_valid_pixel_mask(
            mask_filename, no_data_mask.mask_array, mask_band_id, resolution_id)

        return ImageMasks(no_data_mask, validity_max)

    def get_angle_images(self, out_file: str = None) -> str:
        """See 'InputFileExtractor._get_angle_images'
        """
        # TODO : maybe refactor to :
        # - have extract_sun_angle and extract_viewing_angle in this class,
        # - change root_dir in working dir it out_file is None
        # then refactor these methods to not read multiple times mtl_file_name
        if out_file is not None:
            root_dir = os.path.dirname(out_file)
        else:
            root_dir = os.path.dirname(self._input_product.tile_metadata)

        # Viewing Angles (SAT_AZ / SAT_ZENITH)
        dst_file = os.path.join(root_dir, 'VAA.tif')
        out_file_list = self._input_product.extract_viewing_angle(dst_file, 'Azimuth')

        dst_file = os.path.join(root_dir, 'VZA.tif')
        out_file_list.extend(self._input_product.extract_viewing_angle(dst_file, 'Zenith'))

        # Solar Angles (SUN_AZ, SUN_ZENITH)
        dst_file = os.path.join(root_dir, 'SAA.tif')
        self._input_product.extract_sun_angle(dst_file, 'Azimuth')
        out_file_list.append(dst_file)

        dst_file = os.path.join(root_dir, 'SZA.tif')
        self._input_product.extract_sun_angle(dst_file, 'Zenith')
        out_file_list.append(dst_file)

        out_vrt_file = os.path.join(root_dir, 'tie_points.vrt')
        gdal.BuildVRT(out_vrt_file, out_file_list, separate=True)

        if out_file is not None:
            out_tif_file = out_file
        else:
            out_tif_file = os.path.join(root_dir, ANGLE_IMAGE_FILE_NAME)
        gdal.Translate(out_tif_file, out_vrt_file, format="GTiff")

        # TODO : strange, see with the team
        # self.angles_file = out_vrt_file
        log.info('SAT_AZ, SAT_ZENITH, SUN_AZ, SUN_ZENITH')
        log.info('UNIT = DEGREES (scale: x100) :')
        log.info('             %s', out_tif_file)
        return out_tif_file


class LandsatMajaFileExtractor(InputFileExtractor):

    def __init__(self, input_product: LandsatMajaMTL):
        super().__init__(input_product)

    def _get_valid_pixel_mask(self, mask_filename: str) -> ImageMasks:
        """Create validity mask and nodata pixel mask.
        nodata pixel mask name is nodata_pixel_mask.tif in the same folder of the valid pixel mask

        Args:
            mask_filename (str): valid pixel mask file path

        Returns:
            ImageMasks: generated mask container
        """
        log.info('Read validity and nodata masks')

        # No data mask
        edge = S2L_ImageFile(os.path.join(self._input_product.product_path, self._input_product.edge_mask))
        edge_arr = edge.array

        nodata = np.zeros(edge_arr.shape, np.uint8)
        nodata[edge_arr == 1] = 1

        del edge_arr

        nodata_mask_filename = os.path.join(
            os.path.dirname(mask_filename), NO_DATA_MASK_FILE_NAME)
        no_data_mask = MaskImage(edge, nodata, nodata_mask_filename, None)

        # Validity mask
        cloud = S2L_ImageFile(os.path.join(self._input_product.product_path, self._input_product.cloud_mask))
        cloud_arr = cloud.array
        saturation = S2L_ImageFile(os.path.join(self._input_product.product_path, self._input_product.saturation_mask))
        saturation_arr = saturation.array

        valid_px_mask = np.ones(cloud_arr.shape, np.uint8)
        valid_px_mask[cloud_arr == 1] = 0
        valid_px_mask[cloud_arr == 2] = 0
        valid_px_mask[cloud_arr == 4] = 0
        valid_px_mask[cloud_arr == 8] = 0
        valid_px_mask[saturation_arr == 1] = 0
        valid_px_mask[nodata == 1] = 0

        validity_mask = MaskImage(cloud, valid_px_mask, mask_filename, None)

        return ImageMasks(no_data_mask, validity_mask)

    def get_angle_images(self, out_file: str = None) -> str:
        """See 'InputFileExtractor._get_angle_images'
        """

        # downsample factor
        downsample_factor = 10

        if out_file is None:
            out_file = os.path.join(self._input_product.product_path, ANGLE_IMAGE_FILE_NAME)

        image = self._input_product.reflective_band_list[0]

        # downsample image for angle computation
        coarse_res_image = downsample_coarse_image(image, os.path.dirname(out_file), downsample_factor)

        img_info = fileinfo.ImageInfo(coarse_res_image)
        corners = landsatangles.findImgCorners(coarse_res_image, img_info)
        nadir_line = landsatangles.findNadirLine(corners)
        extent_sun_angles = self._sunAnglesForExtent(img_info)
        sat_azimuth = landsatangles.satAzLeftRight(nadir_line)

        # do not use fmask function but internal custom function
        make_angles_image(coarse_res_image, out_file, nadir_line, extent_sun_angles, sat_azimuth)

        log.info('SAT_AZ , SAT_ZENITH, SUN_AZ, SUN_ZENITH ')
        log.info('UNIT = DEGREES (scale: x100) :')
        log.info('             %s', out_file)
        return out_file

    def _sunAnglesForExtent(self, img_info):
        """
        Return array of sun azimuth and zenith for each of the corners of the image
        extent. Note that this is the raster extent, not the corners of the swathe.

        The algorithm used here has been copied from the 6S possol() subroutine. The
        Fortran code I copied it from was .... up to the usual standard in 6S. So, the
        notation is not always clear.

        """
        corner_lat_long = img_info.getCorners(outEPSG=4326)
        (ul_long, ul_lat, ur_long, ur_lat, lr_long, lr_lat, ll_long, ll_lat) = corner_lat_long
        pts = np.array([
            [ul_long, ul_lat],
            [ur_long, ur_lat],
            [ll_long, ll_lat],
            [lr_long, lr_lat]
        ])
        long_deg = pts[:, 0]
        lat_deg = pts[:, 1]

        # Date/time in UTC
        date_str = self._input_product.observation_date
        time_str = self._input_product.scene_center_time.replace('Z', '')
        ymd = [int(i) for i in date_str.split('-')]
        date_obj = datetime.date(ymd[0], ymd[1], ymd[2])
        julian_day = (date_obj - datetime.date(ymd[0], 1, 1)).days + 1
        julday_year_end = (datetime.date(ymd[0], 12, 31) - datetime.date(ymd[0], 1, 1)).days + 1
        # Julian day as a proportion of the year
        jdp = julian_day / julday_year_end
        # Hour in UTC
        hms = [float(x) for x in time_str.split(':')]
        hour_gmt = hms[0] + hms[1] / 60.0 + hms[2] / 3600.0

        (sun_az, sun_zen) = landsatangles.sunAnglesForPoints(lat_deg, long_deg, hour_gmt, jdp)

        sun_angles = np.vstack((sun_az, sun_zen)).T
        return sun_angles


extractor_class = {
    Sentinel2MTL.__name__: S2FileExtractor,
    LandsatMTL.__name__: LandsatFileExtractor,
    Sentinel2MajaMTL.__name__: S2MajaFileExtractor,
    LandsatMajaMTL.__name__: LandsatMajaFileExtractor,
}
