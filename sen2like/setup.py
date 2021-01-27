from setuptools import setup, find_packages

from sen2like.version import __version__


def read_file(file_name):
    with open(file_name) as fp:
        return fp.read()


setup(
    name='sen2like',
    version=__version__,
    package_dir={'': 'sen2like'},
    packages=find_packages('', exclude=['tests']),
    include_package_data=True,
    license=read_file('LICENSE.txt'),
    description='',
)
