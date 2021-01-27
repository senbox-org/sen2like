import glob
import logging
import os
import re
from xml.dom import minidom

from core.metadata_extraction import from_date_to_doy
from core.readers.reader import BaseReader

log = logging.getLogger('SenLike')


class AlosMTL(BaseReader):
    # Object for metadata extraction
    # Assume that SIP MD File is beside directory including the product
    # "self.doy" not computed
    def __init__(self, product_path):
        super().__init__(product_path)
        self.isValid = True
        if not os.path.exists(self.product_path):
            log.error(' - Input product does not exist')
            return
        # Look for SIP MD file
        radical = os.path.basename(self.product_path)
        self.sip_md = os.path.join(self.product_path + '.MD.XML')
        log.info(' - SIP File name ' + self.sip_md)
        if not os.path.exists(self.sip_md):
            log.error(' No SIP Metadata File found')
            return

        self.read_sip_md_file()
        log.debug(self.sensor)
        if self.sensor == 'PRISM':
            product_collection = glob.glob(os.path.join(
                self.product_path, 'ALPSM*'))
            self.product_collection = product_collection
            dic = {' Nadir View': [f for f in glob.glob(os.path.join(self.product_path, 'ALPSM*')) if
                                   'ALPSMN' in f or 'ALPSMW' in f],
                   ' Forward View': glob.glob(os.path.join(self.product_path, 'ALPSMF*')),
                   ' Backward View': glob.glob(os.path.join(self.product_path, 'ALPSMB*'))}

        if self.sensor == 'AVNIR-2':
            list1 = glob.glob(os.path.join(
                self.product_path, self.sip_id + '*'))
            list2 = glob.glob(os.path.join(
                self.product_path))
            if list1 is None:
                product_collection = product_path
            product_collection = list1 + list2
            self.product_collection = product_collection
            if product_collection is None:
                log.error(' -- No Image found ')
            else:
                dic = {' Nadir View': product_collection[0]}

        if len(self.product_collection) == 0:
            log.error(' No product found in the SIP ZIP File ')
            return

        log.info(' - Extract metadata information in the Dimap file : the Nadir View')
        dlr_product_path = dic[' Nadir View']
        log.debug('dlr product path ' + str(dlr_product_path))
        rexp = 'AL01*.DIMA'
        dimap_file = glob.glob(os.path.join(dlr_product_path, rexp))[0]
        log.debug('dimap file :' + dimap_file)
        self.mtl_file_name = dimap_file
        self.read_dimap_file()

        try:
            log.info(" - Dimap  File name : " + os.path.basename(self.mtl_file_name))
            self.read_dimap_file()

        except IndexError:
            # if not md_list:
            log.error(' -- Warning - no MTL file found - Index Error')
            log.error(' -- Procedure aborted')
            self.mtl_file_name = ''

        # Set image file name - several GTIF in the product, just retrieve the full image
        regex = re.compile(r'AL01.*_[\d|A-Z][\d|A-Z][\d|A-Z][\d|A-Z].GTIF')
        gtiff_list = glob.glob(os.path.join(dlr_product_path, 'AL01*.GTIF'))
        log.debug(dlr_product_path)
        gtiff_file = [rec for rec in gtiff_list if regex.findall(rec)]
        self.image_list = gtiff_file

        # Doy
        rr = self.observation_date.split('-')  # 2007-12-08
        input_date = rr[2] + '-' + rr[1] + '-' + rr[0]

        # 02 - 02 - 2016
        self.doy = from_date_to_doy(input_date)

    def read_sip_md_file(self):

        log.debug(self.sip_md)

        xmldoc = minidom.parse(self.sip_md)
        parameter_name = "eop:Platform"
        eop_platform = xmldoc.getElementsByTagName(parameter_name)[0]
        short_name = eop_platform.getElementsByTagName('eop:shortName')[0]
        self.mission = short_name.childNodes[0].data

        parameter_name = "eop:Instrument"
        eop_instrument = xmldoc.getElementsByTagName(parameter_name)[0]
        short_name = eop_instrument.getElementsByTagName('eop:shortName')[0]
        self.sensor = short_name.childNodes[0].data

        parameter_name = "eop:Sensor"
        eop_sensor = xmldoc.getElementsByTagName(parameter_name)[0]
        op_mode = eop_sensor.getElementsByTagName('eop:operationalMode')[0]
        self.sensor_mode = op_mode.childNodes[0].data

        parameter_name = "eop:EarthObservationMetaData"
        eop_eomd = xmldoc.getElementsByTagName(parameter_name)[0]
        sip_id = eop_eomd.getElementsByTagName('eop:identifier')[0]
        self.sip_id = sip_id.childNodes[0].data

        if self.sensor == 'PRISM':
            #            < eop:vendorSpecific >
            #            < eop:SpecificInformation >
            #            < eop:localAttribute > availableViews < / eop:localAttribute >
            #            < eop:localValue > < / eop:localValue >
            #        < / eop:SpecificInformation >

            parameter_name = "eop:EarthObservationMetaData"
            eop_eomd = xmldoc.getElementsByTagName(parameter_name)[0]
            vn = eop_eomd.getElementsByTagName('eop:vendorSpecific')[0]
            sp_vn = vn.getElementsByTagName('eop:SpecificInformation')[0]
            view = sp_vn.getElementsByTagName('eop:localValue')[0]
            self.sip_avaibleview_test = True
            try:
                self.view = view.childNodes[0].data
            except IndexError:
                self.view = 'N'
                self.sip_avaibleview_test = False
        else:
            self.view = 'N'

    def read_dimap_file(self):
        """ BELOW DIMAP PROC_PARAMETER Block for AVNIR2 (June 29 2018 )
            In case of PRISM more PROC_PARAMETER GIVEN AS DECONVOLUTION_FLAG / DECONVOLUTION ACROSS_PSF...
            Swith required depending on the sensor (PSM / AVNIR)
          <Processing_Parameter>
      <PROC_PARAMETER_DESC>FORMAT</PROC_PARAMETER_DESC>
      <PROC_PARAMETER_VALUE>IMPROVE</PROC_PARAMETER_VALUE>
    </Processing_Parameter>
    <Processing_Parameter>
      <PROC_PARAMETER_DESC>GCP</PROC_PARAMETER_DESC>
      <PROC_PARAMETER_VALUE>_NULL_</PROC_PARAMETER_VALUE>
    </Processing_Parameter>
    <Processing_Parameter>
      <PROC_PARAMETER_DESC>MATCHING_FLAG</PROC_PARAMETER_DESC>
      <PROC_PARAMETER_VALUE>YES</PROC_PARAMETER_VALUE>
    </Processing_Parameter>
    <Processing_Parameter>
      <PROC_PARAMETER_DESC>REF</PROC_PARAMETER_DESC>
      <PROC_PARAMETER_VALUE>02.00</PROC_PARAMETER_VALUE>
    </Processing_Parameter>
    <Processing_Parameter>
      <PROC_PARAMETER_DESC>ORTHORECTIFICATION_FLAG</PROC_PARAMETER_DESC>
      <PROC_PARAMETER_VALUE>YES</PROC_PARAMETER_VALUE>
    </Processing_Parameter>
    <Processing_Parameter>
      <PROC_PARAMETER_DESC>DEM</PROC_PARAMETER_DESC>
      <PROC_PARAMETER_VALUE>02.00</PROC_PARAMETER_VALUE>
    </Processing_Parameter>
    <Processing_Parameter>
      <PROC_PARAMETER_DESC>PROJECTION</PROC_PARAMETER_DESC>
      <PROC_PARAMETER_VALUE>UXX</PROC_PARAMETER_VALUE>
    </Processing_Parameter>
    <Processing_Parameter>
      <PROC_PARAMETER_DESC>RESAMPLING</PROC_PARAMETER_DESC>
      <PROC_PARAMETER_VALUE>BILINEAR</PROC_PARAMETER_VALUE>
    </Processing_Parameter>
  </Data_Processing>


        :return:
        """

        # out_dir = tempfile.mkdtemp(prefix='alos_', dir=os.getcwd(), suffix='')
        # tmp_xml = os.path.join(out_dir,'dim_file.xml')
        tmp_xml = self.mtl_file_name
        log.debug(str(tmp_xml))
        # shutil.copy(self.mtl_file_name,tmp_xml)
        xmldoc = minidom.parse(tmp_xml)

        q_parameter = "Dataset_Sources"
        source_info = xmldoc.getElementsByTagName("Source_Information")[0]
        source_id = source_info.getElementsByTagName("SOURCE_ID")[0]
        self.scene_id = source_id.childNodes[0].data

        q_parameter = "PRODUCT_TYPE"
        self.data_type = xmldoc.getElementsByTagName(q_parameter)[0].childNodes[0].data

        q_parameter = "Scene_Source"
        scene_src = xmldoc.getElementsByTagName(q_parameter)[0]
        observation_date = (scene_src.getElementsByTagName("IMAGING_DATE")[0])
        self.observation_date = observation_date.childNodes[0].data

        parameter = 'SCENE_ORIENTATION'
        self.sc_or = xmldoc.getElementsByTagName(parameter)[0].childNodes[0].data

        parameter = 'PRODUCT_INFO'
        self.pdt_info = xmldoc.getElementsByTagName(parameter)[0].childNodes[0].data

        parameter = 'GEOMETRIC_PROCESSING'
        self.geo_processing = xmldoc.getElementsByTagName(parameter)[0].childNodes[0].data

        # Here swith depending on the mission is required.
        if self.sensor == 'PRISM':
            parameter = 'Processing_Parameter'  # <PROC_PARAMETER_DESC>GCP</PROC_PARAMETER_DESC>
            proc_parameters = xmldoc.getElementsByTagName(parameter)[5]
            self.gcp = (proc_parameters.getElementsByTagName("PROC_PARAMETER_VALUE"))[0].childNodes[0].data

            # parameter = 'MATCHING_FLAG' <PROC_PARAMETER_DESC>MATCHING_FLAG</PROC_PARAMETER_DESC>
            proc_parameters = xmldoc.getElementsByTagName(parameter)[6]
            self.matching_flag = (proc_parameters.getElementsByTagName("PROC_PARAMETER_VALUE"))[0].childNodes[0].data

            # parameter = 'ORTHO_FLAG' <PROC_PARAMETER_DESC>ORTHORECTIFICATION_FLAG</PROC_PARAMETER_DESC>
            proc_parameters = xmldoc.getElementsByTagName(parameter)[8]
            self.ortho_flag = (proc_parameters.getElementsByTagName("PROC_PARAMETER_VALUE"))[0].childNodes[0].data

        if self.sensor == 'AVNIR-2':
            parameter = 'Processing_Parameter'  # <PROC_PARAMETER_DESC>GCP</PROC_PARAMETER_DESC>
            proc_parameters = xmldoc.getElementsByTagName(parameter)[1]
            self.gcp = (proc_parameters.getElementsByTagName("PROC_PARAMETER_VALUE"))[0].childNodes[0].data

            # parameter = 'MATCHING_FLAG' <PROC_PARAMETER_DESC>MATCHING_FLAG</PROC_PARAMETER_DESC>
            proc_parameters = xmldoc.getElementsByTagName(parameter)[2]
            self.matching_flag = (proc_parameters.getElementsByTagName("PROC_PARAMETER_VALUE"))[0].childNodes[0].data

            # parameter = 'ORTHO_FLAG' <PROC_PARAMETER_DESC>ORTHORECTIFICATION_FLAG</PROC_PARAMETER_DESC>
            proc_parameters = xmldoc.getElementsByTagName(parameter)[4]
            self.ortho_flag = (proc_parameters.getElementsByTagName("PROC_PARAMETER_VALUE"))[0].childNodes[0].data

        parameter = 'INCIDENCE_ANGLE'
        self.viewing_angle = xmldoc.getElementsByTagName(parameter)[0].childNodes[0].data

        parameter = 'SUN_AZIMUTH'
        self.sun_azimuth = xmldoc.getElementsByTagName(parameter)[0].childNodes[0].data

        parameter = 'SUN_ELEVATION'
        self.sun_elevation = xmldoc.getElementsByTagName(parameter)[0].childNodes[0].data

        parameter = 'IMAGING_DATE'
        self.observation_date = xmldoc.getElementsByTagName(parameter)[0].childNodes[0].data

        parameter = 'TIME_CENTER_LINE'  # <TIME_CENTER_LINE>2007-12-08T10:31:41.858031</TIME_CENTER_LINE>
        self.scene_center_time = xmldoc.getElementsByTagName(parameter)[0].childNodes[0].data.split('T')[1]

        parameter = 'Quality_Assessment'
        # Quality Assessment : GCP_BASE FOR LIST OF IMAGES INVOLVED IN MATCHING
        qa_gcp_base = xmldoc.getElementsByTagName(parameter)[1]

        q_parameter = "QUALITY_PARAMETER_VALUE"
        source_tag_position = len(qa_gcp_base.getElementsByTagName(q_parameter)) - 1

        match_image_list = qa_gcp_base.getElementsByTagName(q_parameter)[source_tag_position].childNodes[0].data

        self.match_image_list = match_image_list.split()

        # Quality Assessment : GCP ACCURACY
        parameter = 'Quality_Assessment'
        self.gcp_rmse = 'NULL'
        self.gcp_distribution = 'NULL'
        self.gcp_density = 'NULL'
        self.gcp_cp_correlation = 'NULL'
        self.gcp_cp_rmse = 'NULL'

        try:
            qa_gcp = xmldoc.getElementsByTagName(parameter)[2]
            q_parameter = "QUALITY_PARAMETER_VALUE"
            l1 = len(qa_gcp.getElementsByTagName(q_parameter))
            log.debug(l1)
            # SWITCH depending on the 1T processing
            if l1 > 0:
                self.gcp_rmse = qa_gcp.getElementsByTagName(q_parameter)[0].childNodes[0].data

            if l1 >= 3:
                self.gcp_distribution = qa_gcp.getElementsByTagName(q_parameter)[2].childNodes[0].data
                self.gcp_density = qa_gcp.getElementsByTagName(q_parameter)[3].childNodes[0].data

            if l1 >= 4:
                self.gcp_cp_correlation = qa_gcp.getElementsByTagName(q_parameter)[4].childNodes[0].data
                self.gcp_cp_rmse = qa_gcp.getElementsByTagName(q_parameter)[1].childNodes[0].data

        except IndexError:
            log.error(' No GCP QA available')

        q_parameter = "PRODUCT_QUALITY"
        self.pdt_quality = xmldoc.getElementsByTagName(q_parameter)[0].childNodes[0].data

        scene_boundary_lat = []
        scene_boundary_lon = []

        q_parameter = "Vertex"
        for i in range(0, 4, 1):
            scene_coordinate = xmldoc.getElementsByTagName(q_parameter)[i]
            frame_lon = (scene_coordinate.getElementsByTagName('FRAME_LON'))[0].childNodes[0].data
            frame_lat = (scene_coordinate.getElementsByTagName('FRAME_LAT'))[0].childNodes[0].data
            scene_boundary_lon.append(frame_lon)
            scene_boundary_lat.append(frame_lat)

        self.scene_boundary_lat = scene_boundary_lat
        self.scene_boundary_lon = scene_boundary_lon
