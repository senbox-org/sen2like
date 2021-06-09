#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2020

import copy
import json
import logging
import os
import re
import sys
import xml
import xml.dom.minidom
from typing import Union
from xml import parsers as pars
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import xmlschema
import xmltodict

from grids import grids

log = logging.getLogger('Sen2Like')


class MtdWriter:
    """
    Generic xml writer.
    """

    def __init__(self, backbone_path: str, init_MTD_path: Union[str, None], H_F: str):
        """
        :param backbone_path: path of the .xml backbone
        :param init_MTD_path: path of the .xml file of the input product, if exists. Can be None
        :param H_F:           Product level (H or F)
        """
        self.root_in = None
        backbone_path = os.path.join(os.path.dirname(__file__), backbone_path)
        if not os.path.exists(backbone_path):
            log.error('MTD backbone {} does not exist'.format(backbone_path))
            return
        if init_MTD_path and not os.path.exists(init_MTD_path):
            log.error('Input product MTD {} does not exist'.format(init_MTD_path))
            return

        self.backbone_path = backbone_path
        self.init_MTD_path = init_MTD_path

        try:
            tree_bb = ElementTree.parse(backbone_path)  # Tree backbone for the output file. Will not be changed
            self.root_bb = tree_bb.getroot()

            if init_MTD_path and not init_MTD_path.endswith('.txt'):
                tree_in = ElementTree.parse(init_MTD_path)  # Tree of the input mtd (S2 MTD.xml, L2A_QI_report.xml)
                self.root_in = tree_in.getroot()
            else:
                self.root_in = None

        except pars.expat.ExpatError as err:
            logging.error("Error during parsing of MTD product file: %s" % backbone_path)
            logging.error(err)
            sys.exit(-1)

        self.root_out = copy.deepcopy(self.root_bb)  # Tree which will be modified and saved
        self.outfile = None

        self.H_F = H_F  # Product level (H or F)

    def manual_replaces(self, product):
        pass

    def remove_children(self, root, tag: str = '', attrs: dict = None, exceptions: list = None):
        """
        Removes direct children from a node. Conditions can be added on tag and attributes
        Usage example :
        remove_children('./Data_Block/report/checkList[parentID="L2H_SBAF"]/check/extraValues',
                         tag='value', attrs= {'name': 'SBAF_'})

        :param root:  Element or path to element
        :param tag:   If provided, only elements with this tag will be removed
        :param attrs: If provided, only elements matching with these attributes will be removed
        :param exceptions:   Will not remove ,nodes with tag in exception
        :return: namespace of removed Element
        """
        if isinstance(root, xml.etree.ElementTree.Element):
            parents = [root]
        elif isinstance(root, str):
            parents = find_element_by_path(self.root_out, root)
        else:
            log.error('root must be str or Element')
            return

        if attrs is None:
            attrs = {}

        ns = ''
        for parent in parents:
            for elem in parent.findall('./'):
                node_name, ns = remove_namespace(elem.tag)
                if exceptions and node_name in exceptions:
                    continue

                if not attrs and tag in elem.tag:
                    parent.remove(elem)
                elif all([val in elem.get(key) for key, val in attrs.items()]) and tag in elem.tag:
                    parent.remove(elem)
        return ns

    def validate_schema(self, xsd_path, xml_file=None):
        """
        Validates an xml file with respect to given .xsd
        :param xsd_path:
        :param xml_file:
        :return:
        """
        xml_file = xml_file if xml_file else self.outfile
        schema = xmlschema.XMLSchema(os.path.join(os.path.dirname(__file__), xsd_path))
        return schema.is_valid(xml_file)

    def write(self, outfile: str = None, pretty_print=True, json_print=True):
        """
        Writes self.root_out in an .xml file
        :param outfile:
        :param pretty_print:
        :return:
        """
        outpath = outfile if outfile else self.outfile
        if not outpath:
            log.error('No outpath provided for QI report')
        elif pretty_print:
            write_pretty_format(outpath, self.root_out)
        else:
            # XML creation
            tree = ElementTree.ElementTree(element=self.root_out)
            tree.write(outpath, encoding='UTF-8', xml_declaration=True)

        if json_print:
            write_json(outpath)


