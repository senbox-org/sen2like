# Sen2Like


## Local install

### check installation of tools for install

`sudo apt-get install curl git`

#### Retrieve sources of Sen2Like code

* Using git (restricted to telespazio):

`git clone git@gitlab.telespazio.fr:SEN2LIKE/poleeo.git`

* Or from a downloaded archive:

`unzip sen2like.zip`

`cd sen2like`

### Installation of Anaconda or Miniconda

* Installing Anaconda:

`curl  https://repo.anaconda.com/archive/Anaconda3-2020.02-Linux-x86_64.sh --output  Anaconda3-2020.02-Linux-x86_64.sh`

`chmod +x Anaconda3-2020.02-Linux-x86_64.sh`

`./Anaconda3-2020.02-Linux-x86_64.sh`

* or Miniconda:

`curl https://repo.anaconda.com/miniconda/Miniconda3-py37_4.8.2-Linux-x86_64.sh --output Miniconda3-py37_4.8.2-Linux-x86_64.sh`

`chmod +x Miniconda3-py37_4.8.2-Linux-x86_64.sh`

`./Miniconda3-py37_4.8.2-Linux-x86_64.sh`

### Create a conda virtual environment with required packages

`conda create -n sen2like --file requirements.txt -c conda-forge`

### Activate conda virtual environment

`conda activate sen2like`

### Installation of dependencies

`sudo apt-get install mesa-libGL`

## Docker creation

### Docker environement install

#### On Ubuntu

* Docker install method availlable for ubuntu when writing this file "2020-09" check for current date and os

`sudo apt-get remove docker docker-engine docker.io containerd runc`

`sudo apt-get install apt-transport-https ca-certificates curl software-properties-common`

`curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -`

`sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable`

`sudo apt-get update`

`sudo apt-get install docker-ce`

`sudo usermod -aG docker ${USER}`

log out and log in to get changes applied

#### On Centos 7

`sudo yum install -y yum-utils`

`sudo yum-config-manager \
    --add-repo \
    https://download.docker.com/linux/centos/docker-ce.repo`

`sudo yum install docker-ce docker-ce-cli containerd.io`

`sudo usermod -aG docker ${USER}`

log out and log in to get changes applied

### Retrieve sources of Sen2Like code

* Using git (restricted to telespazio):

`git clone https://gitlab.telespazio.fr/SEN2LIKE/poleeo.git`

* Or from a downloaded archive:

`unzip sen2like.zip`

`cd sen2like`

### Docker build

Build docker image from Dockerfile:

`cd ./poleeo/HLS-project`

`docker build -t sen2like .`

### Docker store in repository

Tag the image so that is points to registry

`docker image tag <IMAGE_NAME> <REGISTRY_URL>`

sample

`docker image tag sen2like https://tpz-ssa-docker-registry.telespazio.fr`

Push the image on registry

`docker push <REGISTRY_URL><IMAGE_NAME>`

sample

`docker push https://tpz-ssa-docker-registry.telespazio.fr/sen2like`

 reminder to allow acces to docker registry https://tpz-ssa-docker-registry.telespazio.fr you should
 
  * have an account on the registry
  * update or add /etc/docker/daemon.json with { "insecure-registries" : ["https://tpz-ssa-docker-registry.telespazio.fr"] }
  * restart docker daemon `systemctl restart docker`



## Running the tool

### running on local install

After install.

Python script sen2like.py could be found in cloned git repository, or unzipped folder.

For exemple if git cloned in home directory: 

`/opt/anaconda3/bin/python "$HOME/poleeo/HLS-project/sen2like/sen2like.py" single-tile-mode 31TFJ --conf "./config.ini" --start-date 2017-10-30 --end-date 2017-10-31 --wd "/data/production" --refImage "/data/References/GRI/S2A_OPER_MSI_L1C_TL_MPS__20161018T120000_A000008_T31TFJ_N01.01/IMG_DATA/S2A_OPER_MSI_L1C_TL_MPS__20161018T120000_A000008_T31TFJ_B04.jp2" --bands B04`

### running in docker

After pulling the docket from registry

`docker pull <REGISTRY_URL><IMAGE_NAME>`

sample

