# P4S2L (prisma4sen2like) <!-- omit in toc -->

![License: Apache2](https://img.shields.io/badge/license-Apache%202-blue.svg?&logo=apache)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?&logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-black.svg?)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?&labelColor=ef8336)](https://pycqa.github.io/isort/)

PRISMA 4 Sen2like is a Python application that aims to create Sentinel L1C level like product from PRISMA L1 product.

## Project status <!-- omit in toc -->

**Prototype**

## Table of content <!-- omit in toc -->

- [Installation](#installation)
- [Usage](#usage)
- [Use S2P products withe sen2like](#use-s2p-products-withe-sen2like)
- [Contributing](#contributing)
- [Authors and acknowledgment](#authors-and-acknowledgment)
- [License](#license)

## Installation

You need conda installed. We recommend to use minicoda with python 3.10.

https://docs.conda.io/en/latest/miniconda.html

```console
git clone https://github.com/senbox-org/sen2like.git
cd sen2like/prisma4sen2like
conda env create -f environment.yml
```

You're now ready to use the program.

For contribution, please read [contributing chapter](#contributing)

## Usage

Fist you MUST activate the conda environment: 

```console
conda activate prisma
```

Display help:

```console
PYTHONPATH=prisma python prisma/main.py -h
usage: main.py [-h] PRISMA_L1_FILE DESTINATION_FOLDER WORKING_DIR

positional arguments:
  PRISMA_L1_FILE      Prisma L1 he5 file
  DESTINATION_FOLDER  Generated S2P destination folder
  WORKING_DIR         Working directory

options:
  -h, --help          show this help message and exit
```

Usage example:

```console
PYTHONPATH=prisma python prisma/main.py \
  /data/Products/PRISMA/PRS_L1_STD_OFFL_20220714100507_20220714100511_0001.he5 \
  /data/Products/S2P \
  /data/wd
```

The log file shows the final product path, example: 

```
[INFO   ] [2023-06-15 07:51:23] product_builder.product_builder - Product available in /data/Products/S2P/S2P_MSIL1C_20220714T100509_N0000_R099_T33TTG_20230615T075030.SAFE
```

## Use S2P products withe sen2like

To process S2P products with sen2like, put them in the Sentinel-2 archive folder of sen2like.

## Contributing

Please install code quality tool and lib:

```bash
conda install -n prisma -c conda-forge --file requirements_dev.txt
pre-commit install && pre-commit install --hook-type pre-push
```

TODO : describe hooks

## Authors and acknowledgment

- Sebastien Saunier
- Jérôme Louis
- Patrice Canonici
- Vincent Debaecker

## License

Apache2

