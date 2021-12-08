# Sen2Like Release Notes

## v3.3.0

### New features

* BRDF correction (in Nbar) can use VJB coefficient in place of ROY
* Add new module for intercalibration correction
* Use SCL file, if exist, to compute mask.
* Add a fusion auto check and his result in intermediate product and output
* Local product are now filter by cloud cover as creodias product

### New environment

* Add mgrs 1.4.0 module to requirement

### Fixes

* Add cloud coverage in output sen2like landsat product metadata

## v3.2.0

### New features

* Add support for new products
    * Maja products
    * Landsat-8 Collection 2
    * Landsat-9
* Disable geometric correction for refined products
* In Atmospheric correction, add a reader for CAMS daily data
* Metadata are also written in json format
* Add per-band parallelization
* Add a parameter to force geometric correction
* Add support for JPEG2000 output format in configuration file
* Add a downloader for Copernicus DEM
* Generate stac items for output products

### Fixes

* Fix image format written in metadata file
* Harmonize L8 tile/granule ID with S2
* For S2 products replace the granuleIdentifier by the virtual full PDGS filename

## v3.1.1

### Fixes

* Packagers L2H and L2F can now be both activated at same time
* Output files are now created only at expected resolutions
* Outputs band files for Packagers L2H and L2F now use S2 band names
* Update COG options in configuration file
* QuickLook for SWIR-NIR now use B12, B11 and B8A
* Fix native thermal bands outputs for L8 products

## v3.1

### New features

* Integration of sen2cor (preliminary version)
* Add support for L2A products
* Improve CAMS data management (use of monthly, hourly and climatology data)
* New L2F / L2H output formats
* Bands for geometry assessment can now be specified in configuration file
* Add support for COG output format in configuration file

### Fixes

* [GIPP] parameters are missing in the xml compared to the .ini file
* [GIPP] the xsd file is not found if processor not run from its own directory
* [Stitching] takes always previous row product.
* [Mutli-Tile] fails when parallelisation is enabled
