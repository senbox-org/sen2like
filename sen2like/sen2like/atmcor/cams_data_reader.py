import datetime
import glob
import logging
import os
from datetime import timedelta
from math import floor, ceil

from osgeo import gdal
import numpy as np
from netCDF4 import Dataset

from core.S2L_config import S2L_Config

log = logging.getLogger("Sen2Like")


class ECMWF_Product:
    mandatory_attributes = ['aod550', 'gtco3', 'msl', 'tcwv']
    expected_attributes = ['longitude',
                           'latitude',
                           'time',
                           'tcwv',
                           'msl',
                           't2m',  # Not required
                           'gtco3',
                           'aod',
                           'aod550',
                           'aod469',
                           'aod670',
                           'aod1240'
                           ]

    def __init__(self, cams_config, observation_datetime=None):
        """ Initialize CAMS data reader.

        :param observation_datetime - Optional parameter
        """
        self.cams_monthly_dir = cams_config.get('default')
        self.cams_daily_directory = cams_config.get('daily')
        self.cams_hourly_directory = cams_config.get('hourly')
        self.cams_climatology_directory = cams_config.get('climatology')

        self.observation_datetime = observation_datetime
        self.observation_date = None
        self.observation_date_hour = None
        self.cams_date_hour = None
        self.latitude = None
        self.longitude = None

        # Set initial array to None
        for att in self.expected_attributes:
            setattr(self, att, None)

        if observation_datetime is None:
            return
        doy = self.observation_datetime.timetuple().tm_yday
        log.debug("Day of year: %d" % doy)

        log.info('Initialize ECMWF Product')
        self.is_valid = True
        if self.cams_monthly_dir is not None:
            self.read_cams_monthly()
        else:
            log.warning('No CAMS directory defined. Check configuration.')

        # If some attributes are incomplete, try to complete them
        for parameter in self.mandatory_attributes:
            if getattr(self, parameter) is None and self.cams_daily_directory is not None:
                log.warning('No %s found, try to find daily data' % parameter)
                self.read_cams_daily(parameter)
            if getattr(self, parameter) is None and self.cams_hourly_directory is not None:
                log.warning('No %s found, try to find hourly data' % parameter)
                self.read_cams_hourly(parameter)
            if getattr(self, parameter) is None and self.cams_climatology_directory is not None:
                log.warning('No %s found, try to find climatology data' % parameter)
                self.read_cams_climatology(doy, parameter)
            if getattr(self, parameter) is None:
                log.error('No valid CAMS data found for datetime: %s' % str(observation_datetime))
                log.info('Note that the CAMS monthly database for the Year 2020 is available : '
                         'http://185.178.85.51/CAMS/')
                self.is_valid = False
                return

    def read_date_values(self, hour, ncfile, parameter):
        """Retrieve the ECMWF CAMS parameter for the given date.

        :param parameter: The parameter to read
        :param hour: Time at which date is searched
        :param ncfile: ncfile to read
        :return: Read data
        """
        rootgrp = Dataset(ncfile, 'r')
        nctimes = rootgrp.variables['time'][:]
        if hour not in nctimes:
            log.error('CAMS ncfile: TIME ERROR: {0} is not found in {1} '.format(ncfile, hour))
            return None
        data = rootgrp.variables[parameter][nctimes.tolist().index(hour), ...]
        units = rootgrp.variables[parameter].getncattr('units')
        self.latitude = rootgrp.variables['latitude'][:]
        self.longitude = rootgrp.variables['longitude'][:]
        rootgrp.close()
        return data, units

    # region Monthly CAMS

    def read_cams_monthly(self):
        log.info('Looking for CAMS monthly data file')
        year = str(self.observation_datetime.year)
        month = '%02d' % self.observation_datetime.month
        # Find monthly cams data
        nc_file = glob.glob(os.path.join(self.cams_monthly_dir, year + month, '*.nc'), recursive=True)
        if nc_file:
            self.is_valid = True
            self.set_monthly_array(nc_file[0], self.observation_datetime)
        else:
            log.error('No CAMS monthly data found')

    def set_monthly_array(self, nc_file, observation_date):
        """ Retrieve for the given observation date
        The full array for each available atmospheric parameters
        The nearest time from obs_date in the netcdf is considered
        It is possible to interpolate in time, but it is not performed here
        Warning if delta hour between observation date and cams data exceed
        4 hours
        """
        rootgrp = Dataset(nc_file)
        # key_in : to check if parameters are available
        key_in = list(rootgrp.variables.keys())
        log.debug(key_in)
        umatch = []
        for rec in self.mandatory_attributes:
            if rec not in key_in:
                umatch.append(rec)
        if len(umatch) > 0:
            log.warning("Mismatch NETCDF elements with " + str(umatch))

        nctimes = rootgrp.variables['time'][:]

        if not isinstance(observation_date, datetime.datetime):
            acqdate = datetime.datetime.strptime(observation_date, '%Y-%m-%dT%H:%M:%S.%fZ')
        else:
            acqdate = observation_date

        hour1900 = (acqdate - datetime.datetime(1900, 1, 1)).total_seconds() / 60. / 60.

        u = np.abs(nctimes - hour1900)
        # np.argpartition : used to retrieve the two closest values for statistiscs
        val = [np.sort(u), np.argsort(u)]
        # The two first index :
        index1 = val[1][0]
        v1 = datetime.datetime(1900, 1, 1) + timedelta(
            hours=int(nctimes[index1]))  # VDE : failure for me if hours is type np.int32
        index2 = val[1][1]
        v2 = datetime.datetime(1900, 1, 1) + timedelta(hours=int(nctimes[index2]))

        log.info('Input observation date (hour): ' + str(acqdate))
        log.info('The two selected CAMS Dates:')
        log.info('    Date 1 :' + str(v1))
        log.info('    Date 2 :' + str(v2))

        log.info('Time elapsed between observation date and CAMS data date (hour) :')
        log.info('    %s / %s' % (str(val[0][0]), str(val[0][1])))

        self.observation_date_hour = hour1900
        self.cams_date_hour = nctimes[index1]
        # Retrieve data from CAMS dataset
        key_in.remove('time')
        key_in.remove('latitude')
        key_in.remove('longitude')
        self.latitude = rootgrp.variables['latitude'][:]
        self.longitude = rootgrp.variables['longitude'][:]
        # Should add index-1
        log.debug(key_in)
        for key in key_in:
            C = rootgrp.variables[key][index1, ...]

            sc_factor = 1
            sc_offset = 0
            units = rootgrp.variables[key].getncattr('units')
            C_rescale = np.multiply(sc_factor, np.array(C)) + sc_offset
            log.info('Parameter Set (unit) : ' + key + ' (' + units + ')')

            setattr(self, key, C_rescale)
            setattr(self, key + '_units', units)

        rootgrp.close()

    # endregion

    # region Hourly CAMS

    def read_cams_hourly(self, parameter):
        log.info('Looking for CAMS hourly %s data file' % parameter)
        h1900 = (self.observation_datetime - datetime.datetime(1900, 1, 1)).total_seconds() / 60. / 60.

        # Find h0
        h0 = ncfile_h0 = None
        for h0 in range(int(floor(h1900)), int(floor(h1900)) - 4, -1):
            ncfile_h0 = self._find_cams_hourly_nc(h1900, parameter)
            if ncfile_h0 is not None:
                break
        if h0 is None or ncfile_h0 is None:
            log.error('No CAMS lower data found for %s' % parameter)
            return None

        # Find h1
        h1 = ncfile_h1 = None
        for h1 in range(int(ceil(h1900)), int(ceil(h1900)) + 4):
            ncfile_h1 = self._find_cams_hourly_nc(h1, parameter)
            if h1 != h0 and ncfile_h1 is not None:
                break
        if h1 is None or ncfile_h1 is None:
            log.error('No CAMS upper data found for %s' % parameter)
            return None

        # get visibility for both dates
        data_h0 = self.read_date_values(h0, ncfile_h0, parameter)
        data_h1 = self.read_date_values(h1, ncfile_h1, parameter)
        if data_h0 is None or data_h1 is None:
            log.error('No CAMS hourly data found for %s' % parameter)
            return None

        # interpolate to exact time
        interpolated_data = data_h0[0] + (h1900 - h0) * (data_h1[0] - data_h0[0]) / (h1 - h0)
        self.set_hourly_array(parameter, interpolated_data, data_h0[1])

    def _find_cams_hourly_nc(self, hour1900, parameter):
        date = datetime.datetime(1900, 1, 1) + datetime.timedelta(hours=hour1900)
        hour = date.hour
        date = date.strftime('%Y%m%d')
        log.debug("Hour: %s" % hour)

        if hour == 0:
            subdir = f'{date}{hour}'
            hour = 24
        else:
            subdir = date
        if hour <= 12:
            subdir += '00'
            offset = hour
        else:
            subdir += '12'
            offset = hour - 12

        nc_name = 'z_cams_c_ecmf_{0}0000_prod_fc_sfc_{1:03d}_{2}.nc'.format(subdir, offset, parameter)
        nc_file = os.path.join(self.cams_hourly_directory, subdir, nc_name)
        if os.path.exists(nc_file):
            return nc_file
        return None

    def set_hourly_array(self, parameter, values, units):
        sc_factor = 1
        sc_offset = 0
        data_rescale = np.multiply(sc_factor, np.array(values)) + sc_offset
        log.info('Parameter Set (unit) : %s (%s)' % (parameter, units))
        setattr(self, parameter, data_rescale)
        setattr(self, parameter + '_units', units)

    # endregion

    # region Climatology CAMS

    def read_cams_climatology(self, doy, parameter):
        log.info('Looking for CAMS climatology file for %s' % parameter)
        file_name = os.path.join(self.cams_climatology_directory,
                                 f"CAMS_Climatology_2010-2019_{parameter}_DOY_{doy:03d}.tif")
        if os.path.exists(file_name):
            return self.set_climatology_array(parameter, file_name)
        log.error('No CAMS climatology data found for %s' % parameter)
        return None

    def set_climatology_array(self, parameter, file_name):
        src_ds = gdal.Open(file_name)
        data = src_ds.GetRasterBand(1)
        data_array = data.ReadAsArray()
        src_ds = None

        log.info('Parameter Set: %s' % parameter)
        setattr(self, parameter, data_array)

        # Read latitude and longitude
        for attribute in ('latitude', 'longitude'):
            if getattr(self, attribute) is None:
                l_file = os.path.join(self.cams_climatology_directory, f'{attribute}.tif')
                if os.path.exists(l_file):
                    ds = gdal.Open(l_file)
                    data = ds.GetRasterBand(1)
                    data_array = data.ReadAsArray()[0]
                    ds = None
                    setattr(self, attribute, data_array)
                    log.info('Parameter Set: %s' % attribute)

    # endregion

    # region Daily CAMS

    def read_cams_daily(self, parameter):
        log.info('Looking for CAMS daily %s data file' % parameter)
        h1900 = (self.observation_datetime - datetime.datetime(1900, 1, 1)).total_seconds() / 60. / 60.
        nc_file = self._find_cams_daily_nc(h1900, parameter)
        if nc_file:
            self.is_valid = True
            self.set_daily_array(nc_file, self.observation_datetime)
        else:
            log.error('No CAMS daily data found')

    def _find_cams_daily_nc(self, hour1900, parameter):
        date = datetime.datetime(1900, 1, 1) + datetime.timedelta(hours=hour1900)
        date_str = date.strftime('%Y%m%d')
        log.debug("Hour: %s" % date_str)
        nc_name = f'CAMS_archive_aod550_tcwv_msl_gtco3_analysis_0H_6H_12H_18H_{date.year:4}-{date.month:02}-{date.day:02}.nc'
        nc_file = os.path.join(self.cams_daily_directory, date_str, nc_name)
        if os.path.exists(nc_file):
            return nc_file
        return None

    def set_daily_array(self, nc_file, observation_date):
        """ Retrieve for the given observation date
        The full array for each available atmospheric parameters
        The nearest time from obs_date in the netcdf is considered
        It is possible to interpolate in time, but it is not performed here
        Warning if delta hour between observation date and cams data exceed
        4 hours
        """
        rootgrp = Dataset(nc_file)
        nctimes = rootgrp.variables['time'][:]

        key_in = list(rootgrp.variables.keys())
        log.debug(key_in)
        umatch = []
        for rec in self.mandatory_attributes:
            if rec not in key_in:
                umatch.append(rec)
        if len(umatch) > 0:
            log.warning("Mismatch NETCDF elements with " + str(umatch))

        # Try to find the two closest values
        hour1900 = (self.observation_datetime - datetime.datetime(1900, 1, 1)).total_seconds() / 60. / 60.

        u = np.abs(nctimes - hour1900)
        # np.argpartition : used to retrieve the two closest values for statistiscs
        val = [np.sort(u), np.argsort(u)]
        # The two first index :
        index1 = val[1][0]
        v1 = datetime.datetime(1900, 1, 1) + timedelta(
            hours=int(nctimes[index1]))  # VDE : failure for me if hours is type np.int32
        index2 = val[1][1]
        v2 = datetime.datetime(1900, 1, 1) + timedelta(hours=int(nctimes[index2]))

        log.info('Input observation date (hour): ' + str(self.observation_datetime))
        log.info('The two selected CAMS Dates:')
        log.info('    Date 1 :' + str(v1))
        log.info('    Date 2 :' + str(v2))

        log.info('Time elapsed between observation date and CAMS data date (hour) :')
        log.info('    %s / %s' % (str(val[0][0]), str(val[0][1])))

        self.observation_date_hour = hour1900
        self.cams_date_hour = nctimes[index1]
        # Retrieve data from CAMS dataset
        key_in.remove('time')
        key_in.remove('latitude')
        key_in.remove('longitude')
        self.latitude = rootgrp.variables['latitude'][:]
        self.longitude = rootgrp.variables['longitude'][:]
        # Should add index-1
        log.debug(key_in)
        for key in key_in:
            var_1 = rootgrp.variables[key][index1, ...]
            var_2 = rootgrp.variables[key][index2, ...]

            interpolated_data = var_1 + (hour1900 - nctimes[index1]) * (var_2 - var_1) / (nctimes[index2] - nctimes[index1])

            sc_factor = 1
            sc_offset = 0
            units = rootgrp.variables[key].getncattr('units')
            var_rescale = np.multiply(sc_factor, np.array(interpolated_data)) + sc_offset
            log.info('Parameter Set (unit) : ' + key + ' (' + units + ')')

            setattr(self, key, var_rescale)
            setattr(self, key + '_units', units)

        rootgrp.close()

    # endregion


