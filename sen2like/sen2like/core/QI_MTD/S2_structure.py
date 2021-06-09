#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2020

"""
Script to create S2 like folder structure xml
Architecture is chosen using PSD schemas attached from
https://sentinel.esa.int/documents/247904/685211/Sentinel-2-Products-Specification-Document
"""

import os
import sys
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, Comment

sys.path.append('../..')


def generate_S2_structure_XML(out_xml, product_name=None, tile_name=None, save_xml=False):
    """
    Generates an XML containing the structure of a S2 folder : folders and files to be included
    Structure based on 3 xsd files which were extracted from
    https://sentinel.esa.int/documents/247904/685211/Sentinel-2-Products-Specification-Document
        - S2_User_Product_Level-2A_Structure.xsd   (General structure)
        - S2_PDI_Level-2A_Tile_Structure.xsd       (Structure of the GRANULE folder)
        - S2_PDI_Level-2A_Datastrip_Structure.xsd  (Structure of the DATASTRIP folder)

    :param out_xml: path to output xml
    :param product_name:
    :param tile_name:
    :param save_xml:
    """

    product_name = product_name if product_name else 'PRODUCT_NAME'
    root = Element(product_name)
    root.append(Comment(
        'Product name convention : https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi/naming-convention'))

    # Folders to create in the root folder, following  2_User_Product_Level-2A_Structure.xsd
    SubElement(root, 'AUX_DATA', attrib={'type': 'folder'})
    SubElement(root, 'DATASTRIP', attrib={'type': 'folder'})
    SubElement(root, 'rep_info', attrib={'type': 'folder'})

    html = SubElement(root, 'HTML', attrib={'type': 'folder'})
    html.append(Comment('Folder containing a product presentation html file'))

    granule = SubElement(root, 'GRANULE', attrib={'type': 'folder'})
    granule.append(Comment('Folder containing the Tiles composing the product'))

    # Files to create in the root folder
    inspire = SubElement(root, 'INSPIRE.xml', attrib={'type': 'file'})
    inspire.append(Comment('XML INSPIRE metadata file'))
    manifest = SubElement(root, 'manifest.safe', attrib={'type': 'file'})
    manifest.append(Comment('XML manifest file (SAFE)'))
    mtd = SubElement(root, 'Product_Metadata_File', attrib={'type': 'file'})
    mtd.append(Comment('XML Main Metadata File'))

    # Files/folders to append to the GRANULE folder
    tile_name = tile_name if tile_name else 'TILE_NAME'
    tile_granule = SubElement(granule, tile_name, attrib={'type': 'folder'})
    img_data_granule = SubElement(tile_granule, 'IMG_DATA', attrib={'type': 'folder'})
    qi_data_granule = SubElement(tile_granule, 'QI_DATA', attrib={'type': 'folder'})
    aux_data_granule = SubElement(tile_granule, 'AUX_DATA', attrib={'type': 'folder', 'optional': 'True'})
    aux_data_granule.append(Comment('Folder containing ECMWF data resampled in UTM projection'))

    # Creation of the GRANULE tile structure
    append_tile_structure(img_data_granule, qi_data_granule, aux_data_granule)

    # Creation of the DATASTRIP structure
    # append_datastrip_structure(datastrip)  # No datastrip folder, finally

    # XML creation
    tree = ElementTree.ElementTree(element=root)
    if save_xml:
        tree.write(out_xml)

    return tree


