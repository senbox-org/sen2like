#! /usr/bin/env python
# -*- coding: utf-8 -*-
# G. Cavaro (TPZ-F) 2020

import datetime


class Metadata:
    def __init__(self):
        self.mtd = {}
        self.qi = {}
        self.hardcoded_values = {}
        self.clear()

    def clear(self):
        self.mtd = {"bands_path_H": [],
                    "bands_path_F": [],
                    "product_H_name": "NONE",
                    "product_F_name": "NONE",
                    "granule_H_name": "NONE",
                    "granule_F_name": "NONE",
                    "band_rootName_H": "NONE",
                    "band_rootName_F": "NONE",
                    "generation_time": datetime.datetime(1, 1, 1, 1, 1, 1),
                    "masks_H": [],
                    "masks_F": [],
                    "quicklooks_H": [],
                    "quicklooks_F": [],
                    "ang_filename": "NONE",
                    "qi_path": "NONE",
                    "pvi_filename": "NONE",
                    "S2_AC": 'ZZZ'
                    }

        # self.qi is a dict with the 'Value' nodes from the QI report. key=node_name, item=node_text
        self.qi = {"COREGISTRATION_BEFORE_CORRECTION": "NONE",
                   "SKEW": "NONE",
                   "KURTOSIS": "NONE",
                   "MEAN": "NONE",
                   "STD": "NONE",
                   "RMSE": "NONE",
                   "NB_OF_POINTS": "NONE",
                   "MEAN_DELTA_AZIMUTH": "NONE",
                   "CONSTANT_SOLAR_ZENITH_ANGLE": "NONE"
                   }

        self.hardcoded_values = {"s2_struct_xml": "xml_backbones/S2_folder_backbone.xml",
                                 "bb_S2F_product": "xml_backbones/MTD_MSIL2F_S2.xml",
                                 "bb_S2H_product": "xml_backbones/MTD_MSIL2H_S2.xml",
                                 "bb_L8F_product": "xml_backbones/MTD_OLIL2F_L8.xml",
                                 "bb_L8H_product": "xml_backbones/MTD_OLIL2H_L8.xml",
                                 "bb_S2F_tile": "xml_backbones/MTD_TL_L2F_S2.xml",
                                 "bb_S2H_tile": "xml_backbones/MTD_TL_L2H_S2.xml",
                                 "bb_L8F_tile": "xml_backbones/MTD_TL_L2F_L8.xml",
                                 "bb_L8H_tile": "xml_backbones/MTD_TL_L2H_L8.xml",
                                 "bb_QIH_path": "xml_backbones/L2H_QI_Report_backbone.xml",
                                 "bb_QIF_path": "xml_backbones/L2F_QI_Report_backbone.xml",
                                 "product_mtd_xsd":
                                     "xsd_files/S2-PDGS-TAS-DI-PSD-V14.5_Schema/S2_User_Product_Level-2A_Metadata.xsd",
                                 "product_tl_xsd":
                                     "xsd_files/S2-PDGS-TAS-DI-PSD-V14.5_Schema/S2_PDI_Level-2A_Tile_Metadata.xsd",
                                 "product_QIH_xsd": "xsd_files/L2H_QI_Report.xsd",
                                 "product_QIF_xsd": "xsd_files/L2F_QI_Report.xsd",
                                 "L8_absolute_orbit": "000000",
                                 "PDGS": "9999",
                                 "L8_archiving_center": "ZZZ_",
                                 "L8_archiving_time": "0000-00-00T00:00:00.000Z"}

    def update(self, new_medatada):
        """Merge a metadata content with current metadata

        :param new_medatada: Metadata to merge
        """
        self.qi.update(new_medatada.qi)

        for key, val in new_medatada.mtd.items():
            if isinstance(val, list):
                self.mtd[key].extend(val)
            elif isinstance(val, dict):
                self.mtd[key].update(val)
            else:
                self.mtd[key] = val


metadata = Metadata()
