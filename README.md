# Sen2Like
Generation of Analysis Ready Dataset - Sentinel-2 Mission category.
   
## About

The __Sen2Like__, [1] demonstration processor has been developed by ESA in the framework of the EU Copernicus programme (https://www.copernicus.eu/).

The main goal of __Sen2Like__ is to generate Sentinel-2 like harmonised/fused surface reflectances with higher periodicity by integrating additional compatible optical mission sensors.

It is a contribution to on going worldwide initiatives (*NASA-HLS, Force, CESBIO [2],[3]) undertook to facilitate higher level processing starting from harmonized data. 

The __Sen2Like__ framework is a scientific and open source software. In its current implementation version (*November 2020*), it combines Landsat-8 and Sentinel-2 data products. 
Level 1 and Level 2 input Landsat 8 (LS8) products are processed to be harmonized with Sentinel-2 data (S2).
The two following ARD product types are generated: 
* Harmonized Surface Reflectance Products (Level 2H) - at 30m of resolution,
* Fused Surface Reflectance Products (Level 2F) - at 10-20m of resolution. 

This __harmonisation__ process increases the theoretical number of acquisitions of this virtual constellation (95 
 products/year) by 30 % with respect to Sentinel-2 (S2A & S2B) only acquisitions (73 products/year) and promotes 
 the pixel-based analysis with the extraction of fit-for-purpose dense __time series__, essential 
 for bio-geophysical variables monitoring for instance.

Regardless Missions, Product Type, __Gridded__ data are delivered, the S2 tiling system is based on
the Military Grid Reference System (MGRS).

The __processing workflow__ is based on following algorithms:
*	Geometric Corrections including registration to common reference & the stitching [4],
*	Atmospheric Corrections by using SMAC [5] relying on auxiliary meteorological data,
*	Application of Spectral Band Adjustment Factor (SBAF) [2],
*	Transformation to Nadir BRDF-normalized Reflectance (NBAR) [6],[7],
*	Production of LS8 High Resolution 10 m pixel spacing data (Fusion) [8].
 
Beside these features, the user specifies the geographic footprint of multi temporal data stack.
It is therefore possible, to cover large geographic extent with a __seamless image mosaic__.  

It is worth noting that the overall accuracy of your final ARD product strongly depends on the accuracy of sen2like auxiliary data. Two categories of auxiliary data are important: the raster reference for geometric corrections and the meteorological data for atmospheric corrections. Regarding atmospheric corrections, one possibility is to use data from the Copernicus Atmosphere Monitoring Service [9]. The Sen2Like team prepared a dedicated CAMS monthly dataset for the Year 2020, available from [here](http://185.178.85.51/CAMS/). Please refer to this short [description](http://185.178.85.51/CAMS/Readme_CAMS2020.txt) for additional information.

For further details on the format specification of the harmonized products or the functionalities of the Sen2Like software, please 
refer to the [Product Format Specification](https://github.com/senbox-org/sen2like/blob/master/sen2like/docs/source/S2-PDGS-MPC-L2HF-PFS-v1.0.pdf), and the [User Manual](https://github.com/senbox-org/sen2like/blob/master/sen2like/docs/source/S2-SEN2LIKE-UM-V1.4.pdf).

## Publications and Contacts
**Yearning to know more ? Check out**
*	poster [Sen2Like, a tool to generate Sentinel-2 Harmonised Surface Reflectance Products, First Results With Landsat-8, 3rd S2 Validation Team Meeting](https://www.researchgate.net/publication/332428332_Sen2like_a_Tool_to_Generate_Sentinel-2_Harmonised_Surface_Reflectance_Products_-_First_Results_With_Landsat-8)
*	A [Sen2Like Relaxing Video](https://youtu.be/KBSYYBShyos) prepared for [ESA EO PHI-WEEK 2020](https://www.youtube.com/playlist?list=PLvT7fd9OiI9XELZXcljYTftUtJ_NFWRrY)
*	A [Sen2Like Time Lapse including NDVI graphic](https://youtu.be/yEObvI1KQBg) prepared for QWG#12

And the following research papers :
 + [1] S. Saunier, J. Louis, V. Debaecker et al., "Sen2like, A Tool To Generate Sentinel-2 Harmonised Surface Reflectance Products - First Results with Landsat-8," IGARSS 2019 - 2019 IEEE International Geoscience and Remote Sensing Symposium, Yokohama, Japan, 2019, pp. 5650-5653, doi: 10.1109/IGARSS.2019.8899213.
 + [2] Claverie, Martin, Junchang Ju, Jeffrey G. Masek, Jennifer L. Dungan, Eric F. Vermote, Jean-Claude Roger, Sergii V. Skakun, et Christopher Justice. "The Harmonized Landsat and Sentinel-2 Surface Reflectance Data Set". Remote Sensing of Environment 219 (15 décembre 2018): 145‑61. (https://doi.org/10.1016/j.rse.2018.09.002).
 + [3] Frantz, David. "FORCE—Landsat + Sentinel-2 Analysis Ready Data and Beyond". Remote Sensing 11, nᵒ 9 (janvier 2019): 1124. (https://doi.org/10.3390/rs11091124).
 + [4] S. Kocaman, S., Debaecker, V., Bas, S., Saunier, S., Garcia, K., and Just, D. "Investigation on the Global Image Datasets for the absolute geometric quality assessment of MSG SEVIRI Imagery", in Int. Arch. Photogramm. Remote Sens. Spatial Inf. Sci., XLIII-B3-2020, 1339–1346, 2020 (https://doi.org/10.5194/isprs-archives-XLIII-B3-2020-1339-2020) 
 + [5] Rahman, H., & Dedieu, G. "SMAC: a simplified method for the atmospheric correction of satellite measurements in the solar spectrum." REMOTE SENSING, 15(1), 123-143, 1994.
 + [6] Claverie, Martin, Eric Vermote, Belen Franch, Tao He, Olivier Hagolle, Mohamed Kadiri, et Jeff Masek. "Evaluation of Medium Spatial Resolution BRDF-Adjustment Techniques Using Multi-Angular SPOT4 (Take5) Acquisitions". Remote Sensing 7, nᵒ 9 (18 septembre 2015): 12057‑75. (https://doi.org/10.3390/rs70912057) 
 + [7] Roy, David P., Jian Li, Hankui K. Zhang, Lin Yan, Haiyan Huang, et Zhongbin Li. Examination of Sentinel-2A Multi-Spectral Instrument (MSI) Reflectance Anisotropy and the Suitability of a General Method to Normalize MSI Reflectance to Nadir BRDF Adjusted Reflectance". Remote Sensing of Environment 199 (septembre 2017): 25‑38. (https://doi.org/10.1016/j.rse.2017.06.019)
 + [8] Sen2Like User Manual
 + [9] [Copernicus Atmosphere Monitoring Service](https://atmosphere.copernicus.eu/)
 
 

**Learn how to use Sen2Like**, have a look at the [User Manual](https://github.com/senbox-org/sen2like/blob/master/sen2like/docs/source/S2-SEN2LIKE-UM-V1.5_delivered.pdf).

**Get help**, contact us at sen2like@telespazio.com.

**Follow** the Sen2Like project on [ResearchGate](https://www.researchgate.net/project/Sen2Like).

**You are using Sen2Like? Spread the word**, and use the [#sen2like]() hashtag in your tweets!
