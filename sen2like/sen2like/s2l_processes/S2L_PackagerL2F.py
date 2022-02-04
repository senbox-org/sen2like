#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2020

import datetime as dt
import glob
import logging
import os
import shutil
from xml.etree import ElementTree
import numpy as np
from skimage.transform import resize as skit_resize

import core.QI_MTD.S2_structure
from core import S2L_config
from core.QI_MTD.QIreport import QiWriter
from core.QI_MTD.generic_writer import find_element_by_path
from core.QI_MTD.mtd import metadata
from core.QI_MTD.mtd_writers import MTD_writer_S2, MTD_writer_LS8, MTD_tile_writer_S2, MTD_tile_writer_LS8
from core.QI_MTD.stac_interface import STACWriter
from core.S2L_tools import quicklook
from core.image_file import S2L_ImageFile
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


class S2L_PackagerL2F(S2L_Process):
    images = {}
    out_variables = ['images']

    @staticmethod
    def base_path_S2L(product):
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

        relative_orbit = S2L_config.config.get('relative_orbit')
        file_date = dt.datetime.strftime(product.file_date, '%Y%m%dT%H%M%S')  # generation time

        if product.sensor == 'S2':
            datatake_sensing_start = dt.datetime.strftime(product.dt_sensing_start, '%Y%m%dT%H%M%S')
            datastrip_sensing_start = dt.datetime.strftime(product.ds_sensing_start, '%Y%m%dT%H%M%S')
            absolute_orbit = S2L_config.config.get('absolute_orbit')
        else:
            datatake_sensing_start = dt.datetime.strftime(product.acqdate, '%Y%m%dT%H%M%S')
            datastrip_sensing_start = file_date
            absolute_orbit = metadata.hardcoded_values.get('L8_absolute_orbit')

        PDGS = metadata.hardcoded_values.get('PDGS')
        tilecode = product.mtl.mgrs
        if tilecode.startswith('T'):
            tilecode = tilecode[1:]

        sensor = product.mtl.sensor[0:3]  # OLI / MSI / OLI_TIRS
        product_name = "_".join([product.sensor_name, '{}L2F'.format(sensor), datatake_sensing_start, 'N' + PDGS,
                                 'R{:0>3}'.format(relative_orbit), 'T' + tilecode, file_date]) + '.SAFE'
        granule_compact_name = "_".join(['L2F', 'T' + tilecode, 'A' + absolute_orbit, datastrip_sensing_start,
                                         product.sensor_name, 'R{:0>3}'.format(relative_orbit)])

        return product_name, granule_compact_name, tilecode, datatake_sensing_start

    @staticmethod
    def band_path(tsdir, product_name, granule_name, outfile, native: bool = False):
        if not native:
            out_path = os.path.join(tsdir, product_name, 'GRANULE', granule_name, 'IMG_DATA', outfile)
        else:
            out_path = os.path.join(tsdir, product_name, 'GRANULE', granule_name, 'IMG_DATA', 'NATIVE', outfile)
        return out_path

    def preprocess(self, product):

        if not self.guard():
            return

        product_name, granule_compact_name, tilecode, _ = self.base_path_S2L(product)
        metadata.mtd['product_F_name'] = product_name
        metadata.mtd['granule_F_name'] = granule_compact_name
        metadata.mtd['product_creation_date'] = metadata.mtd.get('product_creation_date', dt.datetime.now())
        outdir = os.path.join(S2L_config.config.get('archive_dir'), tilecode)

        """
        # Creation of S2 folder tree structure
        tree = core.QI_MTD.S2_structure.generate_S2_structure_XML(out_xml='', product_name=product_name,
                                                           tile_name=granule_compact_name, save_xml=False)
        core.QI_MTD.S2_structure.create_architecture(outdir, tree, create_empty_files=True)
        """

        log.debug('Create folder : ' + os.path.join(outdir, product_name))
        change_nodes = {'PRODUCT_NAME': product_name,
                        'TILE_NAME': granule_compact_name
                        }
        core.QI_MTD.S2_structure.create_architecture(outdir, metadata.hardcoded_values.get('s2_struct_xml'),
                                                     change_nodes=change_nodes, create_empty_files=False)

    def process(self, pd, image, band):
        """
        Write final product in the archive directory
        'archive_dir' is defined in S2L_config.config.ini file
        Naming convention from Design Document
        :param pd: instance of S2L_Product class
        :param image: input instance of S2L_ImageFile class
        :param band: band being processed
        :return: output instance of instance of S2L_ImageFile class
        """

        if not self.guard():
            return image
        log.info('Start process')

        # TODO : add production date?

        # /data/HLS_DATA/Archive/Site_Name/TILE_ID/S2L_DATEACQ_DATEPROD_SENSOR/S2L_DATEACQ_DATEPROD_SENSOR
        res = image.xRes
        product_name, granule_compact_name, tilecode, datatake_sensing_start = self.base_path_S2L(pd)
        sensor = pd.sensor_name
        relative_orbit = S2L_config.config.get('relative_orbit')
        native = band in pd.native_bands
        s2_band = pd.get_s2like_band(band)
        if not native:
            band = s2_band
        band_rootName = "_".join(
            ['L2F', 'T' + tilecode, datatake_sensing_start, sensor, 'R{:0>3}'.format(relative_orbit)])
        metadata.mtd['band_rootName_F'] = band_rootName

        output_format = S2L_config.config.get('output_format')
        outfile = "_".join([band_rootName, band, '{}m'.format(int(res))]) + '.' + S2L_ImageFile.FILE_EXTENSIONS[output_format]
        # Naming convention from Sentinel-2-Products-Specification-Document (p294)

        tsdir = os.path.join(S2L_config.config.get('archive_dir'), tilecode)  # ts = temporal series
        newpath = self.band_path(tsdir, product_name, granule_compact_name, outfile, native=native)

        log.debug('New: ' + newpath)
        creation_options=[]
        if output_format in ('COG', 'GTIFF'):
            creation_options.append('COMPRESS=LZW')
        nodata_mask = S2L_ImageFile(pd.mtl.nodata_mask_filename).array
        if nodata_mask.shape != image.array.shape:
            nodata_mask = skit_resize(
                nodata_mask.clip(min=-1.0, max=1.0), image.array.shape, order=0, preserve_range=True
            ).astype(np.uint8)
        image.write(
            creation_options=creation_options,
            filepath=newpath,
            output_format=output_format,
            band=band,
            nodata_value=0,
            no_data_mask=nodata_mask
        )
        metadata.mtd.get('bands_path_F').append(newpath)

        # declare output internally
        self.images[s2_band] = image.filepath
        # declare output in config file
        S2L_config.config.set('imageout_dir', image.dirpath)
        S2L_config.config.set('imageout_' + band, image.filename)

        log.info('End process')
        return image

    def postprocess(self, pd):
        """
        Copy auxiliary files in the final output like mask, angle files
        Input product metadata file is also copied.
        :param pd: instance of S2L_Product class
        """

        if not self.guard():
            return
        log.info('Start postprocess')

        # output directory
        product_name, granule_compact_name, tilecode, datatake_sensing_start = self.base_path_S2L(pd)

        tsdir = os.path.join(S2L_config.config.get('archive_dir'), tilecode)  # ts = temporal series
        outdir = product_name
        product_path = os.path.join(tsdir, outdir)
        qi_dir = os.path.join(product_path, 'GRANULE', granule_compact_name, 'QI_DATA')

        # copy angles file
        outfile = "_".join([metadata.mtd.get('band_rootName_F'), 'ANG']) + '.TIF'
        metadata.mtd['ang_filename'] = outfile
        shutil.copyfile(pd.mtl.angles_file, os.path.join(qi_dir, outfile))

        # copy mask files
        if "S2" in pd.sensor and pd.mtl.tile_metadata is not None:
            tree_in = ElementTree.parse(pd.mtl.tile_metadata)  # Tree of the input mtd (S2 MTD.xml)
            root_in = tree_in.getroot()
            mask_elements = find_element_by_path(root_in, './Quality_Indicators_Info/Pixel_Level_QI/MASK_FILENAME')
            for element in mask_elements:
                mask_file = os.path.join(pd.path, element.text)
                if os.path.exists(mask_file):
                    shutil.copyfile(mask_file, os.path.join(qi_dir, os.path.basename(mask_file)))
                    metadata.mtd.get('masks_F').append({"tag": "MASK_FILENAME",
                                                        "attribs": element.attrib,
                                                        "text": element.text})

        # copy valid pixel mask
        outfile = "_".join([metadata.mtd.get('band_rootName_F'), pd.sensor, 'MSK']) + '.TIF'

        fpath = os.path.join(qi_dir, outfile)
        metadata.mtd.get('masks_F').append({"tag": "MASK_FILENAME",
                                            "attribs": {"type": "MSK_VALPIX"},
                                            "text": os.path.relpath(fpath, product_path)})

        if S2L_config.config.get('output_format') == 'COG':
            img_object = S2L_ImageFile(pd.mtl.mask_filename, mode='r')
            img_object.write(filepath=fpath, output_format='COG', band='MASK')
        else:
            shutil.copyfile(pd.mtl.mask_filename, fpath)

        # QI directory
        qipath = os.path.join(tsdir, 'QI')
        if not os.path.exists(qipath):
            os.makedirs(qipath)

        # save config file in QI
        cfgname = "_".join([outdir, 'INFO']) + '.cfg'
        cfgpath = os.path.join(tsdir, 'QI', cfgname)
        S2L_config.config.savetofile(os.path.join(S2L_config.config.get('wd'), pd.name, cfgpath))

        # save correl file in QI
        if os.path.exists(os.path.join(S2L_config.config.get('wd'), pd.name, 'correl_res.txt')):
            corrname = "_".join([outdir, 'CORREL']) + '.csv'
            corrpath = os.path.join(tsdir, 'QI', corrname)
            shutil.copy(os.path.join(S2L_config.config.get('wd'), pd.name, 'correl_res.txt'), corrpath)

        if len(self.images.keys()) > 1:
            # true color QL
            band_list = ["B04", "B03", "B02"]
            qlname = "_".join([metadata.mtd.get('band_rootName_F'), 'QL', 'B432']) + '.jpg'
            qlpath = os.path.join(qi_dir, qlname)
            quicklook(pd, self.images, band_list, qlpath, S2L_config.config.get("quicklook_jpeg_quality", 95))
            metadata.mtd.get('quicklooks_F').append(qlpath)

            # false color QL
            band_list = ["B12", "B11", "B8A"]
            qlname = "_".join([metadata.mtd.get('band_rootName_F'), 'QL', 'B12118A']) + '.jpg'
            qlpath = os.path.join(qi_dir, qlname)
            quicklook(pd, self.images, band_list, qlpath, S2L_config.config.get("quicklook_jpeg_quality", 95))
            metadata.mtd.get('quicklooks_F').append(qlpath)
        else:
            # grayscale QL
            band_list = list(self.images.keys())
            qlname = "_".join([metadata.mtd.get('band_rootName_F'), 'QL', band_list[0]]) + '.jpg'
            qlpath = os.path.join(qi_dir, qlname)
            quicklook(pd, self.images, band_list, qlpath, S2L_config.config.get("quicklook_jpeg_quality", 95))
            metadata.mtd.get('quicklooks_F').append(qlpath)

        # Copy fusion auto check threshold mask
        if pd.fusion_auto_check_threshold_msk_file is not None:
            outfile = "_".join([metadata.mtd.get('band_rootName_F'), 'FCM']) + '.TIF'
            fpath = os.path.join(qi_dir, outfile)
            shutil.copyfile(pd.fusion_auto_check_threshold_msk_file, fpath)
            metadata.mtd.get('quicklooks_F').append(fpath)

        # PVI
        band_list = ["B04", "B03", "B02"]
        pvi_filename = "_".join([metadata.mtd.get('band_rootName_F'), 'PVI']) + '.TIF'
        qlpath = os.path.join(qi_dir, pvi_filename)
        quicklook(pd, self.images, band_list, qlpath, S2L_config.config.get("quicklook_jpeg_quality", 95), xRes=320,
                  yRes=320,
                  creationOptions=['COMPRESS=LZW'], format='GTIFF')
        metadata.mtd.get('quicklooks_F').append(qlpath)

        # Clear images as packager is the last process
        self.images.clear()

        # Write QI report as XML
        bb_QI_path = metadata.hardcoded_values.get('bb_QIF_path')
        out_QI_path = os.path.join(qi_dir, 'L2F_QI_Report.xml')
        if pd.mtl.l2a_qi_report_path is not None:
            log.info(f'QI report for input product found here : {pd.mtl.l2a_qi_report_path}')
        Qi_Writer = QiWriter(bb_QI_path, outfile=out_QI_path, init_QI_path=pd.mtl.l2a_qi_report_path, H_F='F')
        Qi_Writer.manual_replaces(pd)
        Qi_Writer.write(pretty_print=True, json_print=False)
        # TODO UNCOMMENT BELOW FOR XSD CHECK
        product_QI_xsd = metadata.hardcoded_values.get('product_QIF_xsd')
        log.info('QI Report is valid : {}'.format(Qi_Writer.validate_schema(product_QI_xsd, out_QI_path)))

        # Write tile MTD
        bb_S2_tile = metadata.hardcoded_values.get('bb_S2F_tile')
        bb_L8_tile = metadata.hardcoded_values.get('bb_L8F_tile')
        tile_mtd_path = 'MTD_TL_L2F.xml'
        tile_MTD_outpath = os.path.join(product_path, 'GRANULE', granule_compact_name, tile_mtd_path)

        mtd_tl_writer = MTD_tile_writer_S2(bb_S2_tile, pd.mtl.tile_metadata, H_F='F') if pd.sensor == 'S2' \
            else MTD_tile_writer_LS8(bb_L8_tile, H_F='F')
        mtd_tl_writer.manual_replaces(pd)

        mtd_tl_writer.write(tile_MTD_outpath, pretty_print=True)
        # TODO UNCOMMENT BELOW FOR XSD CHECK
        # product_tl_xsd = metadata.hardcoded_values.get('product_tl_xsd')
        # log.info('Tile MTD is valid : {}'.format(mtd_tl_writer.validate_schema(product_tl_xsd, tile_MTD_outpath)))

        # Write product MTD
        bb_S2_product = metadata.hardcoded_values.get('bb_S2F_product')
        bb_L8_product = metadata.hardcoded_values.get('bb_L8F_product')
        product_mtd_path = 'MTD_{}L2F.xml'.format(pd.mtl.sensor[0:3])  # MSI / OLI/ OLI_TIRS
        product_MTD_outpath = os.path.join(tsdir, product_name, product_mtd_path)
        mtd_pd_writer = MTD_writer_S2(bb_S2_product, pd.mtl.mtl_file_name, H_F='F') if pd.sensor == 'S2' \
            else MTD_writer_LS8(bb_L8_product, H_F='F')
        mtd_pd_writer.manual_replaces(pd)
        mtd_pd_writer.write(product_MTD_outpath, pretty_print=True)
        # TODO UNCOMMENT BELOW FOR XSD CHECK
        # product_mtd_xsd = metadata.hardcoded_values.get('product_mtd_xsd')
        # log.info('Product MTD is valid : {}'.format(mtd_pd_writer.validate_schema(product_mtd_xsd, product_MTD_outpath)))

        # Write stac
        stac_writer = STACWriter()
        stac_writer.write_product(pd, os.path.join(tsdir, product_name), metadata.mtd['bands_path_F'],
                                  f"{metadata.mtd['band_rootName_F']}_QL_B432.jpg", granule_compact_name)
        log.info('End postprocess')

    def guard(self):
        """ Define required condition to algorithme execution
        """
        if S2L_config.config.getboolean('none_S2_product_for_fusion'):
            log.info("Fusion hase not been done. So s2l don't write L2F product.")
            return False
        return True