def find_element_by_path(root: Element, path_to_match: str):
    """
    Find all elements matching with path_to_match in the root element
    Support Xpath attrib and value assignement
    :param root:
    :param path_to_match:
    :return:
    """
    updated_path = get_final_path(root, path_to_match)
    children = root.findall(updated_path)

    return children


def get_final_path(root: Element, path_to_match: str):
    """
    Appends corresponding namespaces in a path without any namespaces.
    :param root:            root from where matching the element  to 'path_to_match' is.
    :param path_to_match:
    :return:
    """

    nodes = path_to_match.split('/')
    final_nodes = nodes

    for i, node_path in enumerate(nodes):
        if node_path == '.':
            continue
        path = '/'.join([node for node in final_nodes[0:i + 1]])
        adjusted_node = adjust_node(root, path, node_path)
        final_nodes[i] = adjusted_node

    return '/'.join(final_nodes)


def adjust_node(root: Element, path: str, node_to_match: str):
    """
    Adjusts a node tag from .../node_tag/... to .../{namespace}node_tag/...
    Allows to use paths without namespaces in queries
    :param root:
    :param path:
    :param node_to_match:
    :return:
    """
    ns_path = node_to_match
    parents = root.findall('/'.join(path.split('/')[:-1]))
    for parent in parents:
        children = list(parent)
        for child in children:
            if node_to_match.split('[')[0] in child.tag:
                _, namespace = remove_namespace(child.tag)
                ns_path = append_namespace_to_path(node_to_match, namespace)
                return ns_path
    return ns_path


def get_idx(root, elem):
    parent = getParentObjectNode(root, elem)
    for i, child in enumerate(parent.findall('./')):
        if child == elem:
            return i


def append_namespace_to_path(path, namespace):
    """
    Append the namespace to all subelement of the path
    Put namespace in tags and tags conditions (Xpath), but not in the attributes conditions
    :param path:
    :param namespace:
    :return:
    """

    last_char = '/' if path.endswith('/') else ''
    first_char = './' if path.startswith('./') else ''

    ns_path = path.lstrip('./').rstrip('/').split('/')
    for i, sub_path in enumerate(ns_path):
        if not sub_path.startswith('['):
            ns_path[i] = namespace + sub_path

    ns_path = '/'.join([sub_path for sub_path in ns_path if sub_path])
    ns_path = first_char + ns_path + last_char

    # Replace tags but not attribs, which do not have namespaces
    ns_path = ns_path.replace('[@', '@123456789@')
    ns_path = ns_path.replace('[', '[' + namespace)
    ns_path = ns_path.replace('@123456789@', '[@')

    return ns_path


def getParentObjectNode(root: Element, node: Element):
    for elem in root.iter('*'):
        if node in list(elem):
            return elem
    return None


def get_elem_path(root: Element, node: Element, rm_ns=False):
    """
    Given an element, find its path in the tree
    :param root:  Full tree
    :param node:  Node we need the path
    :param rm_ns: Whether to return path with or without namespaces
    :return:
    """
    tag, _ = remove_namespace(node.tag)
    path = node.tag if rm_ns else tag
    parent = getParentObjectNode(root, node)
    while parent is not None:
        tag, _ = remove_namespace(parent.tag)
        path = os.path.join(tag, path) if rm_ns else os.path.join(parent.tag, path)
        parent = getParentObjectNode(root, parent)
    return path


def remove_namespace(tag):
    """
    Removes the namespace before an element tag
    Example of tag with namespace : {http://gs2.esa.int/DATA_STRUCTURE/l2aqiReport}L2A_Quality_File
    :param tag:
    :return:
    """

    m = re.match(r'\{.*\}', tag)
    namespace = m.group(0) if m else ''
    node_name = tag.replace(namespace, '')

    return node_name, namespace


