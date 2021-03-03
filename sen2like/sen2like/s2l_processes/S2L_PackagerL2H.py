#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2020

import datetime as dt
import glob
import logging
import os
import shutil
from xml.etree import ElementTree

import core.QI_MTD.S2_structure
from core.QI_MTD.QIreport import QiWriter
from core.QI_MTD.generic_writer import find_element_by_path
from core.QI_MTD.mtd import metadata
from core.QI_MTD.mtd_writers import MTD_writer_S2, MTD_writer_LS8, MTD_tile_writer_S2, MTD_tile_writer_LS8
from core.S2L_config import config
from core.S2L_tools import quicklook
from core.image_file import S2L_ImageFile
from grids import mgrs_framing
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


class S2L_PackagerL2H(S2L_Process):
    images = {}

    def __init__(self):
        super().__init__()

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

        relative_orbit = config.get('relative_orbit')
        file_date = dt.datetime.strftime(product.file_date, '%Y%m%dT%H%M%S')  # generation time

        if product.sensor == 'S2':
            datatake_sensing_start = dt.datetime.strftime(product.dt_sensing_start, '%Y%m%dT%H%M%S')
            datastrip_sensing_start = dt.datetime.strftime(product.ds_sensing_start, '%Y%m%dT%H%M%S')
            absolute_orbit = config.get('absolute_orbit')
        else:
            datatake_sensing_start = dt.datetime.strftime(product.acqdate, '%Y%m%dT%H%M%S')
            datastrip_sensing_start = file_date
            absolute_orbit = metadata.hardcoded_values.get('L8_absolute_orbit')

        PDGS = metadata.hardcoded_values.get('PDGS')
        tilecode = product.mtl.mgrs
        if tilecode.startswith('T'):
            tilecode = tilecode[1:]

        sensor = product.mtl.sensor[0:3]  # OLI / MSI / OLI_TIRS
        product_name = "_".join([product.sensor_name, '{}L2H'.format(sensor), datatake_sensing_start, 'N' + PDGS,
                                 'R{:0>3}'.format(relative_orbit), 'T' + tilecode, file_date]) + '.SAFE'
        granule_compact_name = "_".join(['L2H', 'T' + tilecode, 'A' + absolute_orbit, datastrip_sensing_start,
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

        product_name, granule_compact_name, tilecode, _ = self.base_path_S2L(product)
        metadata.mtd['product_H_name'] = product_name
        metadata.mtd['granule_H_name'] = granule_compact_name
        metadata.mtd['product_creation_date'] = metadata.mtd.get('product_creation_date', dt.datetime.now())
        outdir = os.path.join(config.get('archive_dir'), tilecode)

        """
        # Creation of S2 folder tree structure
        tree = core.QI_MTD.S2_structure.generate_S2_structure_XML(out_xml='', product_name=product_name,
                                                           tile_name=granule_compact_name, save_xml=False)
        core.QI_MTD.S2_structure.create_architecture(outdir, tree, create_empty_files=True)
        """

        log.debug('Create folder : ' + os.path.join(outdir, product_name))
        change_nodes = {'PRODUCT_NAME': product_name,
                        'TILE_NAME': granule_compact_name,
                        }
        core.QI_MTD.S2_structure.create_architecture(outdir, metadata.hardcoded_values.get('s2_struct_xml'),
                                                     change_nodes=change_nodes, create_empty_files=False)

    def process(self, pd, image, band):
        """
        Write final product in the archive directory
        'archive_dir' is defined in config.ini file
        Naming convention from Design Document
        :param pd: instance of S2L_Product class
        :param image: input instance of S2L_ImageFile class
        :param band: band being processed
        :return: output instance of instance of S2L_ImageFile class
        """

        # TODO : add production date?

        # /data/HLS_DATA/Archive/Site_Name/TILE_ID/S2L_DATEACQ_DATEPROD_SENSOR/S2L_DATEACQ_DATEPROD_SENSOR
        res = image.xRes
        product_name, granule_compact_name, tilecode, datatake_sensing_start = self.base_path_S2L(pd)
        sensor = pd.sensor_name
        relative_orbit = config.get('relative_orbit')
        native = band in ['B08', 'B10', 'B11'] if sensor == 'LS8' else \
            band in ['B05', 'B06', 'B07', 'B08']
        s2_band = pd.get_s2like_band(band)
        if not native:
            band = s2_band
        band_rootName = "_".join(
            ['L2H', 'T' + tilecode, datatake_sensing_start, sensor, 'R{:0>3}'.format(relative_orbit)])
        metadata.mtd['band_rootName_H'] = band_rootName

        outfile = "_".join([band_rootName, band, '{}m'.format(int(res))]) + '.TIF'
        # Naming convention from Sentinel-2-Products-Specification-Document (p294)

        tsdir = os.path.join(config.get('archive_dir'), tilecode)  # ts = temporal series
        newpath = self.band_path(tsdir, product_name, granule_compact_name, outfile, native=native)

        COG = config.getboolean('COG')

        log.debug('New: ' + newpath)
        image.write(creation_options=['COMPRESS=LZW'], filepath=newpath, COG=COG, band=band)
        metadata.mtd.get('bands_path_H').append(newpath)

        # declare output internally
        self.images[s2_band] = image.filepath
        # declare output in config file
        config.set('imageout_dir', image.dirpath)
        config.set('imageout_' + band, image.filename)

        return image

    def postprocess(self, pd):
        """
        Copy auxiliary files in the final output like mask, angle files
        Input product metadata file is also copied.
        :param pd: instance of S2L_Product class
        """

        # output directory
        product_name, granule_compact_name, tilecode, datatake_sensing_start = self.base_path_S2L(pd)

        tsdir = os.path.join(config.get('archive_dir'), tilecode)  # ts = temporal series
        outdir = product_name
        product_path = os.path.join(tsdir, outdir)
        qi_dir = os.path.join(product_path, 'GRANULE', granule_compact_name, 'QI_DATA')

        # copy angles file
        outfile = "_".join([metadata.mtd.get('band_rootName_H'), 'ANG']) + '.TIF'
        metadata.mtd['ang_filename'] = outfile
        shutil.copyfile(pd.mtl.angles_file, os.path.join(qi_dir, outfile))

        # copy mask files
        if "S2" in pd.sensor:
            tree_in = ElementTree.parse(pd.mtl.tile_metadata)  # Tree of the input mtd (S2 MTD.xml)
            root_in = tree_in.getroot()
            mask_elements = find_element_by_path(root_in, './Quality_Indicators_Info/Pixel_Level_QI/MASK_FILENAME')
            for element in mask_elements:
                mask_file = os.path.join(pd.path, element.text)
                if os.path.exists(mask_file):
                    shutil.copyfile(mask_file, os.path.join(qi_dir, os.path.basename(mask_file)))
                    metadata.mtd.get('masks_H').append({"tag": "MASK_FILENAME",
                                                        "attribs": element.attrib,
                                                        "text": element.text})

        # copy valid pixel mask
        outfile = "_".join([metadata.mtd.get('band_rootName_H'), pd.sensor, 'MSK']) + '.TIF'

        fpath = os.path.join(qi_dir, outfile)
        metadata.mtd.get('masks_H').append({"tag": "MASK_FILENAME",
                                            "attribs": {"type": "MSK_VALPIX"},
                                            "text": os.path.relpath(fpath, product_path)})

        if config.getboolean('COG'):
            img_object = S2L_ImageFile(pd.mtl.mask_filename, mode='r')
            img_object.write(filepath=fpath, COG=True, band='MASK')
        else:
            shutil.copyfile(pd.mtl.mask_filename, fpath)

        # QI directory
        qipath = os.path.join(tsdir, 'QI')
        if not os.path.exists(qipath):
            os.makedirs(qipath)

        # save config file in QI
        cfgname = "_".join([outdir, 'INFO']) + '.cfg'
        cfgpath = os.path.join(tsdir, 'QI', cfgname)
        config.savetofile(os.path.join(config.get('wd'), pd.name, cfgpath))

        # save correl file in QI
        if os.path.exists(os.path.join(config.get('wd'), pd.name, 'correl_res.txt')):
            corrname = "_".join([outdir, 'CORREL']) + '.csv'
            corrpath = os.path.join(tsdir, 'QI', corrname)
            shutil.copy(os.path.join(config.get('wd'), pd.name, 'correl_res.txt'), corrpath)

        if len(self.images.keys()) > 1:
            # true color QL
            band_list = ["B04", "B03", "B02"]
            qlname = "_".join([metadata.mtd.get('band_rootName_H'), 'QL', 'B432']) + '.jpg'
            qlpath = os.path.join(qi_dir, qlname)
            quicklook(pd, self.images, band_list, qlpath, config.get("quicklook_jpeg_quality", 95))
            metadata.mtd.get('quicklooks_H').append(qlpath)

            # false color QL
            band_list = ["B12", "B11", "B8A"]
            qlname = "_".join([metadata.mtd.get('band_rootName_H'), 'QL', 'B12118A']) + '.jpg'
            qlpath = os.path.join(qi_dir, qlname)
            quicklook(pd, self.images, band_list, qlpath, config.get("quicklook_jpeg_quality", 95))
            metadata.mtd.get('quicklooks_H').append(qlpath)
        else:
            # grayscale QL
            band_list = list(self.images.keys())
            qlname = "_".join([metadata.mtd.get('band_rootName_H'), 'QL', band_list[0]]) + '.jpg'
            qlpath = os.path.join(qi_dir, qlname)
            quicklook(pd, self.images, band_list, qlpath, config.get("quicklook_jpeg_quality", 95))
            metadata.mtd.get('quicklooks_H').append(qlpath)

        # PVI
        band_list = ["B04", "B03", "B02"]
        pvi_filename = "_".join([metadata.mtd.get('band_rootName_H'), 'PVI']) + '.TIF'
        qlpath = os.path.join(qi_dir, pvi_filename)
        quicklook(pd, self.images, band_list, qlpath, config.get("quicklook_jpeg_quality", 95), xRes=320, yRes=320,
                  creationOptions=['COMPRESS=LZW'], format='GTIFF')
        metadata.mtd.get('quicklooks_H').append(qlpath)

        # Clear images as packager is the last process
        self.images.clear()

        # Write QI report as XML
        bb_QI_path = metadata.hardcoded_values.get('bb_QIH_path')
        out_QI_path = os.path.join(qi_dir, 'L2H_QI_Report.xml')
        in_QI_path = glob.glob(os.path.join(pd.path, 'GRANULE', '*', 'QI_DATA', 'L2A_QI_Report.xml'))
        log.info('QI report for input product found : {} (searched at {})'.format(len(in_QI_path) != 0,
                                                                                  os.path.join(pd.path, 'GRANULE', '*',
                                                                                               'QI_DATA',
                                                                                               'L2A_QI_Report.xml')))

        in_QI_path = in_QI_path[0] if len(in_QI_path) != 0 else None

        Qi_Writer = QiWriter(bb_QI_path, outfile=out_QI_path, init_QI_path=in_QI_path, H_F='H')
        Qi_Writer._manual_replaces(pd)
        Qi_Writer.write(pretty_print=True)
        # TODO UNCOMMENT BELOW FOR XSD CHECK
        product_QI_xsd = metadata.hardcoded_values.get('product_QIH_xsd')
        log.info('QI Report is valid : {}'.format(Qi_Writer.validate_schema(product_QI_xsd, out_QI_path)))

        # Write product MTD
        bb_S2_product = metadata.hardcoded_values.get('bb_S2H_product')
        bb_L8_product = metadata.hardcoded_values.get('bb_L8H_product')
        product_mtd_path = 'MTD_{}L2H.xml'.format(pd.mtl.sensor[0:3])  # MSI / OLI/ OLI_TIRS
        product_MTD_outpath = os.path.join(tsdir, product_name, product_mtd_path)
        mtd_pd_writer = MTD_writer_S2(bb_S2_product, pd.mtl.mtl_file_name, H_F='H') if pd.sensor == 'S2' \
            else MTD_writer_LS8(bb_L8_product, H_F='H')
        mtd_pd_writer._manual_replaces(pd)
        mtd_pd_writer.write(product_MTD_outpath, pretty_print=True)
        # TODO UNCOMMENT BELOW FOR XSD CHECK
        # product_mtd_xsd = metadata.hardcoded_values.get('product_mtd_xsd')
        # log.info('Product MTD is valid : {}'.format(mtd_pd_writer.validate_schema(product_mtd_xsd,
        #                                                                           product_MTD_outpath)))

        # Write tile MTD
        bb_S2_tile = metadata.hardcoded_values.get('bb_S2H_tile')
        bb_L8_tile = metadata.hardcoded_values.get('bb_L8H_tile')
        tile_mtd_path = 'MTD_TL_L2H.xml'
        tile_MTD_outpath = os.path.join(product_path, 'GRANULE', granule_compact_name, tile_mtd_path)

        mtd_tl_writer = MTD_tile_writer_S2(bb_S2_tile, pd.mtl.tile_metadata, H_F='H') if pd.sensor == 'S2' \
            else MTD_tile_writer_LS8(bb_L8_tile, H_F='H')
        mtd_tl_writer._manual_replaces(pd)
        mtd_tl_writer.write(tile_MTD_outpath, pretty_print=True)
        # TODO UNCOMMENT BELOW FOR XSD CHECK
        # product_tl_xsd = metadata.hardcoded_values.get('product_tl_xsd')
        # log.info('Tile MTD is valid : {}'.format(mtd_tl_writer.validate_schema(product_tl_xsd, tile_MTD_outpath)))
