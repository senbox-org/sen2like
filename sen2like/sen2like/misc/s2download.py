#! /opt/anaconda3/bin/python
# -*- coding: utf-8 -*-

import datetime as dt
import os
import socket
import sys
import urllib.request as urllib2  # python3
import xml.etree.ElementTree as ET
from argparse import ArgumentParser

from lxml import objectify

NS = "{http://www.w3.org/2005/Atom}"

DEBUG = True

# read api.txt (url, user and password)
BINDIR = os.path.dirname(os.path.abspath(sys.argv[0]))
lines = open(BINDIR + "/api.txt").readlines()
S2_API_URL = lines[0].strip()
S2_API_USER = lines[1].strip()
S2_API_PASSWORD = lines[2].strip()

SEP = "%20AND%20"
SPACE = "%20"


def debug(msg):
    if DEBUG:
        print(msg)


def connect():
    """ Deal with authentification """
    passwordMgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    passwordMgr.add_password(None, S2_API_URL, S2_API_USER, S2_API_PASSWORD)
    handler = urllib2.HTTPBasicAuthHandler(passwordMgr)
    opener = urllib2.build_opener(handler)  # create "opener" (OpenerDirector instance)
    urllib2.install_opener(opener)  # Now all calls to urllib2.urlopen use our opener.# Install the opener.


class Product:
    SENSOR_CODES = {'OL': 'OLCI', 'SL': 'SLSTR'}
    name = None
    id = None
    time = None
    orb = None
    absorb = None
    link = None
    size = None
    cloud = None
    url = None
    timestr = None

    def __str__(self):
        return "{} {} {}".format(self.name, self.size, self.cloud)

    def getSizeInMb(self):
        res = None
        if self.size.endswith('MB'):
            res = float(self.size.replace('MB', ''))
        elif self.size.endswith('GB'):
            res = float(self.size.replace('GB', '')) * 1024
        return res


class Metadata:
    """
    Quick access to metadata parameters, such as EPSG, ULX, ULY
    """

    def __init__(self, mtdfile):
        # parse
        # with open(mtdfile) as f:
        et = objectify.parse(mtdfile)
        self.root = et.getroot()

    def getCldPath(self, res=60):
        cldpath = None
        General_Info = self.root.General_Info
        print(General_Info)
        if General_Info.find('Product_Info') is not None:
            print(General_Info['{}Product_Info'])
            imgpath = General_Info['{}Product_Info'].Product_Organisation.Granule_List.Granule.IMAGE_FILE.text
            tilename = imgpath.split('/')[1]
            cldpath = 'GRANULE/' + tilename + '/QI_DATA/MSK_CLDPRB_60m.jp2'
        else:
            for Granule_List in General_Info['{}L2A_Product_Info'].L2A_Product_Organisation.Granule_List:
                for IMAGE_FILE_2A in Granule_List.Granule.IMAGE_FILE_2A:
                    if IMAGE_FILE_2A.text.endswith('_CLD_%2dm' % res):
                        cldpath = IMAGE_FILE_2A.text + '.jp2'
                        break

    def getBand(self, band):
        path = None
        General_Info = self.root.General_Info
        if General_Info.find('Product_Info') is not None:
            print(General_Info)
            for Granule_List in General_Info['{}Product_Info'].Product_Organisation.Granule_List:
                for IMAGE_FILE in Granule_List.Granule.IMAGE_FILE:
                    if IMAGE_FILE.text.endswith(band):
                        path = IMAGE_FILE.text + '.jp2'
                        break
        else:
            for Granule_List in General_Info['{}L2A_Product_Info'].L2A_Product_Organisation.Granule_List:
                for IMAGE_FILE_2A in Granule_List.Granule.IMAGE_FILE_2A:
                    if IMAGE_FILE_2A.text.endswith(band):
                        path = IMAGE_FILE_2A.text + '.jp2'
                        break

        return path


def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def path2url(path):
    url = ""
    for elt in path.split('/'):
        url += "/Nodes('" + elt + "')"
    return url


def getPath(pd, band, subdir):
    # mtd file
    mkdir(os.path.join(subdir, "mtd"))
    if pd.producttype == "MSIL1C":
        mtdfile = os.path.join(subdir, "mtd", pd.name + '_MTD_MSIL1C.xml')
    else:
        mtdfile = os.path.join(subdir, "mtd", pd.name + '_MTD_MSIL2A.xml')

    if not os.path.exists(mtdfile):
        # get mtd file and save it
        if pd.producttype == "MSIL1C":
            url = pd.url + "/Nodes('MTD_MSIL1C.xml')/$value"
        else:
            url = pd.url + "/Nodes('MTD_MSIL2A.xml')/$value"
        toDownload = True
        while toDownload:
            debug(url)
            try:
                f = urllib2.urlopen(url, timeout=120)
                # xmltext = f.read().decode("utf-8")  # as string
                xml = f.read()  # as bytes
                with open(mtdfile, 'bw') as o:
                    o.write(xml)
                toDownload = False
            except socket.timeout:
                print('timeout')

    # get band path from mtd
    mtd = Metadata(mtdfile)
    path = mtd.getBand(band)  # L2A_T35XLC_A015149_20180517T110629

    return path


