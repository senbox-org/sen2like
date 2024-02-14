#! /usr/bin/env python
# -*- coding: iso-8859-1 -*-
# =============================================================================================
# library for atmospheric correction using SMAC method (Rahman and Dedieu, 1994)
# Contains :
#      smac_inv : inverse smac model for atmospheric correction
#                          TOA==>Surface
#      smac dir : direct smac model
#                          Surface==>TOA
#      coefs : reads smac coefficients
#      PdeZ : #      PdeZ : Atmospheric pressure (in hpa) as a function of altitude (in meters)

# Written by O.Hagolle CNES, from the original SMAC C routine
# =============================================================================================
from math import acos, cos, exp, pi, sqrt

import numpy as np

# =============================================================================================

def PdeZ(Z):
    """
    PdeZ : Atmospheric pressure (in hpa) as a function of altitude (in meters)

    """
    p = 1013.25 * pow(1 - 0.0065 * Z / 288.15, 5.31)
    return p


# =============================================================================================

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


# ======================================================================
def smac_inv(r_toa, tetas, phis, tetav, phiv, pressure, taup550, uo3, uh2o, coef):
    """
    r_surf=smac_inv( r_toa, tetas, phis, tetav, phiv,pressure,taup550, uo3, uh2o, coef)
    Corrections atmosphériques
    """
    ah2o = coef.ah2o
    nh2o = coef.nh2o
    ao3 = coef.ao3
    no3 = coef.no3
    ao2 = coef.ao2
    no2 = coef.no2
    po2 = coef.po2
    aco2 = coef.aco2
    nco2 = coef.nco2
    pco2 = coef.pco2
    ach4 = coef.ach4
    nch4 = coef.nch4
    pch4 = coef.pch4
    ano2 = coef.ano2
    nno2 = coef.nno2
    pno2 = coef.pno2
    aco = coef.aco
    nco = coef.nco
    pco = coef.pco
    a0s = coef.a0s
    a1s = coef.a1s
    a2s = coef.a2s
    a3s = coef.a3s
    a0T = coef.a0T
    a1T = coef.a1T
    a2T = coef.a2T
    a3T = coef.a3T
    taur = coef.taur
    a0taup = coef.a0taup
    a1taup = coef.a1taup
    wo = coef.wo
    gc = coef.gc
    a0P = coef.a0P
    a1P = coef.a1P
    a2P = coef.a2P
    a3P = coef.a3P
    a4P = coef.a4P
    Rest1 = coef.Rest1
    Rest2 = coef.Rest2
    Rest3 = coef.Rest3
    Rest4 = coef.Rest4
    Resr1 = coef.Resr1
    Resr2 = coef.Resr2
    Resr3 = coef.Resr3
    Resa1 = coef.Resa1
    Resa2 = coef.Resa2
    Resa3 = coef.Resa3
    Resa4 = coef.Resa4

    cdr = pi / 180
    crd = 180 / pi

    # /*------:  calcul de la reflectance de surface  smac               :--------*/

    us = cos(tetas * cdr)
    uv = cos(tetav * cdr)
    Peq = pressure / 1013.25

    # /*------:  1) air mass */
    m = 1 / us + 1 / uv

    # /*------:  2) aerosol optical depth in the spectral band, taup     :--------*/
    taup = a0taup + a1taup * taup550

    # /*------:  3) gaseous transmissions (downward and upward paths)    :--------*/
    to3 = 1.
    th2o = 1.
    to2 = 1.
    tco2 = 1.
    tch4 = 1.

    uo2 = (Peq ** po2)
    uco2 = (Peq ** pco2)
    uch4 = (Peq ** pch4)
    uno2 = (Peq ** pno2)
    uco = (Peq ** pco)

    # /*------:  4) if uh2o <= 0 and uo3 <=0 no gaseous absorption is computed  :--------*/
    to3 = exp(ao3 * ((uo3 * m) ** no3))
    th2o = exp(ah2o * ((uh2o * m) ** nh2o))
    to2 = exp(ao2 * ((uo2 * m) ** no2))
    tco2 = exp(aco2 * ((uco2 * m) ** nco2))
    tch4 = exp(ach4 * ((uch4 * m) ** nch4))
    tno2 = exp(ano2 * ((uno2 * m) ** nno2))
    tco = exp(aco * ((uco * m) ** nco))
    tg = th2o * to3 * to2 * tco2 * tch4 * tco * tno2

    # /*------:  5) Total scattering transmission                      :--------*/
    ttetas = a0T + a1T * taup550 / us + (a2T * Peq + a3T) / (1. + us)  # /* downward */
    ttetav = a0T + a1T * taup550 / uv + (a2T * Peq + a3T) / (1. + uv)  # /* upward   */

    # /*------:  6) spherical albedo of the atmosphere                 :--------*/
    s = a0s * Peq + a3s + a1s * taup550 + a2s * (taup550 ** 2)

    # /*------:  7) scattering angle cosine                            :--------*/
    cksi = - ((us * uv) + (sqrt(1. - us * us) * sqrt(1. - uv * uv) * cos((phis - phiv) * cdr)))
    if cksi < -1:
        cksi = -1.0

    # /*------:  8) scattering angle in degree 			 :--------*/
    ksiD = crd * acos(cksi)

    # /*------:  9) rayleigh atmospheric reflectance 			 :--------*/
    ray_phase = 0.7190443 * (1. + (cksi * cksi)) + 0.0412742
    ray_ref = (taur * ray_phase) / (4 * us * uv)
    ray_ref = ray_ref * pressure / 1013.25
    taurz = taur * Peq

    # /*------:  10) Residu Rayleigh 					 :--------*/
    Res_ray = Resr1 + Resr2 * taur * ray_phase / (us * uv) + Resr3 * ((taur * ray_phase / (us * uv)) ** 2)

    # /*------:  11) aerosol atmospheric reflectance			 :--------*/
    aer_phase = a0P + a1P * ksiD + a2P * ksiD * ksiD + a3P * (ksiD ** 3) + a4P * (ksiD ** 4)

    ak2 = (1. - wo) * (3. - wo * 3 * gc)
    ak = sqrt(ak2)
    e = -3 * us * us * wo / (4 * (1. - ak2 * us * us))
    f = -(1. - wo) * 3 * gc * us * us * wo / (4 * (1. - ak2 * us * us))
    dp = e / (3 * us) + us * f
    d = e + f
    b = 2 * ak / (3. - wo * 3 * gc)
    delta = np.exp(ak * taup) * (1. + b) * (1. + b) - np.exp(-ak * taup) * (1. - b) * (1. - b)
    ww = wo / 4.
    ss = us / (1. - ak2 * us * us)
    q1 = 2. + 3 * us + (1. - wo) * 3 * gc * us * (1. + 2 * us)
    q2 = 2. - 3 * us - (1. - wo) * 3 * gc * us * (1. - 2 * us)
    q3 = q2 * np.exp(-taup / us)
    c1 = ((ww * ss) / delta) * (q1 * np.exp(ak * taup) * (1. + b) + q3 * (1. - b))
    c2 = -((ww * ss) / delta) * (q1 * np.exp(-ak * taup) * (1. - b) + q3 * (1. + b))
    cp1 = c1 * ak / (3. - wo * 3 * gc)
    cp2 = -c2 * ak / (3. - wo * 3 * gc)
    z = d - wo * 3 * gc * uv * dp + wo * aer_phase / 4.
    x = c1 - wo * 3 * gc * uv * cp1
    y = c2 - wo * 3 * gc * uv * cp2
    aa1 = uv / (1. + ak * uv)
    aa2 = uv / (1. - ak * uv)
    aa3 = us * uv / (us + uv)

    aer_ref = x * aa1 * (1. - np.exp(-taup / aa1))
    aer_ref = aer_ref + y * aa2 * (1. - np.exp(-taup / aa2))
    aer_ref = aer_ref + z * aa3 * (1. - np.exp(-taup / aa3))
    aer_ref = aer_ref / (us * uv)

    # /*------:  12) Residu Aerosol  					:--------*/
    Res_aer = (Resa1 + Resa2 * (taup * m * cksi) + Resa3 * ((taup * m * cksi) ** 2)) + Resa4 * ((taup * m * cksi) ** 3)

    # /*------:  13)  Terme de couplage molecule / aerosol		:--------*/
    tautot = taup + taurz
    Res_6s = (Rest1 + Rest2 * (tautot * m * cksi) + Rest3 * ((tautot * m * cksi) ** 2)) + Rest4 * (
            (tautot * m * cksi) ** 3)

    # /*------:  14) total atmospheric reflectance  			:--------*/
    atm_ref = ray_ref - Res_ray + aer_ref - Res_aer + Res_6s

    # /*------:  15) Surface reflectance  				:--------*/

    r_surf = r_toa - (atm_ref * tg)
    r_surf = r_surf / ((tg * ttetas * ttetav) + (r_surf * s))

    return r_surf


