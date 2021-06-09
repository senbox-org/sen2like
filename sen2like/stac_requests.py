import argparse
import datetime

import ogr
import pystac

from sen2like.core.product_archive.product_archive import InputProductArchive


def compute_tile_extent(mgrs_tile):
    """Deduce the tile(s) that is(are) needed for covering the input extent (e.g. MGRS tile extent).

    :param mgrs_tile: Input extent.
    :return: List of latitudes, longitudes corresponding to dem tiles.
    """
    tile_wkt = InputProductArchive.mgrs_to_wkt(mgrs_tile, utm=True)
    if tile_wkt is None:
        print("Cannot get geometry for tile {}".format(mgrs_tile))
    tile_geometry = ogr.CreateGeometryFromWkt(tile_wkt)
    extent = tile_geometry.GetEnvelope()
    print("Extent: {}".format(extent))
    if extent:
        lon_min, lon_max, lat_min, lat_max = extent
        return lon_min, lat_min, lon_max, lat_max
    else:
        print("Error while computing tile extent.")
    return None


def products_from_roi(catalog, roi, start_date, end_date):
    tiles = InputProductArchive.roi_to_tiles(roi)
    tile=None
    extent = compute_tile_extent(tile)
    if extent is None:
        print(f"Cannot compute extent for tile {tile}")
        return


    return {tile: products_from_tile(catalog, tile, start_date, end_date) for tile in tiles}


def products_from_tile(catalog, tile, start_date, end_date):
    children = catalog.get_children()
    tile_child = [child for child in children if child.title == tile]
    if len(tile_child) != 1:
        print('Cannot find one catalog for tile %s' % tile)
        return
    tile_catalog = tile_child[0]

    if start_date:
        start_date = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    if end_date:
        end_date = end_date.strftime("%Y-%m-%dT23:59:59")

    results = []
    for root, subcats, items in tile_catalog.walk():
        for item in items:
            is_valid = True
            item_date = item.datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
            if start_date:
                is_valid &= start_date <= item_date
            if end_date:
                is_valid &= item_date <= end_date
            if is_valid:
                results.append(item)

    return results


def band_url_from_product(product, band):
    return product.get_assets().get(band).href


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument("--catalog", help="STAC catalog", dest="catalog", required=True)
    parser.add_argument("--start-date", dest="start_date", help="Beginning of period (format YYYY-MM-DD)",
                        default='')
    parser.add_argument("--end-date", dest="end_date", help="End of period (format YYYY-MM-DD)",
                        default='')

    parser.add_argument("--request", choices=['tile', 'roi'], required=True)
    parser.add_argument("request_content", help="The MGRS tile or roi depending on choice.")

    parser.add_argument("--print", help="Display products", action='store_true')

    args = parser.parse_args()

    _catalog = pystac.read_file(args.catalog)

    start_date = datetime.datetime.strptime(args.start_date, "%Y-%m-%d") if args.start_date else args.start_date
    end_date = datetime.datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else args.end_date

    # start_date = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    # end_date = end_date.strftime("%Y-%m-%dT23:59:59")

    if args.request == 'tile':
        _products = {args.request_content: products_from_tile(_catalog, args.request_content, start_date, end_date)}
    else:
        _products = products_from_roi(_catalog, args.request_content, start_date, end_date)
    for _tile in _products:
        if args.print:
            for _product in _products[_tile]:
                print(_product.id)
                for band in _product.get_assets():
                    print(f"\t{band} : {band_url_from_product(_product, band)}")
                print()
        print()
        print(f"tile {_tile} : {len(_products[_tile])} products found")
