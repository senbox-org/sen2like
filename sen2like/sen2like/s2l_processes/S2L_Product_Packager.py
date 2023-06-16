# Copyright (c) 2023 ESA.
#
# This file is part of sen2like.
# See https://github.com/senbox-org/sen2like for further info.
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

"""S2L product packager base module"""

import datetime as dt
import logging
import os
import shutil
from dataclasses import dataclass
from xml.etree import ElementTree

import numpy as np
from skimage.transform import resize as skit_resize

import core.QI_MTD.S2_structure
import version
from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from core.QI_MTD.generic_writer import find_element_by_path
from core.QI_MTD.mtd_writers import (
    get_product_mtl_writer_class,
    get_tile_mtl_writer_class,
)
from core.QI_MTD.QIreport import QiWriter
from core.QI_MTD.stac_interface import STACWriter
from core.S2L_tools import quicklook
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")

DATE_FILE_FORMAT = "%Y%m%dT%H%M%S"


@dataclass
class PackagerConfig:
    """
    Config class for concrete S2L Packager.
    Most of them are mtd field name used to retrieve mtd value
    """
    product_type_name: str
    mtd_mask_field: str
    mtd_product_name_field: str
    mtd_granule_name_field: str
    mtd_band_root_name_field: str
    mtd_band_path_field: str
    mtd_quicklook_field: str
    mtd_bb_qi_path_field: str
    mtd_qi_report_file_name_field: str
    product_suffix: str
    mtd_product_qi_xsd_field: str
    tile_mtd_file_path: str


