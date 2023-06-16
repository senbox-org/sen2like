# -*- coding: utf-8 -*-
# Copyright (c) 2023 ESA.
#
# This file is part of Prisma4sen2like.
# See https://github.com/senbox-org/sen2like/prisma4sen2like for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Sentinel 2 L1 like product builder module

Example: 
/data/products/Sentinel2/12SYH/S2B_MSIL1C_20220822T175909_N0400_R041_T12SYH_20220822T201139.SAFE
├── AUX_DATA
├── DATASTRIP
│   └── DS_2BPS_20220822T201139_S20220822T180505
│       ├── MTD_DS.xml
│       └── QI_DATA
│           ├── FORMAT_CORRECTNESS.xml --> dummy file
│           ├── GENERAL_QUALITY.xml --> dummy file
│           ├── GEOMETRIC_QUALITY.xml --> dummy file
│           ├── RADIOMETRIC_QUALITY.xml --> dummy file
│           └── SENSOR_QUALITY.xml --> dummy file
├── GRANULE
│   └── L1C_T12SYH_A028524_20220822T180505
│       ├── AUX_DATA --> empty folder
│       ├── IMG_DATA --> images à générer
│       │   ├── T12SYH_20220822T175909_B01.jp2
│       │   ├── T12SYH_20220822T175909_B02.jp2
│       │   ├── T12SYH_20220822T175909_B03.jp2
│       │   ├── T12SYH_20220822T175909_B04.jp2
│       │   ├── T12SYH_20220822T175909_B05.jp2
│       │   ├── T12SYH_20220822T175909_B06.jp2
│       │   ├── T12SYH_20220822T175909_B07.jp2
│       │   ├── T12SYH_20220822T175909_B08.jp2
│       │   ├── T12SYH_20220822T175909_B09.jp2
│       │   ├── T12SYH_20220822T175909_B10.jp2
│       │   ├── T12SYH_20220822T175909_B11.jp2
│       │   ├── T12SYH_20220822T175909_B12.jp2
│       │   ├── T12SYH_20220822T175909_B8A.jp2
│       │   └── T12SYH_20220822T175909_TCI.jp2
│       ├── MTD_TL.xml
│       └── QI_DATA
│           ├── FORMAT_CORRECTNESS.xml --> dummy file
│           ├── GENERAL_QUALITY.xml --> dummy file
│           ├── GEOMETRIC_QUALITY.xml --> dummy file
│           ├── MSK_CLASSI_B00.jp2 --> à générer pour SMAC
│           ├── MSK_DETFOO_B01.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B02.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B03.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B04.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B05.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B06.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B07.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B08.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B09.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B10.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B11.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B12.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_DETFOO_B8A.jp2 --> dummy file ou, binary mask sur la footprint de l'acquisition
│           ├── MSK_QUALIT_B01.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B02.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B03.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B04.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B05.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B06.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B07.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B08.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B09.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B10.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B11.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B12.jp2 --> 30m filled by 0 (8 bands)
│           ├── MSK_QUALIT_B8A.jp2 --> 30m filled by 0 (8 bands)
│           ├── SENSOR_QUALITY.xml --> tenter de générer, si trop complexe / dummy file
│           └── T12SYH_20220822T175909_PVI.jp2 --> à générer avec info/box geo dans le jp2
├── HTML --> empty folder for now
├── INSPIRE.xml --> dummy file
├── manifest.safe --> dummy file
├── MTD_MSIL1C.xml
├── rep_info
│   └── S2_User_Product_Level-1C_Metadata.xsd --> as is
└── S2B_MSIL1C_20220822T175909_N0400_R041_T12SYH_20220822T201139-ql.jpg --> à générer