`docker pull https://tpz-ssa-docker-registry.telespazio.fr/sen2like`

 reminder to allow access to docker registry https://tpz-ssa-docker-registry.telespazio.fr you should
 
  * have an account on the registry
  * update or add /etc/docker/daemon.json with { "insecure-registries" : ["https://tpz-ssa-docker-registry.telespazio.fr"] }
  * restart docker daemon `systemctl restart docker`

Python script sen2like.py could be accessed from docker.

* remark in this sample **local** folder `/data` is supposed to exist and contain sen2like config file `/data/config.ini` a folder for working `/data/production` and the reference image `/data/References/GRI/S2A_OPER_MSI_L1C_TL_MPS__20161018T120000_A000008_T31TFJ_N01.01/IMG_DATA/S2A_OPER_MSI_L1C_TL_MPS__20161018T120000_A000008_T31TFJ_B04.jp2`
 
Launch the docker binding local /data folder to docker internal /data folder

`docker run -it --mount type=bind,source="/data",target=/data tpzf-ssa-docker-registry.telespazio.fr/sen2like/sen2like:3.0`

In prompt activate sen2like env and execute ./sen2like.py

`python ./sen2like.py single-tile-mode 31TFJ --conf "/data/config.ini" --start-date 2017-10-30 --end-date 2017-10-31 --wd "/data/production" --refImage "/data/References/GRI/S2A_OPER_MSI_L1C_TL_MPS__20161018T120000_A000008_T31TFJ_N01.01/IMG_DATA/S2A_OPER_MSI_L1C_TL_MPS__20161018T120000_A000008_T31TFJ_B04.jp2" --bands B04`


### sen2like usage

Sen2like can be run in three different modes:

* `product-mode`: Run the tool on a singe product
* `single-tile-mode`: Run the tool on a MGRS tile. Corresponding products will be loaded.
* `multi-tile-mode`: Run the tool on a ROI defined in a geojson. 
Corresponding MGRS tile will be inferred and products will be loaded. It is equivalent to run a single-tile mode
for each matching tile. In multi-tile mode, multiprocessing can be used to speed-up computation time.

The configuration of the tool is done by command-line arguments and by a configuration file.
A default configuration file is provided in `conf/config.ini`.

### Configuration file
Two configuration file formats are supported:

* Ini file
* GIPP file (xml-like)

The configuration file is divided in several parts, each describing specific block of processing.

#### Processing
Enable or disable a processing block based on value `(True, False)`:

* `doStitching`: Run the stitching processing
* `doGeometryKLT`: Run the geometric correction processing using KLT
* `doToa`: Run the TOA correction
* `doAtmcor`: Run the Atmospheric correction
* `doNbar`: Run Nbar correction processing
* `doSbaf`: Run the Sbaf correction processing
* `doFusion`: Run the Fusion processing
* `doPackager`: Run the packaging processing

#### Directories
Indicates path for special directories:

* `archive_dir`: Where to store resulting products
* `cams_dir`: Where are located CAMS files

#### Downloader
Describes parameters for product acquisition.

By default, two method are described:

* **local**: products are stored in local
* **creodias**: products are located using the creodias api

Other access method can be defined by defining custom attributes, in order to use other API.

To define path, custom attributes can be defined in the configuration file.

* `coverage`: Define the coverage of the product tile in the interval [0, 1 ] (0-100%)

In addition these parameters are defined in the tool and can be used in brackets `{}`:

* `mission`: `Landsat8` or `Sentinel2`
* `tile`: MGRS tile
* `path`: WRS path
* `row`: WRS row

##### Local 
* `base_url`: Specify where the products are stored
* `url_parameters_pattern_Sentinel2`: Describe storage path for Sentinel 2 products
* `url_parameters_pattern_Landsat8`: Describe storage path for Landsat 8 products 

For a Sentinel 2 product on tile 31TFJ:
```
base_url = /data/PRODUCTS
url_parameters_pattern_Sentinel2 = {base_url}/{mission}/{tile}
```
will be replaced by:

```url_parameters_pattern_Sentinel2 = /data/PRODUCTS/Sentinel2/31TFJ```

##### Creodias API
* `base_url` = Base address of the api
* `cloud_cover` = Maximum cloud cover [0, 100]
* `location_Landsat8` = Expression specifiying Landsat 8 filter
* `location_Sentinel2` = Expression specifiying Seninel 2 filter
* `url_parameters_pattern` = API request url. Special parameters between brackets are replaced by defined attributes
* `thumbnail_property` = Path in result json where product path is stored
* `cloud_cover_property` = Path in result json where cloud cover is stored