if __name__ == '__main__':
    # CAMS location
    logging.basicConfig(level=logging.DEBUG)

    config = S2L_Config()
    config.initialize('../conf/config.ini')
    # obs_datetime = datetime.datetime.strptime('2017-04-20T10:34:54.040000Z', '%Y-%m-%dT%H:%M:%S.%fZ')
    # ecmwf_data = ECMWF_Product(config.get('cams_dir'), cams_hourly_directory=config.get('cams_hourly_dir'),
    #                               cams_climatology_directory=config.get('cams_climatology_dir'),
    #                               observation_datetime=obs_datetime)

    # obs_datetime = datetime.datetime.strptime('2020-04-08T10:34:54.040000Z', '%Y-%m-%dT%H:%M:%S.%fZ')
    # ecmwf_data = ECMWF_Product(config.get('cams_dir'), cams_hourly_directory=config.get('cams_hourly_dir'),
    #                           cams_climatology_directory=config.get('cams_climatology_dir'),
    #                           observation_datetime=obs_datetime)
    # aod550 = ecmwf_data.aod550
    # gtco3 = ecmwf_data.gtco3
    # # aod550_multi = ecmwf_data.aod550_multi
    # # gtco3_multi = ecmwf_data.gtco3_multi
    # # print(aod550 - aod550_multi)
    # # print(gtco3 - aod550_multi)

    obs_datetime = datetime.datetime.strptime('2021-01-23T10:34:54.040000Z', '%Y-%m-%dT%H:%M:%S.%fZ')
    _cams_config = {
        "default": config.get('cams_dir'),
        "hourly": config.get('cams_hourly_dir'),
        "daily": config.get('cams_daily_dir'),
        "climatology": config.get('cams_climatology_dir')
    }
    ecmwf_data = ECMWF_Product(cams_config=_cams_config, observation_datetime=obs_datetime)
