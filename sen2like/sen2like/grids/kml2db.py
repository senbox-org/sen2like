import sqlite3
from collections import OrderedDict

import pandas as pd
from pykml import parser


def readDescription(pm):
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


## MAIN ##

# KML can be downloaded on ESA website:
# https://sentinel.esa.int/documents/247904/1955685/S2A_OPER_GIP_TILPAR_MPC__20151209T095117_V20150622T000000_21000101T000000_B00.kml

# read kml as string
with open('S2A_OPER_GIP_TILPAR_MPC__20151209T095117_V20150622T000000_21000101T000000_B00.kml') as f:
    string = f.read()

# parse kml string with pykml
root = parser.fromstring(string)
print('nb tiles:', len(root.Document.Folder.Placemark))

# create empty dic with keys
dic = OrderedDict()

# now for each tile
for pm in root.Document.Folder.Placemark[0:]:
    # get tileid and description
    tileid = pm.name.text
    des = pm.description.text

    # get key/values pairs from kml description
    meta = readDescription(pm)
    for key in ['TILE_ID', 'EPSG', 'UTM_WKT', 'MGRS_REF', 'LL_WKT']:
        if key not in list(dic.keys()):
            # init list
            dic[key] = []
        # add values
        dic[key].append(meta[key])

df = pd.DataFrame.from_dict(dic)
conn = sqlite3.connect('s2grid.db')
df.to_sql('s2tiles', conn)
conn.close()

print('OK')