def search_db(tilecode, search):
    """
    Searchs the db for specific values
    :param tilecode:
    :param search:    ex : 'MGRS_REF', 'EPSG'
    :return:
    """
    converter = grids.GridsConverter()
    roi = converter.getROIfromMGRS(tilecode)
    converter.close()
    return roi[search][0]


def chg_elm_with_tag(root: Element, tag: str, new_value: str, attrs: dict = None):
    """
    Searchs in the tree all elements with a particular tag, and replaces its value
    :param root:      Element from xml tree
    :param tag:       Elements with this tag will have their text replaced
    :param new_value: New text value
    :param attrs :     If provided, adds a constraint on the element to find (attributes must match)
    :return:
    """
    for elem in root.iter('*'):
        node_space, _ = remove_namespace(elem.tag)
        if node_space == tag:
            if not attrs:
                elem.text = str(new_value)
            elif attrs.items() <= elem.attrib.items():
                elem.text = str(new_value)


def change_elm(root: Element, rpath: str, new_value: str, attr_to_change: str = None):
    """
    Changes the text or the attribute's value of a particular element
    :param root:
    :param rpath:             relative path of the element in the root
    :param new_value:
    :param attr_to_change:    If provided, the changed value will be the attribute's one
    :return:
    """
    elements = find_element_by_path(root, rpath)
    if not elements:
        log.warning('(fn change_elm) No element found with this path : {} '.format(rpath) +
                    'Can\'t change its value to {}'.format(new_value))
    # if len(elements) > 1:
    #     log.info('(fn change_elm) Multiple elements found with this path : {}'.format(rpath) +
    #              'The value will be changed for all these elements')

    for elem in elements:
        if attr_to_change:
            elem.attrib[attr_to_change] = new_value
        else:
            elem.text = new_value


def copy_children(root_in: Element, ini_rpath: str, root_out: Element, out_rpath: str):
    """
    Copies all children from root_in's element to root_out's one
    :param root_in:
    :param ini_rpath:
    :param root_out:
    :param out_rpath:
    :return:
    """
    out_elem = find_element_by_path(root_out, out_rpath)
    ini_elem = find_element_by_path(root_in, ini_rpath)

    if len(out_elem) != 1 or len(ini_elem) != 1:
        return
    out_elem = out_elem[0]
    ini_elem = ini_elem[0]

    for idx, child in enumerate(list(ini_elem)):
        out_elem.insert(idx, child)

    replace_namespace_recursively(out_elem, root_out)


def replace_namespace(elem: Element, root_bb: Element):
    """
    Finds in the root_bb the corresponding 'element' to elem, and changes elem's namespace with the 'element's one
    :param elem:
    :param root_bb:
    :return:
    """
    tag, namespace = remove_namespace(elem.tag)
    for e in root_bb.iter('*'):
        e_tag, bb_ns = remove_namespace(e.tag)
        if e_tag == tag and e.attrib == elem.attrib and namespace and bb_ns:
            elem.tag = bb_ns + tag


def replace_namespace_recursively(root: Element, root_bb: Element):
    for elem in root.iter('*'):
        replace_namespace(elem, root_bb)


def create_child(root: Element, rpath: str, tag: str, text: str = None, attribs: dict = None):
    """
    Usage example:
    create_child(root_out, rpath='./General_Info/Product_Info/Product_Organisation/Granule_List/Granule',
                 tag='IMAGE_FILE', text='trololo')
    :param root:
    :param rpath:    relative path of the element in the root
    :param tag:      Tag to give to the created node
    :param text:     Text to give to the created node
    :param attribs:  Attributes to give to the created node. Ex:   {'type':'GIP_S2L'}
    :return:
    """
    if attribs is None:
        attribs = {}

    parent_elm = find_element_by_path(root, rpath)
    if len(parent_elm) > 1 or len(parent_elm) == 0:
        log.warning('(fn create_child) Multiple or 0 elements found with this path {}'.format(rpath) +
                    'Will not create element under')

    child = xml.etree.ElementTree.SubElement(parent_elm[0], tag, attrib=attribs)
    child.text = text