def getBand(pd, band, download=False):
    bandfile = None
    # get tilename
    subdir = os.getcwd()
    path = getPath(pd, band, subdir)  # TOO LONG; vi Try something like:
    # path = 'GRANULE/L2A_{0}_A{1:06d}_{2}/IMG_DATA/R20m/L2A_{0}_{3}_{4}.jp2'.format(pd.tileid, pd.absorb, pd.timeprodstr,
    #                                                                               pd.timestr, band)

    print(path)

    # get band
    url = pd.url + path2url(path) + "/$value"
    bandfile = os.path.join(subdir, os.path.basename(path).replace(".jp2", "_{}.jp2".format(pd.orb)))

    if download:
        if os.path.exists(bandfile):
            print(bandfile, "- Already downloaded")
        else:
            debug(url)
            # connect()
            toDownload = True
            while toDownload:
                try:
                    f = urllib2.urlopen(url, timeout=120)
                    mkdir(subdir)
                    with open(bandfile, 'wb') as o:
                        o.write(f.read())
                    toDownload = False
                except socket.timeout:
                    print('timeout')
            print(bandfile, "- Downloaded!")
    return bandfile


def parse4products(root, platformname='Sentinel-2'):
    products = []
    for entry in root.findall(NS + "entry"):
        pd = Product()
        pd.name = entry.find(NS + "title").text
        pd.id = entry.find(NS + "id").text
        if platformname == 'Sentinel-2':
            pd.producttype = pd.name.split("_")[1]
            pd.timestr = pd.name.split("_")[2]
            pd.tileid = pd.name.split("_")[5]
            pd.timeprodstr = pd.name.split("_")[6]
            pd.time = dt.datetime.strptime(pd.timestr, "%Y%m%dT%H%M%S")
            pd.orb = pd.name.split("_")[4]
        elif platformname == 'Sentinel-3':
            "Example: S3A_OL_1_EFR____20180817T084007_20180817T084307_20180818T123504_0179_034_335_1980_LN1_O_NT_002"
            sensorcode = pd.name.split("_")[1]
            pd.sensor = pd.SENSOR_CODES[sensorcode]
            pd.producttype = "L" + pd.name.split("_")[2]
            pd.datatype = pd.name.split("_")[3]
            pd.timestr = pd.name.split("_")[7]
            pd.time = dt.datetime.strptime(pd.timestr, "%Y%m%dT%H%M%S")
            pd.timeprodstr = pd.name.split("_")[9]
            pd.tileid = "_".join(pd.name.split("_")[10:15])
            pd.orb = pd.name.split("_")[12]

        pd.link = entry.find(NS + "link").get('href')
        for elt in entry.findall(NS + "str"):
            if "name" in elt.keys() and elt.get('name') == 'size':
                pd.size = elt.text
        for elt in entry.findall(NS + "double"):
            if "name" in elt.keys() and elt.get('name') == 'cloudcoverpercentage':
                pd.cloud = elt.text
        for elt in entry.findall(NS + "int"):
            if "name" in elt.keys() and elt.get('name') == 'orbitnumber':
                pd.absorb = int(elt.text)
        pd.url = S2_API_URL + "/odata/v1/Products('" + pd.id + "')/Nodes('" + pd.name + ".SAFE')"
        products.append(pd)
    return products


def search(options):
    """search products on tile"""
    products = []
    searchTerms = []
    for key in options.keys():
        if options[key] is not None:
            searchTerms += ['{}:{}'.format(key, options[key])]

    url = S2_API_URL + '/search?start=0&rows=100&q=(' + SPACE.join(
        searchTerms) + ')'  # beware, if number of rows is to high, the request might fail

    while url is not None:
        # read page
        debug(url)
        f = urllib2.urlopen(url)
        xmltree = ET.parse(f)
        xmlroot = xmltree.getroot()

        # parse products in page
        products += parse4products(xmlroot, options['platformname'])

        # check if next page to read?
        url = None
        for link in xmlroot.findall(NS + "link"):
            if link.get('rel') == "next":
                url = link.get('href').replace(' ', SPACE)
                break

    # sort
    products = sorted(products, key=lambda pd: pd.time)
    return products


