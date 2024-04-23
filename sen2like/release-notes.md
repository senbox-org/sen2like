# Sen2Like Release Notes

## v4.4.3

### Fix

* Fix calculation of Sen2cor region of interest when target UTM differs from the input Landsat product UTM.

## v4.4.2

### Release of Sen2Cor3 documentation and software version 3.01.00

Instructions to retrieve sen2cor3 software and associated documentation available [here](../sen2cor3/README.md).

### Fix

* Force operational-mode parameter as first command line argument
* Remove `_pretty=` parameter in the creodias catalogue URL in the default configuration as it is no more supported by datahub catalogue.
* Update miniconda in [Dockerfile-base](Dockerfile-base)
* Typos in sen2like project [README.md](../README.md)

## v4.4.1

### Important information about sen2like on Creodias

If you are using sen2like on Creodias you should update your sen2like configuration to properly filter Landsat products due to changes in Creodias Opensearch catalog API.

Please refer to [Creodias config parameters chapter](README.md#creodias-api) and take a look at [default configuration sample file](conf/config.ini)

### Fix

* sen2cor was applied only to first product when enable to process a L1 stack
* Fix docker image build instructions in [README.md](README.md)
* TopographicCorrection post process fail if DEM is not present
* Replace finder catalog url by datahub catalog url and update landsat L1 product selection config sample, see [config parameters](README.md#creodias-api)
* Force 2D coordinates for roi file with 3D coordinates

## v4.4.0

### **Breaking changes**

* New mandatory parameters in GIPP XML and INI configuration file:
  * new section with new params : `DEMRepository`
  * new section with new params : `TopographicCorrection`
  * new section with new params : `Sbaf`
* Docker image build is now done in two step. [`Dockerfile`](Dockerfile) is based on a docker image that comes from [`Dockerfile-base`](Dockerfile-base) for reuse purpose.

### New features

* Add topographic correction (Experimental)
* Add DEM Downloader aux data utility to generate DEM in MGRS extent for topographic correction
* New adaptative SBAF capability (Experimental)

### Fix

### Improvements

* Design : Change the way to initialise processing block and to allow dependency injection in processing block classes.


## v4.3.0

### **Breaking changes**

* Bump Python version to 3.10 and dependencies update.

  **Please update your conda environnement or create a new one**

* Remove DEM downloader config parameters
* Remove catalog search filter `processingLevel` in default configuration due to changes in CREODIAS finder API.
  
  **Please do not use this parameter anymore, it is managed by code**

* Update to sen2cor 3.1

### New features

* Add support for PRISMA 4 Sen2like preprocessor output.

### Fix

* Image band parallelization process stability when using `--parallelize-bands` program argument.

### Improvements

* Design: 
  * Move product processing execution from main sen2like module into a new class `core.product_process.ProductProcess` (separation of concern)
  * Compute atmo corr parameters only once per product
  * Set product working dir in the `S2L_Product` instead of rebuild it every time need
  * Replace `metadata` singleton by an attribute in `S2L_Product`
  * `config` singleton no more modified for each product to process, replaced by a `ProcessContext` object attached to the product having variable config parameters.

* Remove unused module:
 
  * `atmcor/smac/COEFS/convert.py`
  * `atmcor/smac/COEFS/convert_from_GIPP.py`
  * `atmcor/smac/COEFS/diff_coeff.py`
  * `core/product_archive/dem_downloader.py`
  * `misc/SCL_to_valid_pixel_mask.py`
  * `misc/Test_retrieve_CAMS.py`
  * `misc/s2download.py`


## v4.2.1

### Known issues

* sen2like not stable when `--parallelize-bands` program argument is used

### Fix

- Fix Tile MTD ULY value


## v4.2.0

### **Breaking changes**

* The new feature `Reprojection` led to the following changes in the configuration files (config.ini and config.xml): 
  * `doGeometryKLT` config parameter is renamed to `doGeometry`
  * Add new `doGeometryCheck` config parameter
  * Remove runtime config parameter `freeze_dx_dy`
  * `force_geometric_correction` config param default value set to `True`
  * remove `reframe_margin` config parameter in `Stitching` section
* Remove legacy Packager : 
  * S2L_Packager module removed
  * Remove `doPackager` config parameter
* `Sen2Like_GIPP.xsd` updated in consequences, **don't forget to update your XML configuration file**
* Sen2Like new HABA AUX file: 
  *  New file naming convention following Sentinel 2 AUX data file naming convention
  *  HABA file attributes and bands management updates

### New features

* Reprojection : product in different geographic projection system (i.e. UTM zones) than the target MRGS tile to process can be processed or used for stitching. SRS stands for Spatial Reference System.
  * Add optional new sen2like program argument : `--allow-other-srs`, default `False`
  * Add optional new config param under `Stitching` section : `same_utm_only`, default `True`

### Fix

* Wrong tile coverage value logged with no-run parameter
* SBAF Param values in QI report of product generated from LS product

### Improvements

* Improve product correctness by updating generated MTD XML file compliant with `S2-PDGS-TAS-DI-PSD-V14.9_S2L-V4.2_Schema`

## v4.1.1

### Fix

* Fix QI report (L2H/F_QUALITY.xml files) not valid
* Fix MEAN_DELTA_AZIMUTH calculation for QI report
* Fix angles files extraction that leaded to random values in tie_points file and non reproducible results

## v4.1.0

### New features

* Add ROI based mode
* Sentinel-2 Collection-1 support
* Generated product compliant with Collection-1 format
* Possible mixed local/remote archive configuration
* Use sen2like version as baseline and real production date time in product MTD and product name
* Add some QI parameters
* Support sen2like 3.0.2

### Improvements

* Refactor Packagers to remove some code duplication
* Refactor Product MTD writer to remove some code duplication
* Factorize diverse duplicated code
* Move mask and angle file generation in a dedicated module (separation of concern)
* Move some function related to the configuration in S2L_Config module
* Code quality (WIP)
* Reduce docker image size of approximately 46%

## v4.0.2

### Fix

* Landsat: collection 2 support: fix BQA extraction (threshold)

### New features

* Sentinel-2: support of processing baseline 4.0 (L1 cloud mask as a raster)
* Landsat-9: Add support of local product archive

## v4.0.1

### Fix

* Bad access to landsat collection number.

## v4.0.0

### New features

* Use SpatiaLite open source library for on the fly computation of required Sentinel-2 MGRS Tiles / Landsat 8/9 WRS scenes  (replaced precalculate database).
* Use Sen2cor 3.0 (independent installation procedure) supporting L1 Collection-1 Landsat 8/9 with Region Of Interest (ROI) processing; the ROI defined by the MGRS footprint within the WRS scene is considered.
* In STAC catalog built by the generator, *href* are web url to request files and no longer their absolute path on file system.
* In the output band images, the 0 value is now reserved to nodata. Negative pixels potentially generated by Sen2like processing blocks (e.g. overcorrection from AtmCorr, NBAR) are clipped to minimum surface reflectance value of 0.0001. Corresponding to Digital Number (DN) = 1 in the image data.
* In the output band images (and only them), in COG and GeoTIFF, nodata pixels can be present (related to DN value 0), e.g. part of the image outside of the satellite acquisition swath.
* For the Quick looks images located in QI_DATA folder, the GDAL-generated aux.xml files contain now the correct scale/offset information for visualization (e.g. with QGIS) or statistics computation.
* In conversion to reflectance, sen2like now uses the radiometric offset written in input product metadata (if available like in Sentinel-2 with PB >= 04.00). 

### New environment

* Update GDAL to 3.3, OpenJPEG to 2.4 and Python to 3.7 and all their dependences

### Fixes

* Don't apply intercalibration on level 2 products.
* In Digital Number (DN) conversion to surface reflectance, Landsat Level-2 surface reflectance is independent of sun elevation (vs Landsat L1 TOA reflectance conversion)

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
