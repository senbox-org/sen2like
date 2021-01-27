#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2018

import xml
import os
import re
import copy
from xml.etree.ElementTree import Element


def find_element_by_path(root, path_to_match):
    """.
    Support Xpath attrib and value assignement
    :param root:
    :param path_to_match:
    :return:
    """

    updated_path = get_final_path(root, path_to_match)
    children = root.findall(updated_path)
    indexes = [get_idx(root, child) for child in children]

    return children, indexes


def adjust_node(root:Element, path:str, node_to_match:str):

    ns_path = node_to_match
    parents = root.findall('/'.join(path.split('/')[:-1]))
    for parent in parents:

        children = parent.getchildren()

        for child in children:
            if node_to_match.split('[')[0] in child.tag:
                _, namespace = remove_namespace(child.tag)
                ns_path = append_namespace_to_path(node_to_match, namespace)
                return ns_path
    return ns_path

def get_final_path(root, path_to_match):
    """
    Does not support namespace constraints inside the path
    :param root:
    :param path_to_match:
    :return:
    """

    nodes = path_to_match.split('/')
    final_nodes = nodes

    for i, node_path in enumerate(nodes):
        if node_path=='.':
            continue
        path = '/'.join([node for node in final_nodes[0:i + 1]])
        adjusted_node = adjust_node(root, path, node_path)
        final_nodes[i] = adjusted_node

    return '/'.join(final_nodes)


def get_idx(root, elem):
    parent = getParentObjectNode(root, elem)
    for i, child in enumerate(parent.findall('./')):
        if child == elem:
            return i


def append_namespace_to_path(path, namespace):
    """
    Append the namespace to all subelement of the path
    :param path:
    :param namespace:
    :return:
    """

    last_char = '/' if path.endswith('/') else ''
    first_char = './' if path.startswith('./') else ''

    ns_path = path.lstrip('./').rstrip('/').split('/')
    for i, sub_path in enumerate(ns_path):
        if not sub_path.startswith('['):
            ns_path[i] = namespace+sub_path

    ns_path = '/'.join([sub_path for sub_path in ns_path if sub_path ])
    ns_path = first_char + ns_path + last_char

    # Replace tags but not attribs, which do not have namespaces
    ns_path = ns_path.replace('[@', '@123456789@')
    ns_path = ns_path.replace('[', '['+namespace)
    ns_path = ns_path.replace('@123456789@', '[@')

    return ns_path


def getParentObjectNode(root:Element, node:Element):
    for elem in root.iter('*'):
        if node in list(elem):
            return elem
    return None


def get_elem_path(root:Element, node:Element, rm_ns=False):

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


def compare_nodes(node1:Element, node2:Element, rpath:str):
    """
    Compares recursively in the nodes which elements are in common, based on the tag
    :param node1:
    :param node2:
    :param rpath:
    :return:
    """

    common_nodes = []
    paths_to_nodes = []
    not_matched = []
    not_matched_paths = []

    children1 = node1.findall('./')
    children2 = node2.findall('./')

    for child1 in children1:
        matched = False
        tag1, _ = remove_namespace(child1.tag)
        child_rpath = os.path.join(rpath, tag1)
        # child_rpath = os.path.join(rpath, child1.tag)

        for child2 in children2:
            tag2, _ = remove_namespace(child2.tag)

            if tag1 == tag2:

                matched = True
                common_nodes.append(child2)
                paths_to_nodes.append(child_rpath)

                new_common_nodes, new_paths, new_not_matched, new_not_matched_paths = compare_nodes(child1, child2, child_rpath)
                common_nodes += new_common_nodes
                paths_to_nodes += new_paths
                not_matched += new_not_matched
                not_matched_paths += new_not_matched_paths

        if not matched:
            not_matched.append(child1)
            not_matched_paths.append(child_rpath)

    return common_nodes, paths_to_nodes, not_matched, not_matched_paths


def compare_trees(self):

    # Find wich elements are in the backbone, and also in the MTD of the used product
    common_nodes, path_to_nodes, not_matched, not_matched_paths = compare_nodes(self.root_bb, self.root_in, rpath='./')
    print('Matched :')
    [print(m) for m in set(path_to_nodes)]
    print('\nNot matched :')
    [print(m) for m in set(not_matched_paths)]
    print()