def s2download(options, download=False, quiet=False, bands=None):
    """
    By defaut the products are not downloaded, only displayed, except if download option is activated.
    """

    # connect to api and search
    connect()
    products = search(options)

    bandfiles = []

    # display
    # products.sort()
    for pd in products:
        print(pd.name, pd.size, pd.cloud)
        if bands is None:
            if download:
                # download if requested
                wget_cmd = 'wget --no-check-certificate --user=%s --password=%s "%s" -O %s' % (
                    S2_API_USER, S2_API_PASSWORD, pd.link.replace("$", "\\$"), pd.name + '.zip')
                if quiet:
                    wget_cmd += ' q'
                debug(wget_cmd)
                os.system(wget_cmd)
        else:
            # import s2downloadband
            for band in bands:
                # s2downloadband.getBand(pd, band, download)
                bandfile = getBand(pd, band, download)
                if bandfile:
                    bandfiles.append(bandfile)

    return products, bandfiles


def stringtodate(string):
    fmt = '%Y-%m-%dT%H:%M:%S'
    if len(string) == 10:
        fmt = '%Y-%m-%d'
    return dt.datetime.strptime(string, fmt)


def main():
    # parse options
    parser = ArgumentParser()
    parser.add_argument('args', nargs='*', help="identifier, e.g. name of product (can be with '*')")
    parser.add_argument("--platformname", dest="platformname", type=str,
                        help="plateforme name (default: Sentinel-2)", metavar="VALUE", default='Sentinel-2')
    parser.add_argument("--producttype", "-p", dest="producttype", type=str,
                        help="producttype (S2MSI1C, S2MSI2A)", metavar="VALUE", default=None)
    parser.add_argument("--tileid", "-t", dest="tileid", type=str,
                        help="tile code, e.g. 50TLK (WARNING: seem to not work with L2A)", metavar="VALUE",
                        default=None)
    parser.add_argument("--relativeorbitnumber", "-r", dest="relativeorbitnumber", type=str,
                        help="relative orbit number", metavar="VALUE", default=None)
    parser.add_argument("--startdate", "-s", dest="startdate", type=str,
                        help="start date, e.g. 2017-01-01 or 2017-01-01T10:53:03", metavar="VALUE", default=None)
    parser.add_argument("--enddate", "-e", dest="enddate", type=str,
                        help="end date, e.g. 2017-01-05", metavar="VALUE", default=None)
    parser.add_argument("--cloud", "-c", dest="cloudcoverpercentage", type=str,
                        help="maximum cloud cover percentage", metavar="VALUE", default=None)
    parser.add_argument("--bands", "-b", dest="bands", type=str,
                        help="select only few bands (B01, SCL, ...) - If not set, the entire product is downloaded",
                        metavar="VALUE", default=None)
    parser.add_argument("--footprint", "-f", dest="footprint", type=str,
                        help="Polygon, e.g. 'POLYGON((23.08400 29.91646 ,25.00542 29.53685, 24.54551 27.80904,  22.65600 28.18927,  23.08400 29.91646))'",
                        metavar="VALUE", default=None)
    parser.add_argument("--download", "-d", dest="download", action='store_true',
                        help="for actually downloading the product (otherwiser only display)")
    parser.add_argument("--quiet", "-q", dest="quiet", action='store_true',
                        help="Do not display progression of downloads")

    options = vars(parser.parse_args())

    # get doDownload option
    download = options.pop('download')
    quiet = options.pop('quiet')
    bands = options.pop('bands')
    if bands is not None:
        bands = bands.split(",")

    # deal with footprints
    footprint = options.pop('footprint')
    if footprint is not None:
        footprint = '"Intersects({})"'.format(footprint.replace(' ', SPACE))
        options['footprint'] = footprint

    # deal with cloud pourcentage
    cloudcoverpercentage = options.pop('cloudcoverpercentage')
    if cloudcoverpercentage is not None:
        cloudcoverpercentage = '[0 TO {}]'.format(cloudcoverpercentage).replace(' ', SPACE)
        options['cloudcoverpercentage'] = cloudcoverpercentage

    # deal with dates
    startdate = options.pop('startdate')
    enddate = options.pop('enddate')
    if startdate is not None:
        if enddate is not None:
            start = stringtodate(startdate).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            end = stringtodate(enddate).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        else:
            start = stringtodate(startdate).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            end = 'NOW'
        options['beginposition'] = '[{}%20TO%20{}]'.format(start, end)

    debug(options)
    args = options.pop('args')
    if len(args) > 0:
        for arg in args:
            options['identifier'] = arg
            s2download(options, download, quiet, bands)
    else:
        s2download(options, download, quiet, bands)


if __name__ == "__main__":
    main()