def copy_elements(elements_to_copy: list, root_in, root_out, root_bb=None):
    """
    Finds matching elements in elements_to_copy, and replaces them in the root_out.
    Waring : it replaces the elements, so root_out's children may be lost if they are not in root_in
    Supports some xpath queries.
    :param elements_to_copy:  List of paths to the nodes we want to copy from the initial MTD file
    :param root_in:   Root from where we want to copy elements
    :param root_out:  Root from where elements will be changed
    :param root_bb:   If provided, changes namespaces to root_bb's ones
    :return:
    """
    for elem_path in elements_to_copy:

        out_elems = find_element_by_path(root_out, elem_path)
        ini_elems = find_element_by_path(root_in, elem_path)
        if len(out_elems) == 0 or len(ini_elems) == 0:
            log.warning('(fn copy_elements) No matching elements found for {}'.format(elem_path))
            continue
        if len(out_elems) == len(ini_elems):
            if len(out_elems) > 1:
                log.warning('(fn copy_elements) multiple matching elements found for {}'.format(elem_path) +
                            'They will be copied in the encountered order')
            for out_elem, ini_elem in zip(out_elems, ini_elems):
                parent = getParentObjectNode(root_out, out_elem)
                idx = get_idx(parent, out_elem)
                parent.remove(out_elem)
                new_elem = copy.copy(ini_elem)
                parent.insert(idx, new_elem)

                if root_bb is not None:
                    replace_namespace_recursively(new_elem, root_bb)


def rm_elm_with_tag(root: Element, tag: str, attrs: dict = None):
    """
    Searchs in the tree all elements with a particular tag, and removes it
    If multiple elements match, all are removed
    :param root:      Element from xml tree
    :param tag:       Elements with this tag will have their text replaced
    :param attrs :     If provided, adds a constraint on the element to find (attributes must match)
    :return:
    """
    for elem in root.iter('*'):
        for child in list(elem):
            node_name, _ = remove_namespace(child.tag)
            if tag == node_name:
                if not attrs:
                    elem.remove(child)
                elif attrs.items() <= elem.attrib.items():
                    elem.remove(child)


def write_pretty_format(outfile: str, root: Element = None):
    """
    Writes an xml with pretty format.
    :param outfile: Outfile path. If root element is not provided, 'outfile' is also the input file which will be parsed
    :param root:
    :return:
    """

    if root is not None:
        dom = xml.dom.minidom.parseString(ElementTree.tostring(root))
    else:
        dom = xml.dom.minidom.parse(outfile)

    pretty = dom.toprettyxml()
    tree = xml.dom.minidom.parseString(pretty)

    with open(outfile, 'w') as fout:
        tree.writexml(fout, indent="", addindent="", newl="", encoding='UTF-8')

    # Split header and root node, and remove blank lines
    with open(outfile, 'r') as fin:
        lines = fin.readlines()
    with open(outfile, 'w') as fout:
        for line in lines:
            search = re.search(r'<(.*?)>', line)
            if search and '?xml version' in search.group() and 'encoding=' in search.group():
                line = line.replace(search.group(), search.group() + '\n')
            if not (len(set(line)) <= 3 and '\n' in set(line)):  # Remove lines with only {'\n', '\t', ' '}
                fout.write(line)


def write_json(xml_file: str):
    """
    Writes a json file with with metadata.
    :param xml_file: xml metadata file path.
    """
    json_file = f'{os.path.splitext(xml_file)[0]}.json'
    log.info('Writing metadata as json')
    xml_content = ''
    with open(xml_file) as p_xml:
        xml_content = xmltodict.parse(p_xml.read())
    with open(json_file, 'w') as fp:
        json.dump(xml_content, fp, indent=4)
    log.info('Json file writed: {}'.format(json_file))
