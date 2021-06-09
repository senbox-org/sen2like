#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2020

import datetime as dt
import logging
import os

from core.QI_MTD.generic_writer import remove_namespace, chg_elm_with_tag, change_elm, create_child, MtdWriter
from core.QI_MTD.mtd import metadata
from version import __version__

log = logging.getLogger('Sen2Like')


class QiWriter(MtdWriter):

    def __init__(self, backbone_path: str, init_QI_path: str = None, H_F='H', outfile: str = None):
        super().__init__(backbone_path, init_QI_path, H_F)
        self.outfile = outfile

    def manual_replaces(self, product):

        # Saving all values which are present in the input QI report
        self.feed_values_dict()

        # Replace all 'value' nodes from mtd dict
        self._replace_values(metadata.qi)

        file_version = str(int(__version__.replace('.', '')))  # Int because it is specified in the .xsd
        chg_elm_with_tag(self.root_out, tag='version', new_value=file_version)
        chg_elm_with_tag(self.root_out, tag='File_Version', new_value=file_version)

        # L2A_Quality_Header
        # ------------------
        change_elm(self.root_out, rpath='./L2{}_Quality_Header/Fixed_Header/Mission'.format(self.H_F),
                   new_value=product.sensor_name)

        product_creation_date = dt.datetime.strftime(metadata.mtd.get('product_creation_date'), 'UTC=%Y-%m-%dT%H:%M:%S')
        change_elm(self.root_out, rpath='./L2{}_Quality_Header/Fixed_Header/Source/Creation_Date'.format(self.H_F),
                   new_value=product_creation_date)

        # Data_Block
        # ----------
        report_creation_date = dt.datetime.strftime(dt.datetime.now(), '%Y-%m-%dT%H:%M:%SZ')
        change_elm(self.root_out, rpath='./Data_Block/report', attr_to_change='date',
                   new_value=report_creation_date)
        chg_elm_with_tag(self.root_out, tag='value', new_value=metadata.qi.get('MEAN', 'None'),
                         attrs={"name": "COREGISTRATION_AFTER_CORRECTION"})

        # # Removing unchanged SBAF values and inserting new ones
        ns = self.remove_children('./Data_Block/report/checkList[parentID="L2H_SBAF"]/check/extraValues', tag='value',
                                  attrs={'name': 'SBAF_'})

        for key, item in sorted(metadata.qi.items()):
            if 'SBAF_' in key:
                create_child(self.root_out, './Data_Block/report/checkList[parentID="L2H_SBAF"]/check/extraValues',
                             tag=ns + 'value', text=str(item),
                             attribs={"name": key})

        # Change all 'item' urls and names
        urls = os.path.join(metadata.mtd.get('product_{}_name'.format(self.H_F)), 'GRANULE',
                            metadata.mtd.get('granule_{}_name'.format(self.H_F)), 'QI_DATA')
        url_aux = os.path.join(metadata.mtd.get('product_{}_name'.format(self.H_F)), 'GRANULE',
                               metadata.mtd.get('granule_{}_name'.format(self.H_F)), 'AUX_DATA')
        change_elm(self.root_out, rpath='./Data_Block/report/checkList/item', attr_to_change='url', new_value=urls)
        change_elm(self.root_out, rpath='./Data_Block/report/checkList[parentID="L2AAUX"]/item', attr_to_change='url',
                   new_value=url_aux)
        change_elm(self.root_out, rpath='./Data_Block/report/checkList/item', attr_to_change='name',
                   new_value=metadata.mtd.get('granule_{}_name'.format(self.H_F)))

    def feed_values_dict(self):
        """
        Function only used by the QI report writer
        Reads the input QI report if it exists, and saves all 'value' nodes text into the metadata.qi dictionary
        :return:
        """
        if self.root_in is not None:
            for elem in self.root_in.iter('*'):
                node_name, _ = remove_namespace(elem.tag)
                if node_name == 'value':
                    # Don't overwrite values who were changed during Sen2Like processes
                    if metadata.qi.get(elem.attrib.get('name')) in [None, "NONE", "None"]:
                        metadata.qi[elem.attrib.get('name')] = elem.text

    def _replace_values(self, values_dict):
        """
        Finds all elements with 'value' tag, and replace their value if they are contained in 'values_dict
        :param values_dict:      dict with the 'Value' nodes from the QI report. key=node_name, item=node_text
        :return:
        """
        for attr, new_value in values_dict.items():
            chg_elm_with_tag(root=self.root_out, tag='value', new_value=new_value, attrs={'name': attr})