# =======================================================================================================
def smac_dir(r_surf, tetas, phis, tetav, phiv, pressure, taup550, uo3, uh2o, coef):
    """
    r_toa=smac_dir ( r_surf, tetas, phis, tetav, phiv,pressure,taup550, uo3, uh2o, coef)
    Application des effets atmosphériques
    """

    ah2o = coef.ah2o
    nh2o = coef.nh2o
    ao3 = coef.ao3
    no3 = coef.no3
    ao2 = coef.ao2
    no2 = coef.no2
    po2 = coef.po2
    aco2 = coef.aco2
    nco2 = coef.nco2
    pco2 = coef.pco2
    ach4 = coef.ach4
    nch4 = coef.nch4
    pch4 = coef.pch4
    ano2 = coef.ano2
    nno2 = coef.nno2
    pno2 = coef.pno2
    aco = coef.aco
    nco = coef.nco
    pco = coef.pco
    a0s = coef.a0s
    a1s = coef.a1s
    a2s = coef.a2s
    a3s = coef.a3s
    a0T = coef.a0T
    a1T = coef.a1T
    a2T = coef.a2T
    a3T = coef.a3T
    taur = coef.taur
    a0taup = coef.a0taup
    a1taup = coef.a1taup
    wo = coef.wo
    gc = coef.gc
    a0P = coef.a0P
    a1P = coef.a1P
    a2P = coef.a2P
    a3P = coef.a3P
    a4P = coef.a4P
    Rest1 = coef.Rest1
    Rest2 = coef.Rest2
    Rest3 = coef.Rest3
    Rest4 = coef.Rest4
    Resr1 = coef.Resr1
    Resr2 = coef.Resr2
    Resr3 = coef.Resr3
    Resa1 = coef.Resa1
    Resa2 = coef.Resa2
    Resa3 = coef.Resa3
    Resa4 = coef.Resa4

    cdr = pi / 180
    crd = 180 / pi

    # /*------:  calcul de la reflectance de surface  smac               :--------*/

    us = cos(tetas * cdr)
    uv = cos(tetav * cdr)
    Peq = pressure / 1013.25

    # /*------:  1) air mass */
    m = 1 / us + 1 / uv

    # /*------:  2) aerosol optical depth in the spectral band, taup     :--------*/
    taup = a0taup + a1taup * taup550

    print(' aerosol optical depth @ 550, taup550 : ' + str(taup550))
    print(' aerosol optical depth in the spectral band, taup : ' + str(taup))

    # /*------:  3) gaseous transmissions (downward and upward paths)    :--------*/
    to3 = 1.
    th2o = 1.
    to2 = 1.
    tco2 = 1.
    tch4 = 1.

    uo2 = (Peq ** po2)
    uco2 = (Peq ** pco2)
    uch4 = (Peq ** pch4)
    uno2 = (Peq ** pno2)
    uco = (Peq ** pco)

    # /*------:  4) if uh2o <= 0 and uo3<= 0 no gaseous absorption is computed  :--------*/
    to3 = exp(ao3 * ((uo3 * m) ** no3))
    th2o = exp(ah2o * ((uh2o * m) ** nh2o))
    to2 = exp(ao2 * ((uo2 * m) ** no2))
    tco2 = exp(aco2 * ((uco2 * m) ** nco2))
    tch4 = exp(ach4 * ((uch4 * m) ** nch4))
    tno2 = exp(ano2 * ((uno2 * m) ** nno2))
    tco = exp(aco * ((uco * m) ** nco))
    tg = th2o * to3 * to2 * tco2 * tch4 * tco * tno2

    print('4) Downward Gas. Transmission                : ' + str(tg))
    print('4) Upward Gas. Transmission                  : ' + str(uo2 * uco2))

    # /*------:  5) Total scattering transmission                      :--------*/
    ttetas = a0T + a1T * taup550 / us + (a2T * Peq + a3T) / (1. + us)  # /* downward */
    ttetav = a0T + a1T * taup550 / uv + (a2T * Peq + a3T) / (1. + uv)  # /* upward   */

    print(('5) Total Scattering Transmission - downward  : ' + str(ttetas)))
    print(('5) Total Scattering Transmission - upward    : ' + str(ttetav)))

    # /*------:  6) spherical albedo of the atmosphere                 :--------*/
    s = a0s * Peq + a3s + a1s * taup550 + a2s * (taup550 ** 2)

    print(('6) Spherical Albedo of the atmosphere        : ' + str(s)))

    # /*------:  7) scattering angle cosine                            :--------*/
    cksi = - ((us * uv) + (sqrt(1. - us * us) * sqrt(1. - uv * uv) * cos((phis - phiv - 360) * cdr)))
    if cksi < -1:
        cksi = -1.0

        # /*------:  8) scattering angle in degree            :--------*/
    ksiD = crd * acos(cksi)

    # /*------:  9) rayleigh atmospheric reflectance              :--------*/
    ray_phase = 0.7190443 * (1. + (cksi * cksi)) + 0.0412742
    ray_ref = (taur * ray_phase) / (4 * us * uv)
    ray_ref = ray_ref * pressure / 1013.25
    taurz = taur * Peq

    print((' Raleygh Atmospheric reflectance  : ' + str(taur)))

    # /*------:  10) Residu Rayleigh                      :--------*/
    Res_ray = Resr1 + Resr2 * taur * ray_phase / (us * uv) + Resr3 * ((taur * ray_phase / (us * uv)) ** 2)

    # /*------:  11) aerosol atmospheric reflectance          :--------*/
    aer_phase = a0P + a1P * ksiD + a2P * ksiD * ksiD + a3P * (ksiD ** 3) + a4P * (ksiD ** 4)

    ak2 = (1. - wo) * (3. - wo * 3 * gc)
    ak = sqrt(ak2)
    e = -3 * us * us * wo / (4 * (1. - ak2 * us * us))
    f = -(1. - wo) * 3 * gc * us * us * wo / (4 * (1. - ak2 * us * us))
    dp = e / (3 * us) + us * f
    d = e + f
    b = 2 * ak / (3. - wo * 3 * gc)
    delta = np.exp(ak * taup) * (1. + b) * (1. + b) - np.exp(-ak * taup) * (1. - b) * (1. - b)
    ww = wo / 4.
    ss = us / (1. - ak2 * us * us)
    q1 = 2. + 3 * us + (1. - wo) * 3 * gc * us * (1. + 2 * us)
    q2 = 2. - 3 * us - (1. - wo) * 3 * gc * us * (1. - 2 * us)
    q3 = q2 * np.exp(-taup / us)
    c1 = ((ww * ss) / delta) * (q1 * np.exp(ak * taup) * (1. + b) + q3 * (1. - b))
    c2 = -((ww * ss) / delta) * (q1 * np.exp(-ak * taup) * (1. - b) + q3 * (1. + b))
    cp1 = c1 * ak / (3. - wo * 3 * gc)
    cp2 = -c2 * ak / (3. - wo * 3 * gc)
    z = d - wo * 3 * gc * uv * dp + wo * aer_phase / 4.
    x = c1 - wo * 3 * gc * uv * cp1
    y = c2 - wo * 3 * gc * uv * cp2
    aa1 = uv / (1. + ak * uv)
    aa2 = uv / (1. - ak * uv)
    aa3 = us * uv / (us + uv)

    aer_ref = x * aa1 * (1. - np.exp(-taup / aa1))
    aer_ref = aer_ref + y * aa2 * (1. - np.exp(-taup / aa2))
    aer_ref = aer_ref + z * aa3 * (1. - np.exp(-taup / aa3))
    aer_ref = aer_ref / (us * uv)

    # /*------:  12) Residu Aerosol                      :--------*/
    Res_aer = (Resa1 + Resa2 * (taup * m * cksi) + Resa3 * ((taup * m * cksi) ** 2)) + Resa4 * ((taup * m * cksi) ** 3)

    # /*------:  13)  Terme de couplage molecule / aerosol       :--------*/
    tautot = taup + taurz
    Res_6s = (Rest1 + Rest2 * (tautot * m * cksi) + Rest3 * ((tautot * m * cksi) ** 2)) + Rest4 * (
            (tautot * m * cksi) ** 3)

    # /*------:  14) total atmospheric reflectance           :--------*/
    atm_ref = ray_ref - Res_ray + aer_ref - Res_aer + Res_6s

    # /*------:  15) TOA reflectance                 :--------*/

    r_toa = r_surf * tg * ttetas * ttetav / (1 - r_surf * s) + (atm_ref * tg)

    return r_toa


# =============================================================================
if __name__ == "__main__":
    # example
    theta_s = 45
    theta_v = 5
    phi_s = 200
    phi_v = 20
    r_toa = 0.2
    # Lecture des coefs_smac
    nom_smac = 'COEFS/coef_LANDSAT5_b1_CONT.dat'
    coefs = coeff(nom_smac)
    bd = 1
    r_surf = smac_inv(r_toa, theta_s, phi_s, theta_v, phi_v, 1013, 0.1, 0.3, 0.3, coefs)
    # r_surf=0.1
    r_toa2 = smac_dir(r_surf, theta_s, phi_s, theta_v, phi_v, 1013, 0.1, 0.3, 0.3, coefs)

    print((r_toa, r_surf, r_toa2))
# pressure 657,
# taup550 0.1,
# uo3 : 0.3
# uh2o : 0.3