#### Geometry
Define parameters for geometric correction.

* `reference_band`= The reference band to use for geometric correction
* `doMatchingCorrection`: Apply the matching correction (`True`, `False`)
* `doAssessGeometry`: Assess geometry (Band list separated by comma.)

#### Atmcor
Atmospheric method to use.

* `use_sen2cor`: Activate sen2cor for Atmospheric correction (SMAC otherwise)
* `sen2cor_path`: Path to sen2cor tool

#### fusion
Define parameters for fusion processing.

* `predict_method` : Predic method to use (predict or composite using most recent valid pixels)
* `predict_nb_products`: Number of products needed by predict method

#### Stitching
Define parameters for stitching processing.

* `reframe_margin`: Margin to add during stitching reframing

#### OutputFormat
Define modifier for written image file.

* `gain`: Gain multplier for output image
* `offset`: Offset to add to the output image

#### Multiprocessing
Define parameters for multiprocessing in multi-tile-mode.

* `number_of_process`: Maximum number of processes to start

#### Packager
Define packaging parameters.

* `quicklook_jpeg_quality`: Quality for outputs quicklooks 

#### Runtime
This section is overriden during runtime and contains backup of computed values.
Modifying this section will have no effect.

### Command line arguments 
The help of the tool can be displayed with the command:
`python sen2like\sen2like.py --help`

```
usage: sen2like.py [-h] [-v] [--refImage PATH] [--wd PATH] [--conf PATH]
                   [--confParams STRLIST] [--bands STRLIST]
                   [--no-run] [--intermediate-products] [--debug]
                   [--no-log-date]
                   {product-mode,single-tile-mode,multi-tile-mode} ...

positional arguments:
  {product-mode,single-tile-mode,multi-tile-mode}
                        Operational mode
    product-mode        Process a single product
    single-tile-mode    Process all products on a MGRS tile
    multi-tile-mode     Process all products on a ROI

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
  --refImage PATH       Reference image (use as geometric reference)
  --wd PATH             Working directory (default : /data/production/wd)
  --conf PATH           S2L_configuration file (Default:
                        SEN2LIKE_DIR/conf/S2L_config.ini)
  --confParams STRLIST  Overload parameter values (Default: None). Given as a
                        "key=value" comma-separated list.Example: --confParams
                        "doNbar=False,doSbaf=False"
  --bands STRLIST       Bands to process as coma separated list (Default: ALL
                        bands)
  --no-run              Do not start process and only list products (default:
                        False)
  --intermediate-products
                        Generate intermediate products (default: False)

Debug arguments:
  --debug, -d           Enable Debug mode (default: False)
  --no-log-date         Do no store date in log (default: False)

```

#### Product mode
In product mode, a product is specified an processed by the tool.

The help of the product-mode can be displayed with the command:

`python sen2like\sen2like.py product-mode --help`

```
usage: sen2like.py product-mode [-h] [-v] [--refImage PATH] [--wd PATH]
                                [--conf PATH] [--confParams STRLIST]
                                [--bands STRLIST] [--no-run]
                                [--intermediate-products] [--debug]
                                [--no-log-date] --tile TILE
                                product

positional arguments:
  product               Landsat8 L1 product path / or Sentinel2 L1C product
                        path

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
  --refImage PATH       Reference image (use as geometric reference)
  --wd PATH             Working directory (default : /data/production/wd)
  --conf PATH           S2L_configuration file (Default:
                        SEN2LIKE_DIR/conf/S2L_config.ini)
  --confParams STRLIST  Overload parameter values (Default: None). Given as a
                        "key=value" comma-separated list.Example: --confParams
                        "doNbar=False,doSbaf=False"
  --bands STRLIST       Bands to process as coma separated list (Default: ALL
                        bands)
  --no-run              Do not start process and only list products (default:
                        False)
  --intermediate-products
                        Generate intermediate products (default: False)
  --tile TILE           Id of the MGRS tile to process

Debug arguments:
  --debug, -d           Enable Debug mode (default: False)
  --no-log-date         Do no store date in log (default: False)
```

Example of command line:

`python sen2like.py product-mode
/eodata/Sentinel-2/MSI/L1C/2017/01/03/S2A_MSIL1C_20170103T104432_N0204_R008_T31TFJ_20170103T104428.SAFE
--wd
~/wd
--tile
31TFJ
--bands B04
`

