import sys

import pytest

"""
Convert SMAC coefficients given by O.Hagolle (1 array, each colomn == 1 band)
to the SMAC format (1 file per band, and specific format)
"""


class coeff:
    def __init__(self, smac_filename):
        with open(smac_filename) as f:
            lines = f.readlines()
        # H20
        temp = lines[0].strip().split()
        self.ah2o = float(temp[0])
        self.nh2o = float(temp[1])
        # O3
        temp = lines[1].strip().split()
        self.ao3 = float(temp[0])
        self.no3 = float(temp[1])
        # O2
        temp = lines[2].strip().split()
        self.ao2 = float(temp[0])
        self.no2 = float(temp[1])
        self.po2 = float(temp[2])
        # CO2
        temp = lines[3].strip().split()
        self.aco2 = float(temp[0])
        self.nco2 = float(temp[1])
        self.pco2 = float(temp[2])
        # NH4
        temp = lines[4].strip().split()
        self.ach4 = float(temp[0])
        self.nch4 = float(temp[1])
        self.pch4 = float(temp[2])
        # NO2
        temp = lines[5].strip().split()
        self.ano2 = float(temp[0])
        self.nno2 = float(temp[1])
        self.pno2 = float(temp[2])
        # NO2
        temp = lines[6].strip().split()
        self.aco = float(temp[0])
        self.nco = float(temp[1])
        self.pco = float(temp[2])

        # rayleigh and aerosol scattering
        temp = lines[7].strip().split()
        self.a0s = float(temp[0])
        self.a1s = float(temp[1])
        self.a2s = float(temp[2])
        self.a3s = float(temp[3])
        temp = lines[8].strip().split()
        self.a0T = float(temp[0])
        self.a1T = float(temp[1])
        self.a2T = float(temp[2])
        self.a3T = float(temp[3])
        temp = lines[9].strip().split()
        self.taur = float(temp[0])
        self.sr = float(temp[0])
        temp = lines[10].strip().split()
        self.a0taup = float(temp[0])
        self.a1taup = float(temp[1])
        temp = lines[11].strip().split()
        self.wo = float(temp[0])
        self.gc = float(temp[1])
        temp = lines[12].strip().split()
        self.a0P = float(temp[0])
        self.a1P = float(temp[1])
        self.a2P = float(temp[2])
        temp = lines[13].strip().split()
        self.a3P = float(temp[0])
        self.a4P = float(temp[1])
        temp = lines[14].strip().split()
        self.Rest1 = float(temp[0])
        self.Rest2 = float(temp[1])
        temp = lines[15].strip().split()
        self.Rest3 = float(temp[0])
        self.Rest4 = float(temp[1])
        temp = lines[16].strip().split()
        self.Resr1 = float(temp[0])
        self.Resr2 = float(temp[1])
        self.Resr3 = float(temp[2])
        temp = lines[17].strip().split()
        self.Resa1 = float(temp[0])
        self.Resa2 = float(temp[1])
        temp = lines[18].strip().split()
        self.Resa3 = float(temp[0])
        self.Resa4 = float(temp[1])


smac_filename_1 = sys.argv[1]
smac_filename_2 = sys.argv[2]

coeffs_1 = coeff(smac_filename_1)
coeffs_2 = coeff(smac_filename_2)

print(smac_filename_1)
print(smac_filename_2)
# for key in coeffs_1.__dict__.keys():
#    print key, coeffs_1.__dict__[key], coeffs_2.__dict__[key]

for key in list(coeffs_1.__dict__.keys()):
    try:
        assert coeffs_1.__dict__[key] == pytest.approx(coeffs_2.__dict__[key], 0.001), "ERROR: {}: {} {} {}".format(
            smac_filename_1, key, coeffs_1.__dict__[key], coeffs_2.__dict__[key])
    except Exception as e:
        print(e)
