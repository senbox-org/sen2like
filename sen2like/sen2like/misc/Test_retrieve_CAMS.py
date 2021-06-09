#!/usr/bin/env python
#
# version 1.0 written on 7 July 2014 by Jerome LOUIS
# updated on 8-9 July 2014 to use associated XML configuration file
# updated on 19 November 2014 to be recover data missing since 30/09/2014
# currently only data from 07/10/2014 is available

# (C) Copyright 2014 Telespazio France

from ecmwfapi import ECMWFDataServer

############# Configuration #############
# .ecmwf_script_config (XML file) must be located in the current home directory
# OuputDir must be the first child of root of XML configuration file

# home = os.path.expanduser('~')
# config_file = home + '/.ecmwf_script_config'
# tree = ET.parse(config_file)
# root = tree.getroot()
# out_dir = root[0].text

############# Configuration #############

# start_date = datetime.datetime(2015,03,17)
# start_date_sec_elapsed = calendar.timegm(start_date.timetuple())

# end_date = datetime.datetime(2015,03,29)
# end_date_sec_elapsed = calendar.timegm(end_date.timetuple())

# n_days = (end_date_sec_elapsed - start_date_sec_elapsed)/86400 + 1

# Initialize ECMWF data server

server = ECMWFDataServer()

# Forecasts

server.retrieve({
    "class": "mc",
    "format": "netcdf",
    "dataset": "cams_nrealtime",
    "date": "2018-09-12/to/2018-09-12",
    "expver": "0001",
    "levtype": "sfc",
    "param": "aod550",
    "stream": "oper",
    "time": "00:00:00",
    "step": "0/3/6/9/12",
    "type": "fc",
    "grid": "0.4/0.4",
    "expect": "any",
    "target": "CAMS_aod550_2018-09-12.nc",
})

# Analysis

# server.retrieve({
#    "class": "mc",
#    "dataset": "cams_nrealtime",
#    "date": "2017-04-20/to/2017-04-20",
#    "expver": "0001",
#    "levtype": "sfc",
#    "param": "207.210",
#    "stream": "oper",
#    "time": "00:00:00/06:00:00/12:00:00/18:00:00",
#    "type": "an",
#    "grid": "0.4/0.4",
#    "expect": "any",
#    "target": "CAMS_archive_aod550_an_2017-04-20.grib",
# })
