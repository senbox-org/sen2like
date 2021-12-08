# Sen2Like and STAC

Sen2like uses the pystac library to read and write STAC files.  
```pip install pystac```

## Generate STAC catalog

At the end of packagers, a stac file is generated in each product folder. This item is not registered in a catalog and
this catalog must then be created for the product to be reachable.

### Generate STAC catalog

The script ```sen2like/generate_stac_files.py``` generates a catalog for a given folder and stac files for all products.

```
>>> python generate_stac_files.py --help
usage: generate_stac_files.py [-h] [--is-tile] [--catalog-path CATALOG_PATH]
                              [--dry-run] [--cog]
                              path

positional arguments:
  path                  Path where to search for products

optional arguments:
  -h, --help            show this help message and exit
  --is-tile             Indicates if the path is a tile path
  --catalog-path CATALOG_PATH, -c CATALOG_PATH
                        Catalog path. If path does not exist it will be
                        created
  --dry-run             Only list products. Do not generate files.
  --cog                 Set image assets type to COG
```

Exemple for generating the catalog /data/S2L/sen2like_catalog.json for all products in /data/S2L:
```python generate_stac_files.py /data/S2L/ -c /data/S2L/sen2like_catalog.json```

Exemple for listing all products in /data/S2L/31TFJ

```python generate_stac_files.py /data/S2L/31TFJ --is-tile --dry-run```

## STAC requests

The file ```stac_requests.py``` contains functions to request the stac catalog.

It is possible to request by temporal extent by specifying a start and/or and end date.  
It is also possible to request products on a specific tile or ROI.

The main function is :

```
products_from_tile(catalog, tile, start_date, end_date)
```

where

* `_catalog` is an instance of a pystac catalog
* `tile` is the tile where to get
* `start_date` is the start of the temporal period
* `end_date` is the end of the temporal period

## STAC browser

### Build browser

Install nodejs  
```curl -sL https://rpm.nodesource.com/setup_10.x | sudo bash -```  
```sudo yum install nodejs```

Browser github  
```https://github.com/radiantearth/stac-browser/releases/tag/v1.0.1```

Move to extracted stac-browser folder  
```cd stac-browser```

Install node-modules  
```npm install```

Build with specification of catalog url and path proxy.
```CATALOG_URL=http://45.130.29.32/stac/sen2like_catalog.json STAC_PROXY_URL="/data/S2L|http://45.130.29.32/stac/S2L" npm run build```

CATALOG_URL: The stac catalog URL.  
STAC_PROXY_URL: The original location and the proxy location separated by the | character, i.e. {original}|{proxy}.

### Deploy browser

Once the browser is built, copy content of dist folder to /var/www/html/
```cp dist/* /var/www/html```
