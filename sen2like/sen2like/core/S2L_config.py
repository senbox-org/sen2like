#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import configparser
import datetime
import hashlib
import json
import logging
import os

from argparse import Namespace
from collections import OrderedDict
from xml.etree import ElementTree

import xmlschema

# TODO see this to have config object
# https://stackoverflow.com/questions/63431417/using-configparser-to-create-objects-of-a-class

# INTERNAL CONFIGURATION (static)

# define here all the blocks that are implemented, then user to choose
# which blocks are to be run through the on/off switches in the config.ini file
PROC_BLOCKS = OrderedDict()
PROC_BLOCKS['S2L_Geometry'] = {'extension': '_REFRAMED.TIF', 'applicability': 'L8_L9_S2'}
PROC_BLOCKS['S2L_Stitching'] = {'extension': '_STITCHED.TIF', 'applicability': 'L8_L9_S2'}
PROC_BLOCKS['S2L_GeometryCheck'] = {'extension': None, 'applicability': 'L8_L9_S2'}
PROC_BLOCKS['S2L_Toa'] = {'extension': '_TOA.TIF', 'applicability': 'L8_L9_S2'}
PROC_BLOCKS['S2L_InterCalibration'] = {'extension': '_INTERCAL.TIF', 'applicability': 'L8_L9_S2'}
PROC_BLOCKS['S2L_Atmcor'] = {'extension': '_SURF.TIF', 'applicability': 'L8_L9_S2'}
PROC_BLOCKS['S2L_Nbar'] = {'extension': '_BRDF.TIF', 'applicability': 'L8_L9_S2'}
PROC_BLOCKS['S2L_Sbaf'] = {'extension': '_SBAF.TIF', 'applicability': 'L8_L9_S2'}
PROC_BLOCKS['S2L_PackagerL2H'] = {'extension': None, 'applicability': 'L8_L9_S2'}
PROC_BLOCKS['S2L_Fusion'] = {'extension': '_FUSION.TIF', 'applicability': 'L8_L9'}
PROC_BLOCKS['S2L_PackagerL2F'] = {'extension': None, 'applicability': 'L8_L9_S2'}

logger = logging.getLogger("Sen2Like")


class XmlParser:

    def __init__(self, config_file):
        self.config_file = config_file
        self.root = None
        self.document_tree = None

    def initialize(self):
        if not self.validate_schema():
            logger.error("XML configuration file is not compliant with XSD.")
            return False
        self.document_tree = ElementTree.parse(self.config_file)
        self.root = self.document_tree.getroot()
        return True

    def display(self):
        for section in self.root:
            print(f"\n[{section.tag}]")
            for parameter in section:
                print(f"{parameter.tag} = {parameter.text}")

    def validate_schema(self):
        path = os.path.dirname(__file__)
        xsd_path = os.path.abspath(os.path.join(path, "..", "..", "conf", "Sen2Like_GIPP.xsd"))
        schema = xmlschema.XMLSchema(xsd_path)
        return schema.is_valid(self.config_file)

    def get(self, option, default=None):
        """
        Search option in all sections and return value
        (do not take account of sections)
        """
        value = default
        for section in self.root:
            element = section.find(option)
            if element is not None:
                value = element.text
                if value == 'None':
                    value = None
                break
        return value

    def get_section(self, section):
        """Return content of a section as a dictionary."""
        found_section = self.root.find(section)
        if found_section:
            return {option.tag: option.text for option in found_section}
        return {}

    def getboolean(self, option):
        """
        Search option in all sections and return value
        (do not take account of sections)
        """
        value = self.get(option)
        return value.lower() == 'true'

    def getfloat(self, option):
        """
        Search option in all sections and return value
        (do not take account of sections)
        """
        value = self.get(option)
        if value is not None:
            value = float(value)
        return value

    def set(self, option, value):
        """
        Set new option in file.
        Section is 'RunTime' by default
        """
        # Add section if it does not exist
        runtime_element = self.root.find('.//RunTime')
        if runtime_element is None:
            runtime_element = ElementTree.Element('RunTime')
            self.root.append(runtime_element)
        element = runtime_element.find(option)
        if element is None:
            # Add option
            element = ElementTree.SubElement(runtime_element, option)
        element.text = str(value)

    def overload(self, dic):
        """
        Overload parameters value in config
        Input given by a dictionary key/value, or as a
        "key=value" comma-separated list,
            example: "doNbar=False,doSbaf=False"
        """
        if isinstance(dic, str):
            string = dic
            dic = {}
            for keyval in string.strip().split(','):
                [key, value] = keyval.split('=')
                dic[key] = value

        for (option, value) in list(dic.items()):
            for section in self.root:
                element = section.find(option)
                if element is not None:
                    element.text = str(value)
                    break
            else:
                logger.warning("Can not overload parameter '%s' (not found)", option)

    def savetofile(self, config_file):
        """Save configuration file into ini format."""
        # check if dir exists
        dirout = os.path.dirname(config_file)
        if not os.path.exists(dirout):
            os.makedirs(dirout)
        # write in file
        _config = configparser.ConfigParser()
        _config.optionxform = str
        for section in self.root:
            _config[section.tag] = {param.tag: param.text for param in section}
        with open(config_file, "w") as config_writer:
            _config.write(config_writer)


