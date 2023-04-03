
Sen2Like - how to start
==============================

## Quick start

Follow [sen2like/README.md](sen2like/README.md#local-install) instruction to install sen2like and activate his environment.


### Input and output directories in config parameters

Before launching command, it is mandatory to define location of data sources and
location of Sen2Like output products.

#### Data Sources
<center><ins>Copy sen2like/conf/config.ini in your work directory and start editing the file</ins></center>

In Sen2Like two categories of data sources exist: **local data source** and **remote data source**. 
Herein, It is assumed  that products are stored on your system, it is a local data source.

To plug a local data sources, two actions are required 

-   Set the value of `base_url` parameter
-   Organize input product directories breakdown structure accordingly

<center><ins>Set value of base_url parameter</ins></center>

`base_url` parameter is the root directory where all input products are stored

<center><ins>Organize input product directories</ins></center>

When relevant create mission dependant directory:
- For Sentinel-2 data create directory  `base_url`/Sentinel2
- For Landsat 8 respectively Landsat 9 create directory
  `base_url`/Landsat8, `base_url`/Landsat9,
  
When relevant create scene dependant directories 
- For Sentinel-2 data create MGRS Code directory in `base_url`/Sentinel2
  
   _Example: /data/PRODUCTS/Sentinel2/31TFJ_ 
- For Landsat 8 create WRS PATH / WRS ROW directories in `base_url`/Landsat8
  
   _Example: /data/PRODUCTS/Landsat8/181/40_ 

At command launch, Sen2like will search Sentinel-2, Landsat 8 products accordingly.

<center><ins>Move products into the scene dependant directories</ins></center>

   _Example 1: For tile 31TFJ, all sentinel products are stored in /data/PRODUCTS/Sentinel2/31TFJ_

   _Example 2: S2A_MSIL1C_20211016T103031_N0301_R108_T31TFJ_20211016T124013.SAFE is stored in /data/PRODUCTS/Sentinel2/31TFJ_

   _Example 3:LC81960302017318MTI00 is stored in /data/PRODUCTS/Landsat8/196/30_


#### Output product directory
<center><ins> Create archive directory </ins></center>
The config parameter `archive_dir` is the root directory where all output products will be stored by sen2like. 
In `archive_dir` products are always stored in the same path :  `{archive_dir}/{tile}`.

It is worth noting that parameters in configuration file can be overriden with `--confParams` sen2like command interface.
The usage of this interface is not discussed in this tutorial.


### Command examples

#### Simple example

List L1C products on tile 31TFJ between 2017-01-01 and 2017-02-01:
```
python sen2like/sen2like/sen2like.py single-tile-mode 31TFJ --wd wd --config ./config.ini --start-date 2017-01-01 --end-date 2017-02-01 --no-run
```

Run sen2like on them:
```
python sen2like/sen2like/sen2like.py single-tile-mode 31TFJ --wd wd --config ./config.ini --start-date 2017-01-01 --end-date 2017-02-01
```

`wd` is the work directory where intermediate images will be stored.

For more information on execution, you can print more logs and save intermediate products in work directory with the following options:
```
python sen2like/sen2like/sen2like.py single-tile-mode 31TFJ --wd wd --config ./config.ini --start-date 2017-01-01 --end-date 2017-02-01 --debug --intermediate-products
```
