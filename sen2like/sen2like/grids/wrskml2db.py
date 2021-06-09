import sqlite3
from collections import OrderedDict
from math import floor

import pandas as pd
from pykml import parser


def readDescription(des):
    """
    read kml description and derive a dictionary
    with key/value for each parameters
    (expected keys: ['UTM_WKT', 'EPSG', 'TILE_ID', 'LL_WKT', 'MGRS_REF'])
    """

    # read string stream
    lines = []
    line = ''
    isText = False
    for c in des:
        if c == '<':
            isText = False
            if line.strip() != '':
                lines.append(line)
            line = ''
        if isText:
            line += c
        if c == '>':
            isText = True

    # fill dictionary
    meta = {}
    for i in range(0, len(lines), 2):
        meta[lines[i]] = lines[i + 1]

    # return dictionary
    return meta


# MAIN

# KML can be downloaded on Landsat website:
# https://landsat.usgs.gov/pathrow-shapefiles

# read kml as string
with open('WRS-2_bound_world.kml') as f:
    string = f.read()

# parse kml string with pykml
root = parser.fromstring(string)
print('nb tiles:', len(root.Document.Placemark))

# create empty dic with keys
dic = OrderedDict()

# now for each tile
for pm in root.Document.Placemark[0:]:
    meta = {'WRS_ID': pm.name.text}
    # get tileid and description
    [path, row] = meta['WRS_ID'].split('_')
    meta['PATH'] = path
    meta['ROW'] = row
    coords_txt = pm.Polygon.outerBoundaryIs.LinearRing.coordinates.text.strip()
    # -178.785,-80.929,6999.999999999999 -177.567,
    # -82.68000000000001,6999.999999999999 169.654,
    # -82.68000000000001,6999.999999999999 170.873,
    # -80.929,6999.999999999999 -178.785,
    # -80.929,6999.999999999999

    coords = []
    for coord in coords_txt.split(' '):
        coords.append(" ".join(coord.split(',')[:2]))  # keeping x,y removing z

    # MULTIPOLYGON(((
    # 179.938002683357 - 72.9727796803777, 179.755750140428 - 73.9555330546422, -176.683165143952 - 73.9797063483524,
    # -176.7009986188 - 72.9954805993986, 179.938002683357 - 72.9727796803777)))

    ll_wkt = "MULTIPOLYGON(((" + ",".join(coords) + ")))"
    meta['LL_WKT'] = ll_wkt
    """print path, row
    print coords
    print ll_wkt"""

    # get utm zone
    ctr_lon = float(pm.description.text.split('CTR LON</strong>:')[-1].split('<br>')[0])
    utm_zone = floor((ctr_lon + 180) / 6) + 1
    meta['UTM'] = utm_zone

    # get key/values pairs from kml description
    for key in ['WRS_ID', 'PATH', 'ROW', 'LL_WKT', 'UTM']:
        if key not in list(dic.keys()):
            # init list
            dic[key] = []
        # add values
        dic[key].append(meta[key])

df = pd.DataFrame.from_dict(dic)
dic = None

conn = sqlite3.connect('s2grid.db')
df.to_sql('l8tiles', conn)
conn.close()
