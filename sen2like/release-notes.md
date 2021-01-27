# Sen2Like Release Notes

## v3.1.2

### Fixes

* Fix S2 band naming in output
* Do not resample S2 images to 30m
* Downsample band to 30m during fusion if needed
* Fix COG levels in configuration file
* Fix QL naming in metadata

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