class S2L_Product_Packager(S2L_Process):
    """Base class for S2L product packaging"""

    def __init__(self, config: PackagerConfig):
        super().__init__()
        self.images = {}
        self.product_type_name = config.product_type_name
        self.mtd_mask_field = config.mtd_mask_field
        self.mtd_product_name_field = config.mtd_product_name_field
        self.mtd_granule_name_field = config.mtd_granule_name_field
        self.mtd_band_root_name_field = config.mtd_band_root_name_field
        self.mtd_band_path_field = config.mtd_band_path_field
        self.mtd_quicklook_field = config.mtd_quicklook_field
        self.mtd_bb_qi_path_field = config.mtd_bb_qi_path_field
        self.mtd_qi_report_file_name_field = config.mtd_qi_report_file_name_field
        self.product_suffix = config.product_suffix
        self.mtd_product_qi_xsd_field = config.mtd_product_qi_xsd_field
        self.tile_mtd_file_path = config.tile_mtd_file_path

    def base_path_product(self, product: S2L_Product):
        """
        See https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi/naming-convention
        More information https://sentinel.esa.int/documents/247904/685211/Sentinel-2-Products-Specification-Document
                         at p74, p438
        Needed parameters : datastrip sensing start
                            datatake sensing start
                            absolute orbit
                            relative orbit
                            product generation time
                            Product baseline number
        """

        relative_orbit = product.mtl.relative_orbit

        # generation time
        generation_time = dt.datetime.strftime(
            product.metadata.mtd.get('product_creation_date', None),
            DATE_FILE_FORMAT)

        datatake_sensing_start = dt.datetime.strftime(product.dt_sensing_start, DATE_FILE_FORMAT)
        datastrip_sensing_start = dt.datetime.strftime(product.ds_sensing_start, DATE_FILE_FORMAT)
        absolute_orbit = product.absolute_orbit

        tile_code = product.mgrs
        if tile_code.startswith('T'):
            tile_code = tile_code[1:]

        sensor = product.mtl.sensor[0:3]  # OLI / MSI / OLI_TIRS

        product_name = "_".join(
            [product.sensor_name, f'{sensor}{self.product_type_name}', datatake_sensing_start, f'N{version.baseline}',
             f'R{relative_orbit:0>3}', f'T{tile_code}', generation_time]) + '.SAFE'

        granule_compact_name = "_".join([self.product_type_name, f'T{tile_code}', f'A{absolute_orbit}',
                                         datastrip_sensing_start, product.sensor_name,
                                         f'R{relative_orbit:0>3}'])

        return product_name, granule_compact_name, tile_code, datatake_sensing_start

    @staticmethod
    def band_path(ts_dir: str, product_name: str, granule_name: str, outfile: str, native: bool = False):
        """
        Build band image file path of S2 product

        Args:
            ts_dir (str): path of output tile directory
            product_name (str): product name
            granule_name (str): granule name
            outfile (str): image band file name
            native (bool): if put in NATIVE sub dir

        Returns:
            full path as done by `os.path.join`

        """
        if not native:
            out_path = os.path.join(ts_dir, product_name, 'GRANULE', granule_name, 'IMG_DATA', outfile)
        else:
            out_path = os.path.join(ts_dir, product_name, 'GRANULE', granule_name, 'IMG_DATA', 'NATIVE', outfile)
        return out_path

    def preprocess(self, product: S2L_Product):

        if not self.guard(product):
            log.info('Abort pre process due to execution condition')
            return

        metadata = product.metadata
        # set it first as it is used in base_path_product
        metadata.mtd['product_creation_date'] = metadata.mtd.get('product_creation_date', dt.datetime.utcnow())

        product_name, granule_compact_name, tile_code, _ = self.base_path_product(product)

        metadata.mtd[self.mtd_product_name_field] = product_name
        metadata.mtd[self.mtd_granule_name_field] = granule_compact_name

        out_dir = os.path.join(S2L_config.config.get('archive_dir'), tile_code)

        # Creation of S2 folder tree structure
        # tree = core.QI_MTD.S2_structure.generate_S2_structure_XML(out_xml='', product_name=product_name,
        #                                                    tile_name=granule_compact_name, save_xml=False)
        # core.QI_MTD.S2_structure.create_architecture(outdir, tree, create_empty_files=True)

        log.debug('Create folder : %s', os.path.join(out_dir, product_name))
        change_nodes = {'PRODUCT_NAME': product_name,
                        'TILE_NAME': granule_compact_name,
                        }
        core.QI_MTD.S2_structure.create_architecture(out_dir, metadata.hardcoded_values.get('s2_struct_xml'),
                                                     change_nodes=change_nodes, create_empty_files=False)

        # extract mask statistic for QI report
        if product.mask_info:
            metadata.qi["NODATA_PIX_PERCENTAGE"] = f'{product.mask_info.get_nodata_pixel_percentage():.6f}'
            metadata.qi["VALID_PIX_PERCENTAGE"] = f'{product.mask_info.get_valid_pixel_percentage():.6f}'

        # extract ROI (ROI based mode
        if product.roi_filename:
            metadata.qi["ROI_FILE"] = os.path.basename(product.roi_filename)

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        """
        Write final product in the archive directory
        'archive_dir' is defined in S2L_config.config.ini file
        Naming convention from Design Document
        :param pd: instance of S2L_Product class
        :param image: input instance of S2L_ImageFile class
        :param band: band being processed
        :return: output instance of S2L_ImageFile class
        """

        log.info('Start process')
        if not self.guard(product):
            log.info('Abort process due to execution condition')
            return image

        # TODO : add production date?

        # /data/HLS_DATA/Archive/Site_Name/TILE_ID/S2L_DATEACQ_DATEPROD_SENSOR/S2L_DATEACQ_DATEPROD_SENSOR
        res = image.xRes
        product_name, granule_compact_name, tile_code, datatake_sensing_start = self.base_path_product(product)
        sensor = product.sensor_name
        relative_orbit = product.mtl.relative_orbit
        native = band in product.native_bands
        s2_band = product.get_s2like_band(band)

        if not native:
            band = s2_band

        band_root_name = "_".join([self.product_type_name, 'T' + tile_code,
                                  datatake_sensing_start, sensor, f'R{relative_orbit:0>3}'])

        product.metadata.mtd[self.mtd_band_root_name_field] = band_root_name

        output_format = S2L_config.config.get('output_format')
        outfile = "_".join([band_root_name, band, f'{int(res)}m']) + '.' + S2L_ImageFile.FILE_EXTENSIONS[
            output_format]
        # Naming convention from Sentinel-2-Products-Specification-Document (p294)

        ts_dir = os.path.join(S2L_config.config.get('archive_dir'), tile_code)  # ts = temporal series
        new_path = self.band_path(ts_dir, product_name, granule_compact_name, outfile, native=native)

        log.debug('New: %s',  new_path)
        creation_options = []

        if output_format in ('COG', 'GTIFF'):
            creation_options.append('COMPRESS=LZW')

        nodata_mask = S2L_ImageFile(product.nodata_mask_filename).array

        if nodata_mask.shape != image.array.shape:
            nodata_mask = skit_resize(
                nodata_mask.clip(min=-1.0, max=1.0), image.array.shape, order=0, preserve_range=True
            ).astype(np.uint8)

        image.write(
            creation_options=creation_options,
            filepath=new_path,
            output_format=output_format,
            band=band,
            nodata_value=0,
            no_data_mask=nodata_mask
        )

        product.metadata.mtd.get(self.mtd_band_path_field).append(new_path)

        # declare output internally
        self.images[s2_band] = image.filepath

        log.info('End process')
        return image

    def postprocess(self, product: S2L_Product):
        """
        Copy auxiliary files in the final output like mask, angle files
        Input product metadata file is also copied.
        :param pd: instance of S2L_Product class
        """

        log.info('Start postprocess')
        if not self.guard(product):
            log.info('Abort post process due to execution condition')
            return

        # output directory
        product_name, granule_compact_name, tile_code, datatake_sensing_start = self.base_path_product(product)

        ts_dir = os.path.join(S2L_config.config.get('archive_dir'), tile_code)  # ts = temporal series
        product_path = os.path.join(ts_dir, product_name)
        granule_dir = os.path.join(product_path, 'GRANULE', granule_compact_name)
        qi_data_dir = os.path.join(granule_dir, 'QI_DATA')

        # copy angles file
        self._copy_angles_file(product, qi_data_dir)

        # copy mask files
        self._copy_masks(product, qi_data_dir, product_path)

        # ROI File (ROI based mode)
        if product.roi_filename:
            shutil.copyfile(product.roi_filename, os.path.join(qi_data_dir, os.path.basename(product.roi_filename)))

        # QI directory
        qi_path = os.path.join(ts_dir, 'QI')
        if not os.path.exists(qi_path):
            os.makedirs(qi_path)

        # save correl file in QI
        if os.path.exists(os.path.join(product.working_dir, 'correl_res.txt')):
            corr_name = f"{product_name}_CORREL.csv"
            corr_path = os.path.join(qi_path, corr_name)
            shutil.copy(os.path.join(product.working_dir, 'correl_res.txt'), corr_path)

        self.postprocess_quicklooks(qi_data_dir, product)

        # Write QI report as XML
        self._write_qi_report(product, qi_data_dir)

        # Write tile MTD
        self._write_tile_mtd(product, granule_dir)

        # Write product MTD
        self._write_product_mtd(product, product_path)

        # Write stac
        stac_writer = STACWriter()
        stac_writer.write_product(
            product, product_path,
            product.metadata.mtd[self.mtd_band_path_field],
            f"{product.metadata.mtd[self.mtd_band_root_name_field]}_QL_B432.jpg",
            granule_compact_name
        )
        log.info('End postprocess')

    def postprocess_quicklooks(self, qi_data_dir: str, product: S2L_Product):
        """
        Creates all QL of the product B432 & B12118A (for multi band process, otherwise greyscale for the unique band)
        and PVI
        Args:
            qi_data_dir (str): path to quicklook output dir
            product (S2L_Product): product
        """

        # PVI : MUST BE FIRST
        band_list = ["B04", "B03", "B02"]
        pvi_filename = f"{product.metadata.mtd.get(self.mtd_band_root_name_field)}_PVI.TIF"
        ql_path = os.path.join(qi_data_dir, pvi_filename)
        result_path = quicklook(product, self.images, band_list, ql_path, S2L_config.config.get(
            "quicklook_jpeg_quality", 95),
            xRes=320, yRes=320, creationOptions=['COMPRESS=LZW'],
            out_format='GTIFF', offset=int(S2L_config.config.get('offset')))

        if result_path is not None:
            product.metadata.mtd.get(self.mtd_quicklook_field).append(ql_path)

        if len(self.images.keys()) > 1:
            # true color QL
            self.handle_product_quicklook(qi_data_dir, product, ["B04", "B03", "B02"], 'B432')
            self.handle_product_quicklook(qi_data_dir, product, ["B12", "B11", "B8A"], 'B12118A')
        else:
            # grayscale QL
            band_list = list(self.images.keys())
            self.handle_product_quicklook(qi_data_dir, product, band_list, band_list[0])

    def handle_product_quicklook(self, qi_data_dir: str, product: S2L_Product, band_list: list, suffix: str):
        """
        Creates a quicklook for the given bands
        Args:
            qi_data_dir (str): path to quicklook output dir
            product (S2L_Product): product
            band_list (list): list of band name of the product to use to generate the QL
            suffix (str): quicklook filename suffix (before extension)
        """
        ql_name = "_".join([product.metadata.mtd.get(self.mtd_band_root_name_field), 'QL', suffix]) + '.jpg'
        ql_path = os.path.join(qi_data_dir, ql_name)
        result_path = quicklook(product, self.images, band_list, ql_path, S2L_config.config.get(
            "quicklook_jpeg_quality", 95), offset=int(S2L_config.config.get('offset')))

        if result_path is not None:
            product.metadata.mtd.get(self.mtd_quicklook_field).append(ql_path)

    def guard(self, product:S2L_Product):
        # pylint: disable=unused-argument
        """ Define required condition to algorithm execution
        """
        return True

    def _copy_masks(self, product, qi_data_dir, product_path):
        # TODO : find a way to avoid this condition.
        if product.sensor in ["S2", "Prisma"] and product.mtl.tile_metadata is not None:
            tree_in = ElementTree.parse(product.mtl.tile_metadata)  # Tree of the input mtd (S2 MTD.xml)
            root_in = tree_in.getroot()
            mask_elements = find_element_by_path(root_in, './Quality_Indicators_Info/Pixel_Level_QI/MASK_FILENAME')
            for element in mask_elements:
                mask_file = os.path.join(product.path, element.text)
                if os.path.exists(mask_file):
                    shutil.copyfile(mask_file, os.path.join(qi_data_dir, os.path.basename(mask_file)))
                    product.metadata.mtd.get(self.mtd_mask_field).append({"tag": "MASK_FILENAME", "attribs": element.attrib,
                                                                  "text": element.text})

        # copy valid pixel mask
        outfile = "_".join([product.metadata.mtd.get(self.mtd_band_root_name_field), 'MSK']) + '.TIF'

        fpath = os.path.join(qi_data_dir, outfile)
        product.metadata.mtd.get(self.mtd_mask_field).append({"tag": "MASK_FILENAME", "attribs": {"type": "MSK_VALPXL"},
                                                      "text": os.path.relpath(fpath, product_path)})

        if S2L_config.config.get('output_format') == 'COG':
            img_object = S2L_ImageFile(product.mask_filename, mode='r')
            img_object.write(filepath=fpath, output_format='COG', band='MASK')
        else:
            shutil.copyfile(product.mask_filename, fpath)

    def _copy_angles_file(self, product, qi_data_dir):
        outfile = f"{product.metadata.mtd.get(self.mtd_band_root_name_field)}_ANG.TIF"
        product.metadata.mtd['ang_filename'] = outfile
        shutil.copyfile(product.angles_file, os.path.join(qi_data_dir, outfile))

    def _write_qi_report(self, product, qi_data_dir):
        bb_qi_path = product.metadata.hardcoded_values.get(self.mtd_bb_qi_path_field)
        out_qi_path = os.path.join(qi_data_dir, self.mtd_qi_report_file_name_field)

        if product.mtl.l2a_qi_report_path is not None:
            log.info('QI report for input product found here : %s', product.mtl.l2a_qi_report_path)

        qi_writer = QiWriter(bb_qi_path,
                             outfile=out_qi_path,
                             init_qi_path=product.mtl.l2a_qi_report_path,
                             H_F=self.product_suffix)
        qi_writer.manual_replaces(product)
        qi_writer.write(pretty_print=True, json_print=False)
        # validate against XSD
        product_qi_xsd = product.metadata.hardcoded_values.get(self.mtd_product_qi_xsd_field)
        log.info('QI Report is valid : %s', qi_writer.validate_schema(product_qi_xsd, out_qi_path))

    def _write_tile_mtd(self, product, granule_dir):

        tile_mtd_out_path = os.path.join(granule_dir, self.tile_mtd_file_path)

        writer_class = get_tile_mtl_writer_class(product.sensor)
        mtd_writer = writer_class(product.sensor, product.mtl.tile_metadata, self.product_suffix)

        mtd_writer.manual_replaces(product)
        mtd_writer.write(tile_mtd_out_path, pretty_print=True)
        # TODO UNCOMMENT BELOW FOR XSD CHECK
        # product_tl_xsd = metadata.hardcoded_values.get('product_tl_xsd')
        # log.info('Tile MTD is valid : {}'.format(mtd_tl_writer.validate_schema(product_tl_xsd, tile_MTD_outpath)))

    def _write_product_mtd(self, product, product_path):
        product_mtd_file_name = f'MTD_{product.mtl.sensor[0:3]}{self.product_type_name}.xml'  # MSI / OLI/ OLI_TIRS
        product_mtd_out_path = os.path.join(product_path, product_mtd_file_name)

        writer_class = get_product_mtl_writer_class(product.sensor)
        mtd_writer = writer_class(product.sensor, product.mtl.mtl_file_name, self.product_suffix)

        mtd_writer.manual_replaces(product)
        mtd_writer.write(product_mtd_out_path, pretty_print=True)
        # TODO UNCOMMENT BELOW FOR XSD CHECK
        # product_mtd_xsd = metadata.hardcoded_values.get('product_mtd_xsd')
        # log.info('Product MTD is valid : {}'.format(mtd_pd_writer.validate_schema(product_mtd_xsd, product_MTD_outpath)))