# @get_modifications
def chg_elm_with_tag(root: Element, tag: str, new_value: str, attrs: dict=None):
    """
    Searchs in the tree all elements with a particular tag, and replaces its value
    :param root:      Element from xml tree
    :param tag:       Elements with this tag will have their text replaced
    :param new_value: New text value
    :param attr :     If provided, adds a constraint on the element to find (attributes must match)
    :return:
    """
    changed = []
    for elem in root.iter('*'):
        node_space, _ = remove_namespace(elem.tag)
        if node_space == tag:
            if not attrs:
                elem.text = str(new_value)
                changed.append(elem)
            elif attrs.items() <= elem.attrib.items():
                elem.text = str(new_value)
                changed.append(elem)
    return changed

# @get_modifications
def change_elm(root:Element, rpath:str, new_value:str, attr_to_change: str=None):
    """
    Changes the text or the attribute's value of a particular element
    :param root:
    :param rpath:             relative path of the element in the root
    :param new_value:
    :param attr_to_change:    If provided, the changed value will be the attribute's one
    :return:
    """
    elements, indexes = find_element_by_path(root, rpath)

    if not elements:
        print('\nWARNING : (change_elm) no element found with this path : {}\n'.format(rpath))
    if len(elements) > 1:
        print('\nWARNING : multiple elements found with this path : {}'.format(rpath))
        print('The value will be changed for all these elements\n')

    for elem in elements:
        if attr_to_change:
            elem.attrib[attr_to_change] = new_value
        else:
            elem.text = new_value

    return elements

# @get_modifications
def copy_children(root_in:Element, ini_rpath:str, root_out:Element, out_rpath:str):
    """
    Copies all children from root_in's element to root_out's one
    :param root_in:
    :param ini_rpath:
    :param root_out:
    :param out_rpath:
    :return:
    """

    changed = []

    out_elem, _ = find_element_by_path(root_out, out_rpath)
    ini_elem, _ = find_element_by_path(root_in, ini_rpath)

    if len(out_elem)!=1 or len(ini_elem)!=1: return changed
    out_elem = out_elem[0]
    ini_elem = ini_elem[0]

    for idx, child in enumerate(ini_elem.getchildren()):
        out_elem.insert(idx, child)
        changed.append(child)

    replace_namespace_recursively(out_elem, root_out)

    return changed


def replace_namespace(elem: Element, root_bb: Element):
    """
    Finds in the root_bb the corresponding 'element' to elem, and changes elem's namespace with the 'element's one
    :param elem:
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

# @get_modifications
def create_child(root:Element, rpath:str, tag:str, text:str=None, attribs:dict={}):

    parent_elm, _ = find_element_by_path(root, rpath)
    if len(parent_elm) >1 or len(parent_elm)==0:
        print('(create_child) Multiple ot 0 elements found with this path {}'.format(rpath),
              '\n Will not create element under.')
        return []

    child = xml.etree.ElementTree.SubElement(parent_elm[0], tag, attrib=attribs, text=text)

    return [child]


# @get_modifications
def copy_elements(elements_to_copy:list, root_in, root_out, root_bb):
    """
    Finds matching elements in elements_to_copy, and replaces them in the root_out.
    Supports some xpath queries.
    :param elements_to_copy:  List of paths to the nodes we want to copy from the initial MTD file
    :return:
    """

    changed = []
    for elem_path in elements_to_copy:

        out_elems, indexes = find_element_by_path(root_out, elem_path)
        ini_elems, _ = find_element_by_path(root_in, elem_path)

        if len(out_elems) == len(ini_elems):
            if len(out_elems) > 1:
                print('WARNING : (copy_elements) multiple elements found for {}'.format(elem_path))
            for out_elem, ini_elem, idx in zip(out_elems, ini_elems, indexes):
                parent = getParentObjectNode(root_out, out_elem)
                parent.remove(out_elem)
                new_elem = copy.copy(ini_elem)
                parent.insert(idx, new_elem)

                replace_namespace_recursively(new_elem, root_bb)
                [changed.append(e) for e in new_elem.iter('*')]

    return changed