# Sen2Cor 3 version 3.02.00

## Retrieve Sen2cor 3.02.00 documentation from sftp server

```
hostname = 'sftp.telespazio.fr'
port = 22  # default SFTP port is 22
username = 'sen2cor3'
password = '4sen2like'
remote_path = '/upload/Sen2Cor-3.02.00/Documentation/'
```

**_Sen2cor 3.02.00 Software Release Note:_**  
sftp://sen2cor3@sftp.telespazio.fr/upload/Sen2Cor-3.02.00/Documentation/OMPC.TPZ.SRN.002%20-%20i1r0%20-%20Sen2Cor%203.02.00%20Software%20Release%20Note.pdf

**_Sen2cor 3.02.00 Software Configuration and User Manual:_**  
sftp://sen2cor3@sftp.telespazio.fr/upload/Sen2Cor-3.02.00/Documentation/OMPC.TPZ.SUM.002%20-%20i1r0%20-%20Sen2Cor%203.02.00%20Configuration%20and%20User%20Manual.pdf

## Retrieve Sen2cor 3.02.00 software from sftp server

Either with a software like Filezilla:

```
hostname = 'sftp.telespazio.fr'
port = 22  # default SFTP port is 22
username = 'sen2cor3'
password = '4sen2like'
remote_path = '/upload/Sen2Cor-3.02.00/Software/sen2cor_3.2.0_python_3.10_20241218.zip'
```

e.g: sftp://sen2cor3@sftp.telespazio.fr/upload/Sen2Cor-3.02.00/Software/sen2cor_3.2.0_python_3.10_20241218.zip

or with the example script "sen2cor3_download.py" based on "paramiko" module.  
It requires paramiko version 3.4.0 that could be installed with conda [see below](#create-the-sen2like-conda-environment):

```
conda activate sen2like
conda install paramiko=3.4.0 -c conda-forge
```

```
python sen2cor3_download.py sen2cor3_install_dir
```

## Unzip sen2cor_3.2.0_python_3.10.zip into the Sen2Cor 3 directory of your choice

```
e.g. sen2cor3_install_dir=/opt/sen2cor3/code/
cd $sen2cor3_install_dir
unzip sen2cor_3.2.0_python_3.10.zip
```

## Auxiliary Data Symbolic linking

Sen2Cor3 relies on a set of external auxiliary data that needs to be available in Sen2Cor3 "aux_data" folder:
- ECMWF CAMS data: daily, monthly
- ESA CCI files
- Copernicus DEM files

Further details are available in Sen2Cor3 Software User Manual.

Examples of symbolic linking is given hereafter:
- symbolic linking of your local CAMS folder that contains daily CAMS data e.g. /data/CAMS/daily
- symbolic linking of your local ESA CCI files e.g. /data/AUX_DATA/


```
cd $sen2cor3_install_dir/sen2cor_3.2.0_python_3.10/SEN2COR_3/aux_data
ln -s /data/CAMS/daily ./ECMWF/daily
ln -s /data/AUX_DATA/ESACCI-LC-L4-Snow-Cond-500m-MONTHLY-2000-2012-v2.4 ./ESACCI-LC-L4-Snow-Cond-500m-MONTHLY-2000-2012-v2.4
ln -s /data/AUX_DATA/ESACCI-LC-L4-WB-Map-150m-P13Y-2000-v4.0.tif ./ESACCI-LC-L4-WB-Map-150m-P13Y-2000-v4.0.tif
ln -s /data/AUX_DATA/ESACCI-LC-L4-LCCS-Map-300m-P1Y-2015-v2.0.7.tif ./ESACCI-LC-L4-LCCS-Map-300m-P1Y-2015-v2.0.7.tif
```

## Install miniconda if conda is not already installed on your system

https://repo.anaconda.com/miniconda/Miniconda3-py37_22.11.1-1-Linux-x86_64.sh

## Create the sen2like conda environment

Once you retrieved the code, go into Sen2Cor3 root source folder and run the following command to create a conda env named sen2like:

```
cd $sen2cor3_install_dir/sen2cor_3.2.0_python_3.10
conda create -n sen2like --file requirements.txt -c conda-forge
```

## Activate sen2like conda environment

Sen2Cor 3.2 uses the same conda environment as Sen2like:

``` 
conda activate sen2like
```

### Test the Command line execution

```
python $sen2cor3_install_dir/sen2cor_3.2.0_python_3.10/SEN2COR_3/L2A_Process.py --help

output:
usage: L2A_Process.py [-h] [--mode MODE] [--resolution {10,20,30,60}] [--datastrip DATASTRIP] [--tile TILE] [--output_dir OUTPUT_DIR] [--work_dir WORK_DIR]
                      [--img_database_dir IMG_DATABASE_DIR] [--res_database_dir RES_DATABASE_DIR] [--processing_centre PROCESSING_CENTRE] [--archiving_centre ARCHIVING_CENTRE]
                      [--processing_baseline PROCESSING_BASELINE] [--raw] [--tif] [--sc_only] [--sc_classic] [--sc_cog] [--cr_only] [--debug] [--GIP_L2A GIP_L2A]
                      [--GIP_L2A_SC GIP_L2A_SC] [--GIP_L2A_AC GIP_L2A_AC] [--GIP_L2A_PB GIP_L2A_PB] [--Hyper_MS]
                      input_dir

Sen2Cor. Version: 03.02.00, created: 2024.12.18, supporting Level-1C product version 15.0, supporting Level-1TP Collection_1-2 Landsat_8-9, supporting Hyper MS Level-1C.

positional arguments:
  input_dir             Directory of Level-1C input

options:
  -h, --help            show this help message and exit
  --mode MODE           Mode: generate_datastrip, process_tile
  --resolution {10,20,30,60}
                        Target resolution, can be 10, 20 or 60m for S2, 30m for Hyper. If omitted, only 20 and 10m resolutions will be processed
  --datastrip DATASTRIP
                        Datastrip folder
  --tile TILE           Tile folder
  --output_dir OUTPUT_DIR
                        Output directory
  --work_dir WORK_DIR   Work directory
  --img_database_dir IMG_DATABASE_DIR
                        Database directory for L1C(H) input images
  --res_database_dir RES_DATABASE_DIR
                        Database directory for results and temporary products
  --processing_centre PROCESSING_CENTRE
                        Processing centre as regex: ^[A-Z_]{4}$, e.g "SGS_"
  --archiving_centre ARCHIVING_CENTRE
                        Archiving centre as regex: ^[A-Z_]{4}$, e.g. "SGS_"
  --processing_baseline PROCESSING_BASELINE
                        Processing baseline in the format: "dd.dd", where d=[0:9]
  --raw                 Export raw images in rawl format with ENVI hdr
  --tif                 Export raw images in TIFF format instead of JPEG-2000
  --sc_only             Performs only the scene classification at 60 or 20m resolution, 30m for Hyper
  --sc_classic          Performs scene classification in Sen2Cor 2.9 mode
  --sc_cog              Export SCL image in COG format instead of JPEG_2000
  --cr_only             Performs only the creation of the L2A product tree, no processing
  --debug               Performs in debug mode
  --GIP_L2A GIP_L2A     Select the user GIPP
  --GIP_L2A_SC GIP_L2A_SC
                        Select the scene classification GIPP
  --GIP_L2A_AC GIP_L2A_AC
                        Select the atmospheric correction GIPP
  --GIP_L2A_PB GIP_L2A_PB
                        Select the processing baseline GIPP
  --Hyper_MS            To Process a Hyper_MS product


``` 