MTD_MSIL1C
TODO
"""
import logging
import os
import shutil

from adapter import MaskFileDef
from jinja2 import Environment, FileSystemLoader, select_autoescape
from osgeo import gdal
from sen2like_product import BAND_LIST, MASK_TABLE, Sen2LikeProduct
from utils import utc_format

logger = logging.getLogger(__name__)


class Sen2LikeProductBuilder:
    """Class to build/package a Sentinel 2 L1 like product"""

    _TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "product_template")

    def __init__(self, product: Sen2LikeProduct, work_dir: str, dest_dir: str):
        self._product: Sen2LikeProduct = product
        self._product_dir = os.path.join(work_dir, self._product.product_name)
        self._dest_dir = dest_dir
        self._env = Environment(loader=FileSystemLoader(self._TEMPLATE_DIR), autoescape=select_autoescape())
        self._created_masks: list[MaskFileDef] = []

    def build(self):
        """Build product in working dir then move it into destination dir"""
        # folder tree
        self._create_product_structure()

        # mask files
        self._create_mask_files()

        # images files
        self._create_pvi_file()
        self._create_band_images_file()

        # mtd files
        self._render_product_mtd()
        self._render_datastrip_mtd()
        self._render_tile_mtd()

        # finally put in destination dir
        dest_dir = os.path.join(self._dest_dir, self._product.product_name)
        os.rename(self._product_dir, dest_dir)

        logger.info("Product available in %s", dest_dir)

    # ####################
    # PATH Properties

    @property
    def _aux_path(self):
        return os.path.join(self._product_dir, "AUX_DATA")

    @property
    def _datastrip_path(self):
        return os.path.join(self._product_dir, "DATASTRIP", self._product.datastrip_identifier[17:56])

    @property
    def _datastrip_qi_data_path(self):
        return os.path.join(self._datastrip_path, "QI_DATA")

    @property
    def _html_path(self):
        return os.path.join(self._product_dir, "HTML")

    @property
    def _rep_info_path(self):
        return os.path.join(self._product_dir, "rep_info")

    @property
    def _granule_path(self):
        return os.path.join(self._product_dir, "GRANULE", self._product.short_granule_identifier)

    @property
    def _granule_aux_data_path(self):
        return os.path.join(self._granule_path, "AUX_DATA")

    @property
    def _granule_img_data_path(self):
        return os.path.join(self._granule_path, "IMG_DATA")

    @property
    def _relative_granule_qi_data_path(self):
        # Warning: this function is only for metadata template usage and not for file manipulation
        return "/".join(["GRANULE", self._product.short_granule_identifier, "QI_DATA"])

    @property
    def _granule_qi_data_path(self):
        return os.path.join(self._granule_path, "QI_DATA")

    # ########################################
    # Product files creation methods

    def _create_product_structure(self):
        logger.info("Create product folder tree in %s", self._product_dir)
        # product root
        os.mkdir(self._product_dir)

        # inside product
        os.mkdir(self._aux_path)
        os.mkdir(self._html_path)
        os.mkdir(self._rep_info_path)

        # datastrip dir
        os.makedirs(self._datastrip_path)
        os.mkdir(self._datastrip_qi_data_path)

        # granule dir
        os.makedirs(self._granule_path)
        os.mkdir(self._granule_aux_data_path)
        os.mkdir(self._granule_img_data_path)
        os.mkdir(self._granule_qi_data_path)

        # add static file
        shutil.copy(
            os.path.join(self._TEMPLATE_DIR, "rep_info", "S2_User_Product_Level-1C_Metadata.xsd"), self._rep_info_path
        )

    def _create_pvi_file(self):
        pvi_file_path = os.path.join(self._granule_qi_data_path, self._product.pvi_filename)
        tci_file_path = os.path.join(self._granule_img_data_path, self._product.tci_filename)

        # PVI : MUST BE FIRST
        band_list = ["B04", "B03", "B02"]

        images = {}
        for band in band_list:
            images[band] = self._product.get_band_file(band)

        result_path = self.quicklook(
            images,
            band_list,
            tci_file_path,
            95,
            xRes=30,
            yRes=30,
            creationOptions=["COMPRESS=LZW"],
            out_format="GTIFF",
            offset=1000,
        )

        result_path = self.quicklook(
            images,
            band_list,
            pvi_file_path,
            95,
            xRes=320,
            yRes=320,
            creationOptions=["COMPRESS=LZW"],
            out_format="GTIFF",
            offset=1000,
        )

        # result_path = self.quicklook(images, band_list, pvi_file_path, 95,
        #     xRes=320, yRes=320, creationOptions=['COMPRESS=LZW'],
        #     out_format='GTIFF', offset=1000)

    def quicklook(
        self,
        images,
        bands,
        qlpath,
        quality=95,
        xRes=30,
        yRes=30,
        out_format="JPEG",
        creationOptions: list = None,
        offset: int = 0,
    ):
        """

        :param images: list of image filepaths
        :param bands: List of 3 band index for [R, G, B]
        :param qlpath: output file path
        :return: output file path if any otherwise None
        """

        imagefiles = []

        # bands for rgb
        for band in bands:
            if band not in images.keys():
                logger.warning("Bands not available for quicklook (%s)", bands)
                return None
            else:
                imagefiles.append(images[band])

        # create output directory if it does not exist
        qldir = os.path.dirname(qlpath)
        if not os.path.exists(qldir):
            os.makedirs(qldir)

        # Grayscale or RGB
        if len(bands) == 1:
            band_list = [1]
        else:
            band_list = [1, 2, 3]

        # create single vrt with B4 B3 B2
        vrtpath = qlpath + ".vrt"

        gdal.BuildVRT(vrtpath, imagefiles, separate=True)

        # Remove nodata attribut
        vrt = gdal.Open(vrtpath, gdal.GA_Update)
        for i in band_list:
            vrt.GetRasterBand(i).DeleteNoDataValue()
        del vrt
        # convert to JPEG (with scaling)
        # TODO: DN depend on the mission, the level of processing...

        # default
        src_min = 0
        # src_min = 1
        src_max = 2500
        dst_min = 0
        # dst_min = 1
        dst_max = 255
        if bands == ["B12", "B11", "B8A"]:
            src_max = 4000

        scale = [[src_min + offset, src_max + offset, dst_min, dst_max]]

        # do gdal...
        if out_format == "GTIFF":
            # Because the driver does not support QUALITY={quality} as create_options when format='Gtiff'
            create_options = creationOptions
        else:
            create_options = (
                [f"QUALITY={quality}"] if creationOptions is None else [f"QUALITY={quality}"] + creationOptions
            )

        dataset = gdal.Translate(
            qlpath,
            vrtpath,
            xRes=xRes,
            yRes=yRes,
            resampleAlg="bilinear",
            bandList=band_list,
            outputType=gdal.GDT_Byte,
            format=out_format,
            creationOptions=create_options,
            scaleParams=scale,
        )

        quantification_value = 10000.0
        scaling = (src_max - src_min) / quantification_value / (dst_max - dst_min)

        try:
            for i in band_list:
                dataset.GetRasterBand(i).SetScale(scaling)
                # force offset to 0
                dataset.GetRasterBand(i).SetOffset(0)
                dataset.GetRasterBand(i).DeleteNoDataValue()

            dataset = None

        except Exception as e:
            logger.warning(e, exc_info=True)
            logger.warning("error updating the metadata of quicklook image")

        # clean
        os.remove(vrtpath)

        return qlpath

    def _create_band_images_file(self):
        for band in BAND_LIST:
            band_file = self._product.get_band_file(band)

            shutil.copyfile(
                band_file, os.path.join(self._granule_img_data_path, self._product.get_image_filename(band) + ".TIF")
            )

    def _create_mask_files(self):
        logger.info("Extract masks")
        # Get possible mask files, copy them to their dest dir,
        # then update _created_masks to properly fill for MTD_TL
        for mask_file in MASK_TABLE:
            logger.info("Attempt to extract %s", mask_file.value)
            mask_file_path = self._product.get_mask_file(mask_file)
            if mask_file_path:
                shutil.copyfile(mask_file_path, os.path.join(self._granule_qi_data_path, mask_file.value))
                self._created_masks.append(mask_file)
            else:
                logger.warning("Unable to extract %s", mask_file.value)

    def _render_product_mtd(self):
        logger.info("Render MTD_MSIL1C.xml")

        template = self._env.get_template("MTD_MSIL1C.xml")

        output_from_parsed_template = template.render(
            product=self._product,
            product_start=utc_format(self._product.product_start_time),
            product_stop=utc_format(self._product.product_stop_time),
            datatake_sensing_start=utc_format(self._product.datatake_sensing_start),
            generation_time=self._product.product_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        )

        # to save the results
        with open(os.path.join(self._product_dir, "MTD_MSIL1C.xml"), "w", encoding="UTF-8") as mtd_file:
            mtd_file.write(output_from_parsed_template)

    def _render_datastrip_mtd(self):
        # Refabriquer le DS name : DS_2BPS_20220822T201139_S20220822T180505
        # 2BPS : est le processing dans le nom du DS

        # Info à mettre correctement
        # - ARCHIVING_CENTRE-> Processing_Station (4 char, to be completes with _)
        # - RECEPTION_STATION -> Acquisition_Station (4 char, to be completes with _)
        # - PROCESSING_CENTER -> Processing_Station (4 char, to be completes with _)
        # - Processing_Info/UTC_DATE_TIME -> PRODUCT REPORT INFO / Processing_Time
        # - DATATAKE_SENSING_START -> Product_StartTime
        # - DATASTRIP_SENSING_START -> Product_StartTime
        # - DATASTRIP_SENSING_STOP -> Product_StopTime

        # Le reste c'est du flaN

        logger.info("Render MTD_DS.xml")

        template = self._env.get_template("DATASTRIP/DS_ID/MTD_DS.xml")

        output_from_parsed_template = template.render(
            product=self._product,
            product_start=utc_format(self._product.product_start_time),
            product_stop=utc_format(self._product.product_stop_time),
            datatake_sensing_start=utc_format(self._product.datatake_sensing_start),
            datastrip_sensing_start=utc_format(self._product.datastrip_sensing_start),
            datastrip_sensing_stop=utc_format(self._product.datastrip_sensing_stop),
            processing_time=self._product.processing_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # to save the results
        with open(os.path.join(self._datastrip_path, "MTD_DS.xml"), "w", encoding="UTF-8") as mtd_file:
            mtd_file.write(output_from_parsed_template)

    def _render_tile_mtd(self):
        # MTD_TL
        # - SENSING_TIME -> temp au centre de scene
        # - Geometric_Info -> ajouter 30x30

        # - Mean_Sun_Angle/ZENITH_ANGLE -> Sun_zenith_angle
        # - Mean_Sun_Angle/AZIMUTH_ANGLE -> Sun_azimuth_angle

        # - Tile_Angles/Sun_Angles_Grid/Zenith/Values_List -> "Sun_zenith_angle" partout
        # - Tile_Angles/Sun_Angles_Grid/Azimuth/Values_List -> "Sun_azimuth_angle" partout

        # TODO ????
        # Mean_Viewing_Incidence_Angle_List/Mean_Viewing_Incidence_Angle/ZENITH_ANGLE
        # Mean_Viewing_Incidence_Angle_List/Mean_Viewing_Incidence_Angle/AZIMUTH_ANGLE

        # TODO : in L1C_T12SYH_A028524_20220822T180505

        logger.info("Render MTD_TL.xml")

        template = self._env.get_template("GRANULE/TL_ID/MTD_TL.xml")

        output_from_parsed_template = template.render(
            product=self._product,
            sensing_time=self._product.tile_sensing_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            granule_qi_path=self._relative_granule_qi_data_path,
            mask_files=self._created_masks,
        )

        # to save the results
        with open(os.path.join(self._granule_path, "MTD_TL.xml"), "w", encoding="UTF-8") as mtd_file:
            mtd_file.write(output_from_parsed_template)
