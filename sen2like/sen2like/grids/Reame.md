# Grids Tools 

Tools to build MGRS and WRS grids databases used to compute product tiles to process with sen2like and tile coverage.

## kml2s2tiles.py

Create MGRS databases

## wrskml2l8tiles.py

Create WRS-2 databases

This script needs path_row/utm lookup table file to properly set UTM zone info in the database.

Original file is [utm_zone_wrs2.lst](!utm_zone_wrs2.lst), it have been transform to [utm_zone_wrs2.csv](!utm_zone_wrs2.csv) for the script.