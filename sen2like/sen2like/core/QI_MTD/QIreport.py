#! /usr/bin/env python
# -*- coding: utf-8 -*-
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


import datetime as dt
import logging
import os

import version
from core.QI_MTD.generic_writer import (
    XmlWriter,
    change_elm,
    chg_elm_with_tag,
    create_child,
    find_element_by_path,
    remove_namespace,
)
from core.QI_MTD.mtd import Metadata

log = logging.getLogger('Sen2Like')


class QiWriter(XmlWriter):

    def __init__(self, backbone_path: str, init_qi_path: str = None, H_F='H', outfile: str = None):
        """
        Init L2H/F_QUALITY.xml writer.
        When `init_qi_path`is given, the L2H/F_QUALITY.xml result inherit values from init_qi_path content
        if not recompute by S2L.
        Args:
            backbone_path (str): L2H/F_QUALITY.xml file template
            init_qi_path (str): L2A_QUALITY.xml file path, can be `None`
            H_F (str): type of the product (H/F)
            outfile (str): L2H/F_QUALITY.xml output file path
        """
        super().__init__(backbone_path, init_qi_path, H_F)
        self.outfile = outfile

    def manual_replaces(self, product):

        metadata = product.metadata
        # Saving all values which are present in the input QI report (L2A_QUALITY.xml) if any.
        # This is done to retrieve all values from init_qi_path (input_xml_path in XmlWriter)
        # that are not in metadata.qi (computed by S2L) and put them in metadata.qi
        self._feed_values_dict(metadata)

        # Replace all 'value' nodes from mtd dict
        self._replace_values(metadata.qi)

        chg_elm_with_tag(self.root_out, tag='version', new_value=version.baseline_dotted)
        chg_elm_with_tag(self.root_out, tag='File_Version', new_value=version.baseline)
        chg_elm_with_tag(self.root_out, tag='Creator_Version', new_value=version.__version__)

        # L2A_Quality_Header
        # ------------------
        change_elm(self.root_out, rpath='./L2{}_Quality_Header/Fixed_Header/Mission'.format(self.H_F),
                   new_value=product.sensor_name)

        product_creation_date = dt.datetime.strftime(metadata.mtd.get('product_creation_date'), 'UTC=%Y-%m-%dT%H:%M:%S')
        change_elm(self.root_out, rpath='./L2{}_Quality_Header/Fixed_Header/Source/Creation_Date'.format(self.H_F),
                   new_value=product_creation_date)

        # Data_Block
        # ----------
        report_creation_date = dt.datetime.strftime(dt.datetime.now(dt.UTC), '%Y-%m-%dT%H:%M:%SZ')
        change_elm(self.root_out, rpath='./Data_Block/report', attr_to_change='date',
                   new_value=report_creation_date)
        chg_elm_with_tag(self.root_out, tag='value', new_value=metadata.qi.get('MEAN', 'None'),
                         attrs={"name": "COREGISTRATION_AFTER_CORRECTION"})

        self._sbaf_replace(metadata)

        # Change all 'item' urls and names
        product_name_field = f"product_{self.H_F}_name"
        granule_name_field = f"granule_{self.H_F}_name"
        urls = os.path.join(metadata.mtd.get(product_name_field), 'GRANULE',
                            metadata.mtd.get(granule_name_field), 'QI_DATA')
        url_aux = os.path.join(metadata.mtd.get(product_name_field), 'GRANULE',
                               metadata.mtd.get(granule_name_field), 'AUX_DATA')
        change_elm(self.root_out, rpath='./Data_Block/report/checkList/item', attr_to_change='url', new_value=urls)
        change_elm(self.root_out, rpath='./Data_Block/report/checkList[parentID="L2A_AUX"]/item', attr_to_change='url',
                   new_value=url_aux)
        change_elm(self.root_out, rpath='./Data_Block/report/checkList/item', attr_to_change='name',
                   new_value=metadata.mtd.get(granule_name_field))

        # process L2A input for PSD 15 support (DARK_FEATURES_PERCENTAGE replaced by CAST_SHADOW_PERCENTAGE)
        if self.input_xml_path and product.psd == '15':
            self._manage_psd_15()

    def _sbaf_replace(self, metadata: Metadata):
        extra_values_elem = './Data_Block/report/checkList[parentID="L2H_SBAF"]/check/extraValues'
        # # Removing unchanged SBAF values and inserting new ones
        ns = self.remove_children(
            extra_values_elem,
            tag='value',
            attrs={'name': 'SBAF_COEFFICIENT_'}
        )
        self.remove_children(extra_values_elem, tag='value', attrs={'name': 'SBAF_OFFSET_'})

        for key, item in sorted(metadata.qi.items()):
            if 'SBAF_COEFFICIENT_' in key or 'SBAF_OFFSET_' in key:
                create_child(
                    self.root_out, extra_values_elem,
                    tag=ns + 'value', text=str(item),
                    attribs={"name": key}
                )

    def _manage_psd_15(self):
        """
        Replace element `value` attribute `name` DARK_FEATURES_PERCENTAGE with CAST_SHADOW_PERCENTAGE 
        and set its value properly
        """
        DARK_FEATURES_PERCENTAGE_PATH = './Data_Block/report/checkList[parentID="L2A_SC"]/check/extraValues/value[@name="DARK_FEATURES_PERCENTAGE"]'
        CAST_SHADOW_PERCENTAGE_PATH = './Data_Block/report/checkList[parentID="L2A_SC"]/check/extraValues/value[@name="CAST_SHADOW_PERCENTAGE"]'

        elem = find_element_by_path(self.root_out, DARK_FEATURES_PERCENTAGE_PATH)
        if len(elem) != 1:
            log.error(
                "PSD15: Unable to replace DARK_FEATURES_PERCENTAGE by CAST_SHADOW_PERCENTAGE, 0 or > 1 elem match in template"
            )
            return

        orig = find_element_by_path(self.root_in, CAST_SHADOW_PERCENTAGE_PATH)
        if len(orig) != 1:
            log.error(
                "PSD15: Unable to find CAST_SHADOW_PERCENTAGE in %s, 0 or > 1 elem match",
                self.input_xml_path
            )
            return

        elem[0].attrib["name"] = "CAST_SHADOW_PERCENTAGE"
        elem[0].text=orig[0].text

    def _feed_values_dict(self, metadata):
        """
        Function only used by the QI report writer
        Reads the input QI report if it exists, put all 'value' nodes text into the metadata.qi dictionary
        if not already in.
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