def append_tile_structure(img_data: Element, qi_data: Element, aux_data: Element):
    """
     Create the structure for granule tile defined as in 'S2_PDI_Level-2A_Tile_Structure.xsd' and appends it
     to the tile element of the xml tree
    :param img_data:  Element for the IMG_DATA folder  inside the GRANULE folder
    :param qi_data:      "            QI_DATA                     "
    :param aux_data:     "            AUX_DATA                    "
    :return:
    """

    # Files/folders to append to AUX_DATA
    ecmwf = SubElement(aux_data, 'ECMWF_Meteorological_file', attrib={'type': 'file'})
    ecmwf.append(Comment('Metetorological data in GRIB format resampled in UTM projection'))
    dem = SubElement(aux_data, 'DEM', attrib={'type': 'file', 'optional': 'True'})
    dem.append(Comment('MOptional Digital Elevation Map resampled to image data resolution'))

    # Files/folders to append to IMG_DATA
    SubElement(img_data, 'All_11_S2_CHANNELS', attrib={'type': 'file'})
    SubElement(img_data, 'Aerosol_Optical_Thickness_map', attrib={'type': 'file'})
    SubElement(img_data, 'Water_Vapor_Map', attrib={'type': 'file'})
    SubElement(img_data, 'TCI_channel', attrib={'type': 'file', 'optional': 'True'})
    SubElement(img_data, 'NATIVE', attrib={'type': 'folder'})

    # Files to append to QI_DATA
    SubElement(qi_data, 'OLQC_reports_XML_formatted', attrib={'type': 'file'})
    SubElement(qi_data, 'GML_Quality_Mask_files', attrib={'type': 'file'})
    cloud_c = SubElement(qi_data, 'Cloud_Confidence', attrib={'type': 'file'})
    cloud_c.append(Comment(
        'Raster mask values range from 0 for high confidence clear sky to 100 for high confidence cloudy. '
        'Unsigned Integer. JPEG2000. 8bit. available at 20m and 60m resolution.'))
    snow_ice_c = SubElement(qi_data, 'Snow_Ice_Confidence', attrib={'type': 'file'})
    snow_ice_c.append(Comment(
        'Raster mask values range from 0 for high confidence NO snow/ice to 100 for high confidence snow/ice. '
        'Unsigned Integer. JPEG2000. 8bit. available at 20m and 60m resolution.'))
    preview_image = SubElement(qi_data, 'Preview_Image', attrib={'type': 'file', 'optional': 'True'})
    preview_image.append(Comment('L2A PVI Preview Image file 343 x 343 pixels'))
    ddv_pixels = SubElement(qi_data, 'DDV_pixels', attrib={'type': 'file'})
    ddv_pixels.append(
        Comment('Raster mask of Dark Dense Vegetation pixels used during AOT retrieval processing (optional)'))


def append_datastrip_structure(datastrip: Element):
    """
     Create the structure for DATASTRIP folder as defined in 'S2_PDI_Level-2A_Datastrip_Structure.xsd' and appends it
     to the datastrip element of the xml tree
    :param datastrip:  Element for the DATASTRIP folder
    :return:
    """

    datastrip_folder = SubElement(datastrip, 'DATASTRIP_NAME', attrib={'type': 'folder'})
    datastrip_folder.append(Comment(
        'Naming convention from '
        'https://sentinel.esa.int/documents/247904/685211/Sentinel-2-Products-Specification-Document at p74, p438'))

    SubElement(datastrip_folder, 'DataStrip_Metadata_File', attrib={'type': 'file'})

    qi_data = SubElement(datastrip_folder, 'QI_DATA', attrib={'type': 'folder'})
    oqlc = SubElement(qi_data, 'OLQC', attrib={'type': 'file'})
    oqlc.append(Comment('OLQC reports XML formatted'))


def create_architecture(out_folder: str, structure_xml_path, change_nodes: dict = None, create_empty_files=True):
    """
    Create the architecture defined in the xml file (or tree if a tree is provided as input
    :param out_folder:
    :param structure_xml_path: Etree.Elementtree or str path to xml
    :param change_nodes:
    :param create_empty_files:
    :return:
    """
    if change_nodes is None:
        change_nodes = {}
    os.makedirs(out_folder, exist_ok=True)

    # Inputs type tree or path to xml
    if type(structure_xml_path) == str:
        tree = ElementTree.parse(os.path.join(os.path.dirname(__file__), structure_xml_path))
    else:
        tree = structure_xml_path

    root = tree.getroot()

    for key, tag in change_nodes.items():
        if root.iter(key):
            root.iter(key).__next__().tag = tag

    product_path = os.path.join(out_folder, root.tag)
    create_children(root, root.tag, product_path, create_empty_files)


def create_children(root: Element, rpath: str, save_path: str, create_empty_files=True):
    """
    Creates all elements (folders and files) contained in the root element
    :param root:                Root of the tree
    :param rpath:               Relative path inside the structure
    :param save_path:           Path to save the S2 folder
    :param create_empty_files:  Whether to create files or not (to get the full S2 structure)
    :return:
    """
    children = root.findall('./')
    for child in children:
        if isinstance(child.tag, str):  # Removing <function Comment>
            child_rpath = os.path.join(rpath, child.tag)
            child_save_path = os.path.join(save_path, child.tag)
            if child.attrib['type'].lower() == 'folder':
                os.makedirs(child_save_path, exist_ok=True)
            elif child.attrib['type'].lower() == 'file' and create_empty_files:
                with open(child_save_path, 'w'):
                    pass

            create_children(child, child_rpath, child_save_path, create_empty_files)