#### Single tile mode
In single-tile mode, a MGRS tile is specified an processed by the tool.

The help of the single-tile-mode can be displayed with the command:

`python sen2like\sen2like.py single-tile-mode --help`

```
usage: sen2like.py single-tile-mode [-h] [--start-date START_DATE]
                                    [--end-date END_DATE] [-v]
                                    [--refImage PATH] [--wd PATH]
                                    [--conf PATH] [--confParams STRLIST]
                                    [--bands STRLIST] [--no-run]
                                    [--intermediate-products] [--debug]
                                    [--no-log-date]
                                    tile

positional arguments:
  tile                  Id of the MGRS tile to process

optional arguments:
  -h, --help            show this help message and exit
  --start-date START_DATE
                        Beginning of period (format YYYY-MM-DD)
  --end-date END_DATE   End of period (format YYYY-MM-DD)
  -v, --version         show program's version number and exit
  --refImage PATH       Reference image (use as geometric reference)
  --wd PATH             Working directory (default : /data/production/wd)
  --conf PATH           S2L_configuration file (Default:
                        SEN2LIKE_DIR/conf/S2L_config.ini)
  --confParams STRLIST  Overload parameter values (Default: None). Given as a
                        "key=value" comma-separated list.Example: --confParams
                        "doNbar=False,doSbaf=False"
  --bands STRLIST       Bands to process as coma separated list (Default: ALL
                        bands)
  --no-run              Do not start process and only list products (default:
                        False)
  --intermediate-products
                        Generate intermediate products (default: False)

Debug arguments:
  --debug, -d           Enable Debug mode (default: False)
  --no-log-date         Do no store date in log (default: False)
```

Example of command line:

`python sen2like.py single-tile-mode
31TFJ
--wd
~/wd
--refImage
/data/HLS/31TFJ/L2F_31TFJ_20170103_S2A_R008/L2F_31TFJ_20170103_S2A_R008_B04_10m.TIF
`

#### Multi tile mode
In multi-tile mode, a geojson file is specified an processed by the tool.
An example of geojson file containing tile 31TFJ is located in `conf/tile_mgrs_31TFJ.json`.

The help of the multi-tile-mode can be displayed with the command:

`python sen2like\sen2like.py multi-tile-mode --help`

```
usage: sen2like.py multi-tile-mode [-h] [--start-date START_DATE]
                                   [--end-date END_DATE] [--jobs JOBS] [-v]
                                   [--refImage PATH] [--wd PATH] [--conf PATH]
                                   [--confParams STRLIST] [--bands STRLIST]
                                   [--no-run]
                                   [--intermediate-products] [--debug]
                                   [--no-log-date]
                                   roi

positional arguments:
  roi                   Json file containing the ROI to process

optional arguments:
  -h, --help            show this help message and exit
  --start-date START_DATE
                        Beginning of period (format YYYY-MM-DD)
  --end-date END_DATE   End of period (format YYYY-MM-DD)
  --jobs JOBS, -j JOBS  Number of tile to process in parallel
  -v, --version         show program's version number and exit
  --refImage PATH       Reference image (use as geometric reference)
  --wd PATH             Working directory (default : /data/production/wd)
  --conf PATH           S2L_configuration file (Default:
                        SEN2LIKE_DIR/conf/S2L_config.ini)
  --confParams STRLIST  Overload parameter values (Default: None). Given as a
                        "key=value" comma-separated list.Example: --confParams
                        "doNbar=False,doSbaf=False"
  --bands STRLIST       Bands to process as coma separated list (Default: ALL
                        bands)
  --no-run              Do not start process and only list products (default:
                        False)
  --intermediate-products
                        Generate intermediate products (default: False)

Debug arguments:
  --debug, -d           Enable Debug mode (default: False)
  --no-log-date         Do no store date in log (default: False)
```

Example of command line:

`python sen2like.py multi-tile-mode
ROI_FILE
--wd
~/wd
--refImage
/data/HLS/31TFJ/L2F_31TFJ_20170103_S2A_R008/L2F_31TFJ_20170103_S2A_R008_B04_10m.TIF
`

## [Release notes](release-notes.md)

## License
[Apache License 2.0](LICENSE.txt)