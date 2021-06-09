"""
Convert SMAC coefficients given by O.Hagolle (1 array, each colomn == 1 band)
to the SMAC format (1 file per band, and specific format)
"""
import sys

from lxml import objectify


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


def writeline(array, n, o, line=None):
    """
    write the n first values from array,
    in the SMAC format,
    and delete in array values that have been used

    array = array of values (coeffs)
    n = number of values to write
    o = file stream
    line = line number (if special format is needed)
    """

    # format
    if line == 11:
        stringArray = ('%.6e %.6f' % (array[0], array[1])).split()
        # o.write(' '+' '.join(stringArray) + '\n')
    elif line == 13:
        stringArray = ('%.14e %.14e %.14e' % (array[0], array[1], array[2])).split()
        # o.write('          '+' '.join(stringArray) + '\n')
    elif line == 14:
        stringArray = ('%.14e %.14e' % (array[0], array[1])).split()
        # o.write('          '+' '.join(stringArray) + '\n')
    else:
        stringArray = ['%.6f' % val for val in array[0:n]]

    # write
    o.write(' ' + ' '.join(stringArray) + '\n')

    # remove already written
    for i in range(n):
        array.pop(0)


if __name__ == '__main__':

    # read source file
    # lines = open("landsat8_coeff.txt").readlines()
    # line = lines[0]

    xmlFile = sys.argv[1]
    with open(xmlFile) as f:
        xmltext = f.read()
    root = objectify.fromstring(xmltext)
    print(root)
    line = root.Data_Block.SMAC_Coefficients.text

    bands = []
    if xmlFile.startswith('L8'):
        bands = ['440', '490', '560', '660', '860', '1630', '2250', '1370']  # 1 to 9 bands without PAN (band 8)
        name = 'LANDSAT8'
    elif xmlFile.startswith('L9'):
        bands = ['440', '490', '560', '660', '860', '1630', '2250', '1370']  # 1 to 9 bands without PAN (band 8)
        name = 'LANDSAT9'
    elif xmlFile.startswith('S2'):
        bands = ['B' + str(b) for b in range(1, 13)]
        bands.insert(8, 'B8a')
        name = 'S2A_CONT'
        if xmlFile.startswith('S2B'):
            name = 'S2B_CONT'
    print(name)
    print(bands)

    a = [float(x) for x in line.split()]  # all coeff of all bands in 1 row
    # nCoeff = 49

    # for each column (each band)
    for i, band in enumerate(bands):
        print('band:', band)
        # coeffs = a[nCoeff*i:nCoeff*(i+1)]
        coeffs = a[i::len(bands)]
        print(len(coeffs))
        smac_filename = 'Coef_{}_{}.dat'.format(name, band)
        with open(smac_filename, 'w') as o:
            # write in the SMAC specific format
            writeline(coeffs, 2, o)  # line1
            writeline(coeffs, 2, o)
            writeline(coeffs, 3, o)
            writeline(coeffs, 3, o)
            writeline(coeffs, 3, o)  # line5
            writeline(coeffs, 3, o)
            writeline(coeffs, 3, o)
            writeline(coeffs, 4, o)
            writeline(coeffs, 4, o)
            writeline(coeffs, 2, o)  # line10
            writeline(coeffs, 2, o, line=11)
            writeline(coeffs, 2, o)
            writeline(coeffs, 3, o, line=13)
            writeline(coeffs, 2, o, line=14)
            writeline(coeffs, 2, o)  # line15
            writeline(coeffs, 2, o)
            writeline(coeffs, 3, o)
            writeline(coeffs, 2, o)
            writeline(coeffs, 2, o)  # line19
            if len(coeffs) != 0:
                print('ERROR: some values have not been used')

        test = coeff(smac_filename)
        print(test.__dict__)
        print()
        print('Written:', smac_filename)
        print()