class IniParser:

    def __init__(self, config_file):
        self.config_file = config_file
        self.configObject = configparser.RawConfigParser(allow_no_value=True)
        self.configObject.optionxform = str

    def initialize(self):
        return self.configObject.read(self.config_file)

    def display(self):
        logger.info(self.configObject.defaults())
        for section in self.configObject.sections():
            logger.info(section)
            logger.info(self.configObject.items(section))

    def get(self, option, default=None):
        """
        Search option in all sections and return value
        (do not take account of sections)
        """
        value = default
        for section in self.configObject.sections():
            if option in self.configObject.options(section):
                value = self.configObject.get(section, option)
                if value == 'None':
                    value = None
                break
        return value

    def get_section(self, section):
        """Return content of a section as a dictionary."""
        if self.configObject.has_section(section):
            return dict(self.configObject.items(section))
        return {}

    def getboolean(self, option):
        """
        Search option in all sections and return value
        (do not take account of sections)
        """
        for section in self.configObject.sections():
            if option in self.configObject.options(section):
                return self.configObject.getboolean(section, option)
        return None

    def getfloat(self, option):
        """
        Search option in all sections and return value
        (do not take account of sections)
        """
        for section in self.configObject.sections():
            if option in self.configObject.options(section):
                return self.configObject.getfloat(section, option)
        return None

    def set(self, option, value):
        """
        Set new option in file.
        Section is 'RunTime' by default
        """
        # add section if does not exist
        if 'RunTime' not in self.configObject.sections():
            self.configObject.add_section('RunTime')

        # add option
        self.configObject.set('RunTime', option, str(value))

    def overload(self, dic):
        """
        Overload parameters value in config
        Input given by a dictionary key/value, or as a "key=value" comma-separated list,

        example: "doNbar=False,doSbaf=False"
        """
        if isinstance(dic, str):
            string = dic
            dic = {}
            for keyval in string.strip().split(','):
                [key, value] = keyval.split('=')
                dic[key] = value

        for (option, value) in list(dic.items()):
            for section in self.configObject.sections():
                if option in self.configObject.options(section):
                    self.configObject.set(section, option, str(value))
                    break
            else:
                logger.warning("Can not overload parameter '%s' (not found)", option)

    def savetofile(self, configfile):
        # check if dir exists
        dirout = os.path.dirname(configfile)
        if not os.path.exists(dirout):
            os.makedirs(dirout)
        # write in file
        with open(configfile, 'w') as o:
            self.configObject.write(o)


class S2L_Config:
    parsers = {".xml": XmlParser,
               ".ini": IniParser,
               ".cfg": IniParser}

    def __init__(self, configuration_file=None):
        self.parser = None

        if configuration_file is not None:
            self.initialize(configuration_file)

    def initialize(self, config_file):
        if not os.path.exists(config_file):
            logger.error("Configuration file does not exists: %s", config_file)
            return False
        logger.info("Reading configuration file: %s", os.path.abspath(config_file))
        self.parser = self.parsers.get(os.path.splitext(config_file)[-1])
        if self.parser is None:
            logger.error("Unsupported configuration file format.")
            return False
        self.parser = self.parser(config_file)
        return self.parser.initialize()

    def __getattr__(self, item):
        if item in ["display", "get", "getboolean", "getfloat", "set", "overload", "savetofile", "get_section"]:
            return getattr(self.parser, item)
        raise AttributeError(f"'S2L_Config' object has no attribute '{item}'")

    def _compute_config_hash(self, args):
        """Compute hash from arguments and configuration.

        :param args: Tool arguments.
        :param _config: Configuration
        :return: Hexdigest of the hash.
        """

        # debug
        import copy
        exclude_list = ['parallelize_bands']
        dc = copy.deepcopy(args.__dict__)
        for exc in exclude_list:
            dc.pop(exc)
        dc = str(dc)

        # Prod
        # dc = str(args.__dict__)

        # Configuration hash
        if self.parser.config_file is not None:
            with open(self.parser.config_file) as file:
                file_content = file.read()
        _hash = hashlib.md5(file_content.encode())
        _hash.update(dc.encode())
        return _hash.hexdigest()

    def update_with_args(self, args: Namespace, tile=None):
        """update config with the given arguments

        Args:
            args (Namespace): parsed program args
            tile (str, optional): tile name. Defaults to None.
        """
        # init S2L_config and save to wd
        if not self.initialize(args.S2L_configfile):
            return

        if args.confParams is not None:
            self.overload(args.confParams)

        # set working dir
        date_now = datetime.datetime.utcnow().strftime('%Y%m%dT_%H%M%S')
        output_folder = f'{"" if args.no_log_date else f"{date_now}_"}{self._compute_config_hash(args)}'
        self.set('wd', os.path.join(args.wd, output_folder))

        references_map_file = self.get('references_map')
        if args.refImage:
            self.set('refImage', args.refImage)
        elif references_map_file and tile:
            if os.path.isfile(references_map_file):
                # load dataset
                with open(references_map_file) as j:
                    references_map = json.load(j)
                self.set('refImage', references_map.get(tile))
            else:
                logger.warning("The reference path %s doesn't exist. So it is considered as None.", references_map_file)
                self.set('refImage', None)
        else:
            self.set('refImage', None)
        self.set('hlsplus', self.getboolean('doPackagerL2F'))
        self.set('debug', args.debug)
        self.set('generate_intermediate_products', args.generate_intermediate_products)
        if hasattr(args, 'l2a'):
            self.set('s2_processing_level', 'LEVEL2A' if args.l2a else "LEVEL1C")

        self.set('allow_other_srs', args.allow_other_srs)


config = S2L_Config()
