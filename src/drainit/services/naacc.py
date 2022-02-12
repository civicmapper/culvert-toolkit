import json
from typing import List
from pathlib import Path
from collections import OrderedDict
from dataclasses import fields
from petl.transform.conversions import replaceall

import pint
import petl as etl
from marshmallow import ValidationError

from ..models import (
    NaaccCulvertSchema,
    DrainItPoint
)
from ..calculators.capacity import (
    Capacity,
    CapacitySchema,
    calc_culvert_capacity,
    capacity_numeric_fields
)
from ..utils import validate_petl_record_w_schema, convert_value_via_xwalk
from .naacc_config import (
    NAACC_HEADER_LOOKUP, 
    NAACC_INLET_SHAPE_CROSSWALK, 
    NAACC_INLET_TYPE_CROSSWALK
)

units = pint.UnitRegistry()


class NaaccEtl:

    def __init__(
        self,
        naacc_csv_file=None,
        naacc_petl_table=None,
        output_path=None,
        lookup_naac_inlet_shape=NAACC_INLET_SHAPE_CROSSWALK,
        lookup_naac_inlet_type=NAACC_INLET_TYPE_CROSSWALK,
        wkid=4326
        ) ->  None :

        self.naacc_csv_file=naacc_csv_file
        self.naacc_petl_table=naacc_petl_table
        self.output_path=output_path
        self.lookup_naac_inlet_shape=lookup_naac_inlet_shape
        self.lookup_naac_inlet_type=lookup_naac_inlet_type
        self.wkid=wkid

        self.naacc_culvert_schema = NaaccCulvertSchema()
        self.capacity_schema = CapacitySchema()
        
        # self.table = self.read_naacc_csv_to_petl(
        #     self.naacc_csv_file,
        #     self.naacc_petl_table,
        #     self.output_path,
        #     self.lookup_naac_inlet_shape,
        #     self.lookup_naac_inlet_type
        # )
        self.table = None
        self.points = None


    # ------------------------------------------------------------------------------
    # NAACC ETL HELPER FUNCTIONS

    def _xwalk_naac_to_capacity(self, row):
        """crosswalk values from the NAACC fields to Capacity fields, type-casting
        numeric fields from strings along the way if necessary

        :param row: a single NAACC table row, where the table is from extract_naacc_table
        :type row: petl.Record
        :return: the row, w/ transformed or derived values
        :rtype: tuple    
        """
        
        r = OrderedDict({i[0]: i[1] for i in zip(row.flds, row)})
        
        for n_field, cap_field in NAACC_HEADER_LOOKUP.items():
            # for numeric fields, cast values to the specified python type based on the lookup above
            if cap_field in capacity_numeric_fields.keys():
                number_type = capacity_numeric_fields[cap_field]
                try:
                    r[cap_field] = number_type(r[n_field])
                except:
                    r[cap_field] = r[n_field]
            # otherwise just copy them over
            else:
                r[cap_field] = r[n_field]
            
        return tuple(r.values())

    def _culvert_geometry_tests(self, row):
        """determines whether a culvert can be included for capacity analysis based
        on a number of conditions. Logic from Cornell Culvert Model v2.1.

        Used within the context of a petl.rowmap function; writes to a boolean 
        `include` column and the validation_errors column

        TODO: leverage marshmallow-dataclass to make this part of the schema validation steps

        :param row: a single NAACC table row, where the table is from extract_naacc_table
        :type row: petl.Record
        :return: the row, w/ transformed or derived values
        :rtype: tuple

        """

        # convert PETL Record object to an ordered dictionary
        r = OrderedDict({i[0]: i[1] for i in zip(row.flds, row)})
        
        # if r['validation_errors'] is not None:
        #   return tuple(r.values())
        
        # try:
            
        # collect any reasons for exclusion here:
        validation_errors = {}

        # Check 1: wrong bridge type
        if all([
            r["crossing_type"] == "Bridge",
            r["in_shape"] not in ["Box/Bridge with Abutments", "Open Bottom Arch Bridge/Culvert"],
        ]):
            r["include"] = False
            validation_errors.setdefault('in_shape', []).append("Wrong bridge type ({0})".format(r["in_shape"]))

        # Check 2: bridge span too long
        if all([
            r["crossing_type"] == "Bridge", 
            r["in_a"] is not None and r["in_a"] >= 20
        ]):
            r["include"] = False
            validation_errors.setdefault('in_a', []).append("Bridge wider than 20 ft ({0} ft)".format(r["in_a"]))

        # Check 3: bad geometry
        culvert_geometry_fields = ["in_a", "in_b", "hw", "length"]
        # check if all values in culvert_geometry_fields are floats:
        culvert_geometry_fields_are_floats = [isinstance(r[f], float) for f in culvert_geometry_fields]
        # check if any values in culvert_geometry_fields are < 0:
        culvert_geometry_fields_are_lt0 = [
            v < 0 for v in 
            [r[f] for f in culvert_geometry_fields]
            if v is not None
        ]

        if not all(culvert_geometry_fields_are_floats):
            r["include"] = False
            for f, v in zip(culvert_geometry_fields, culvert_geometry_fields_are_floats):
                if v is None:
                    validation_errors.setdefault(f, []).append("cannot be None.")
                else:
                    validation_errors.setdefault(f, []).append("must be a number ({0})".format(v))
            # validation_errors.append("Required culvert geometry is missing: {0}".format([f for f,v in zip(culvert_geometry_fields, culvert_geometry_fields_are_floats) if not v]))
        elif any(culvert_geometry_fields_are_lt0):
            r["include"] = False
            for f,v in zip(culvert_geometry_fields, culvert_geometry_fields_are_lt0):
                validation_errors.setdefault(f, []).append("must be a greater than zero ({0})".format(v))
            # validation_errors.append("Required culvert geometry is negative: {0}".format([f for f,v in zip(culvert_geometry_fields, culvert_geometry_fields_are_gt0) if not v]))
        else:
            pass
        
        # if any validation errors found, add to the row's validation_errors field
        if validation_errors:
            if r['validation_errors'] is not None:
                r['validation_errors'].update(validation_errors)
            else:
                r['validation_errors'] = validation_errors

        # return as a tuple of values for the row
        return tuple(r.values())
        
        # except TypeError as e:
        #     # print('_naacc_exclude_tests', e, r['Survey_Id'])
        #     return tuple(r.values())

    def _derive_capacity_parameters(self, row):
        """transform or derive values for use in calculating culvert capacity

        NOTE: This function is designed to be used per-row within a petl.rowmap 
        function call
        
        TODO: replace the nested if/elif/else business logic here with a 
        multi-column lookup table that can be loaded from a human-readable, 
        human-editable external config file (e.g., a csv)

        :param row: a single NAACC table row, where the table is from extract_naacc_table
        :type row: petl.Record
        :return: the row, w/ transformed or derived values
        :rtype: tuple
        """

        # convert the incoming PETL.Record object to a dictionary
        row = OrderedDict({i[0]: i[1] for i in zip(row.flds, row)})
        
        # skip if validation errors are present
        if row['validation_errors'] is not None:
            return tuple(row.values())

        try:

            # -----------------------------------------------------
            # constants 

            # pi. Note that source script used a precision 5 float instead of 
            # Python's available math.pi constant, the latter likely being more precise
            pi = 3.14159 #math.pi

            # -----------------------------------------------------
            # variables to be calculated

            # culvert area ( square meters; default is for round pipe)
            culvert_area_sqm = ((row["in_a"] / 2) ** 2) * pi
            # culvert depth (meters, default is for round pipe)
            culvert_depth_m = row["in_a"]
            # coefficients based on shape and material from FHWA engineering pub HIF12026, appendix A
            coefficient_c = 0.04
            coefficient_y = 0.7
            # slope coefficient from FHWA engineering pub HIF12026, appendix A
            coefficient_slope = -0.5
            # slope as rise/run
            slope_rr = 0
            #  head over invert by adding dist from road to top of culvert to D 
            head_over_invert = 0

            comments = []
            exclusion_comments = []

            # -----------------------------------------------------
            # imperial to metric conversions

            row["length"] = (row["length"] * units.foot).to(units.meter).magnitude
            row["in_a"] = (row["in_a"] * units.foot).to(units.meter).magnitude
            row["hw"] = (row["hw"] * units.foot).to(units.meter).magnitude

            # if culvert is not round, need B (height), so convert from feet to meters
            if row["in_shape"] != "Round":
                row["in_b"] = (row["in_b"] * units.foot).to(units.meter).magnitude

            # -----------------------------------------------------
            # culvert slope as rise/run
            slope_rr = row["slope"] / 100 

            # -----------------------------------------------------
            # calculate culvert area and depth based on culvert shape

            # if culvert is round, depth is diameter
            if row["in_shape"] == "Round":
                culvert_area_sqm = ((row["in_a"] / 2) ** 2) * pi  # Area in m^2, thus diameter in m
                culvert_depth_m = row["in_a"]
            # if culvert is eliptical, depth is B 
            elif row["in_shape"] in ["Elliptical", "Pipe Arch"]:
                culvert_area_sqm = (row["in_a"] / 2) * (row["in_b"] / 2) * pi
                culvert_depth_m = row["in_b"]
            # if culvert is a box, depth is B
            elif row["in_shape"] == "Box":
                culvert_area_sqm = (row["in_a"]) * (row["in_b"])
                culvert_depth_m = row["in_b"]
            # if culvert is an arch, depth is B
            elif row["in_shape"] == "Arch":
                culvert_area_sqm = ((row["in_a"] / 2) * (row["in_b"] / 2) * pi) / 2
                culvert_depth_m = row["in_b"]
            # else:
            #     exclusion_comments.append('in_shape has unknown value: {0}'.format(row["in_shape"]))

            # Calculate head over invert by adding dist from road to top of culvert to D
            # H = row['HW'] / 3.2808 + D
            head_over_invert = row["hw"] + culvert_depth_m  # TODO: Check if OK that conversion is done above

            # assign ks (slope coefficient from FHWA engineering pub HIF12026, appendix A)
            if row["in_type"] == "Mitered to Slope":
                coefficient_slope = 0.7
            else:
                coefficient_slope = -0.5

            # assign c and y values (coefficients based on shape and material from FHWA engineering pub HIF12026, appendix A)
            # no c and y value provide for inlet_type == "other".  Will take on the filler values
            if row["in_shape"] == "Arch":
                if row["culv_mat"] in ["Concrete", "Stone"]:
                    if row["in_type"] in ["Headwall", "Projecting"]:
                        coefficient_c = 0.041
                        coefficient_y = 0.570
                    elif row["in_type"] == "Mitered to Slope":
                        coefficient_c = 0.040
                        coefficient_y = 0.48
                    elif row["in_type"] == "Wingwall":
                        coefficient_c = 0.040
                        coefficient_y = 0.620
                    elif row["in_type"] == "Wingwall and Headwall":
                        coefficient_c = 0.040
                        coefficient_y = 0.620
                    # else:
                    #     exclusion_comments.append(
                    #         'in_shape+culv_mat+in_type has unhandled combination of values: [{0}]'\
                    #         .format(" + ".join([row["in_shape"], row["culv_mat"], row["in_type"]]))
                    #     )
                        
                elif (row["culv_mat"] in ["Plastic", "Metal"]):  
                    # inlet_type to row['Culv_Mat'] for plastic - sharon
                    if row["in_type"] == "Mitered to Slope":
                        coefficient_c = 0.0540
                        coefficient_y = 0.5
                    elif row["in_type"] == "Projecting":
                        coefficient_c = 0.065
                        coefficient_y = 0.12
                    elif any(
                        [
                            row["in_type"] == "Headwall",
                            row["in_type"] == "Wingwall and Headwall",
                            row["in_type"] == "Wingwall",
                        ]
                    ):
                        coefficient_c = 0.0431
                        coefficient_y = 0.610
                    # else:
                    #     exclusion_comments.append(
                    #         'in_shape+culv_mat+in_type has unhandled combination of values: [{0}]'\
                    #         .format(" + ".join([row["in_shape"], row["culv_mat"], row["in_type"]]))
                    #     )                    
                elif row["culv_mat"] == "Combination":
                    coefficient_c = 0.045 # Changed March 2019 from c = 1.0   #filler values -sharon
                    coefficient_y = 0.5  # Y = 1.0    # filler values - sharon
                    comments.append("Default c & Y values.")
                # else:
                #     exclusion_comments.append(
                #         'in_shape+culv_mat has unhandled combination of values: [{0}]'\
                #         .format(" + ".join([row["in_shape"], row["culv_mat"]]))
                #     )
                    

            elif row["in_shape"] == "Box":
                if row["culv_mat"] in ["Concrete", "Stone"]:
                    coefficient_c = 0.0378
                    coefficient_y = 0.870
                elif row["culv_mat"] in ["Plastic", "Metal"]:
                    if row["in_type"] == "Headwall":
                        coefficient_c = 0.0379
                        coefficient_y = 0.690  # put in else statement in case other inlet types exist-Sharon
                    elif row["in_type"] == "Wingwall":  ## Jo put this in but needs to check...
                        coefficient_c = 0.040
                        coefficient_y = 0.620
                        comments.append("Default c & Y values.")
                    else:
                        coefficient_c = 0.04  # c = 1.0
                        coefficient_y = 0.65  # Y = 1.0 #filler numbers -Sharon
                        comments.append("Default c & Y values.")
                elif row["culv_mat"] == "Wood":
                    coefficient_c = 0.038
                    coefficient_y = 0.87
                elif row["culv_mat"] == "Combination":
                    coefficient_c = 0.038
                    coefficient_y = 0.7  # filler values -Sharon
                    comments.append("Default c & Y values.")
                # else:
                #     exclusion_comments.append(
                #         'in_shape+culv_mat has unhandled combination of values: [{0}]'\
                #         .format(" + ".join([row["in_shape"], row["culv_mat"]]))
                #     )

            elif row["in_shape"] in ["Elliptical", "Pipe Arch"]:
                if row["culv_mat"] in ["Concrete", "Stone"]:
                    coefficient_c = 0.048
                    coefficient_y = 0.80
                elif row["culv_mat"] in ["Plastic", "Metal"]:
                    if row["in_type"] == "Projecting":
                        coefficient_c = 0.060
                        coefficient_y = 0.75
                    else:
                        coefficient_c = 0.048
                        coefficient_y = 0.80
                elif row["culv_mat"] == "Combination":
                    coefficient_c = 0.05  # c = 1.0
                    coefficient_y = 0.8  # Y = 1.0  #filler -Sharon
                    comments.append("Default c & Y values.")
                # else:
                #     exclusion_comments.append(
                #         'in_shape+culv_mat has unhandled combination of values: [{0}]'\
                #         .format(" + ".join([row["in_shape"], row["culv_mat"]]))
                #     )           

            elif row["in_shape"] == "Round":
                if row["culv_mat"] in ["Concrete", "Stone"]:
                    if row["in_type"] == "Projecting":
                        coefficient_c = 0.032
                        coefficient_y = 0.69
                    else:
                        coefficient_c = 0.029
                        coefficient_y = 0.74
                elif row["culv_mat"] in ["Plastic", "Metal"]:
                    if row["in_type"] == "Projecting":
                        coefficient_c = 0.055
                        coefficient_y = 0.54
                    elif row["in_type"] == "Mitered to Slope":
                        coefficient_c = 0.046
                        coefficient_y = 0.75
                    else:
                        coefficient_c = 0.038
                        coefficient_y = 0.69
                elif row["culv_mat"] == "Combination":
                    coefficient_c = 0.04  # c = 1.0
                    coefficient_y = 0.65  # Y = 1.0 #filler-Sharon
                    comments.append("Default c & Y values.")
            #     else:
            #         exclusion_comments.append(
            #             'in_shape+culv_mat has unhandled combination of values: [{0}]'\
            #             .format(" + ".join([row["in_shape"], row["culv_mat"]]))
            #         )
                    
            # else:
            #     exclusion_comments.append(
            #         'in_shape has unhandled value: [{0}]'\
            #         .format(row["in_shape"])
            #     )

            # store computed values in the row dictionary
            row['comments'] = "; ".join(comments)
            row['culvert_area_sqm'] = culvert_area_sqm
            row['culvert_depth_m'] = culvert_depth_m
            row['coefficient_c'] = coefficient_c
            row['coefficient_y'] = coefficient_y
            row['coefficient_slope'] = coefficient_slope
            row['head_over_invert'] = head_over_invert
            row['slope_rr'] = slope_rr
            
            if exclusion_comments:
                if row['validation_errors'] is not None:
                    row['validation_errors']['Capacity_Params'] = exclusion_comments
                else:
                    row['validation_errors'] = {'Capacity_Params': exclusion_comments}

            # return the row in the format expected by PETL.rowmap
            return tuple(row.values())
        
        except TypeError as e:
            print(e, row['Survey_Id'])
            print(row)
            # print(e.with_traceback())
            return tuple(row.values())

    def _extend_and_hydrate(
        self, 
        validated_table,
        lookup_naac_inlet_shape=NAACC_INLET_SHAPE_CROSSWALK,
        lookup_naac_inlet_type=NAACC_INLET_TYPE_CROSSWALK
        ):

        # ----------------------------------------------------------------------------
        # Derive params used for capacity & overflow calculations
        #
        # This will extend the table with Capacity fields, cross-walk from NAACC to Capacity
        # model, and apply validation steps for shapes, materials, and dimensions 
        # spec'd by Cornell Culvert 2.1.
        #
        # Add fields from the Capacity model to the table and crosswalk to generic fields and values.
        # * add capacity fields
        # * copy values from naacc fields / convert values using lookups
        # * set include/exclude based on capacity field values
        #
        # TODO: move everything below to a separate capacity-focused "extend and hyrdate" function

        # extend the table with fields from the Capacity model
        extended_table = etl\
            .addfields(
                validated_table, 
                [(f.name, f.default) for f in fields(Capacity)]
                # [(k, v.default) for k,v in Capacity.__dataclass_fields__.items()]
            )
        # get the new header
        extended_table_header = list(etl.header(extended_table))

        # hydrate the table: copy values from the NAACC fields to the Capacity fields,
        # crosswalk values, and derive parameters required for calculating capacity
        hydrated_table = etl\
            .rowmap(
                extended_table,
                self._xwalk_naac_to_capacity, 
                header=extended_table_header, 
                failonerror=True
            )\
            .convert(
                "in_shape",
                lambda v, r: convert_value_via_xwalk(r['Inlet_Structure_Type'], lookup_naac_inlet_shape),
                failonerror=True,
                pass_row=True
            )\
            .convert(
                "in_type",
                lambda v, r: convert_value_via_xwalk(r['Inlet_Type'], lookup_naac_inlet_type),
                failonerror=True,
                pass_row=True
            )\
            .rowmap(
                self._culvert_geometry_tests, 
                header=extended_table_header, 
                failonerror=True
            )\
            .rowmap(
                self._derive_capacity_parameters,
                header=extended_table_header, 
                failonerror=True
            )\
            .convert(
                'include', 
                lambda v, r: False if r['validation_errors'] is not None else True, 
                pass_row=True,
                failonerror=True,
            )\
            .convert(
                'culvert_capacity',
                lambda v, r: calc_culvert_capacity(
                    culvert_area_sqm=r['culvert_area_sqm'], 
                    head_over_invert=r['head_over_invert'], 
                    culvert_depth_m=r['culvert_depth_m'], 
                    slope_rr=r['slope_rr'], 
                    coefficient_slope=r['coefficient_slope'], 
                    coefficient_y=r['coefficient_y'],
                    coefficient_c=r['coefficient_c']
                    #si_conv_factor=si_conv_factor
                ),
                pass_row=True,
                failonerror=True
            )
            # .convert("comments",lambda v: [])\
            # .convert('validation_errors', lambda v: json.dumps(v))\
            # .replace('validation_errors', "null", "")
            # .replaceall("", None)

        return hydrated_table


    # ------------------------------------------------------------------------------
    # NAACC ETL FUNCTIONS

    def read_naacc_csv_to_petl(
        self, 
        naacc_csv_file=None,
        naacc_petl_table=None,
        output_path=None,
        lookup_naac_inlet_shape=NAACC_INLET_SHAPE_CROSSWALK,
        lookup_naac_inlet_type=NAACC_INLET_TYPE_CROSSWALK,
        wkid=4326
        ) -> List[DrainItPoint]:
        """performs ETL of a raw NAACC table to a PETL Table Object ~~appropriate Drain-It models.~~

        :param naacc_csv_file: (as string or Path object) to the naacc-conforming culvert data csv
        :type naacc_csv_file: str, Path
        :param output_path: [description], defaults to None
        :type output_path: [type], optional
        :param lookup_naac_inlet_shape: [description], defaults to NAACC_INLET_SHAPE_CROSSWALK
        :type lookup_naac_inlet_shape: [type], optional
        :param lookup_naac_inlet_type: [description], defaults to NAACC_INLET_TYPE_CROSSWALK
        :type lookup_naac_inlet_type: [type], optional
        :return: List of Drain-It Point models with nested NaaccCulvert and Capacity models.
        :rtype: List[Point]
        """

        naacc_csv_file = self.naacc_csv_file if naacc_csv_file is None else None
        naacc_petl_table = self.naacc_petl_table if naacc_petl_table is None else None
        output_path = self.output_path if output_path is None else None

        if not any([
            naacc_csv_file,
            naacc_petl_table
        ]):
            print("No input provided for the NAACC ETL function")
            return None
        else:
            raw_table = None

        if naacc_csv_file:
            ip = Path(naacc_csv_file)
            csv_name = ip.stem

            # read the file into a PETL table object
            raw_table = etl.fromcsv(naacc_csv_file)

        if naacc_petl_table:
            # use the provided PETL table object
            raw_table = naacc_petl_table

        # ----------------------------------------------------------------------------
        # Validate all NAACC rows against the schema
        #
        # This step only focuses on validation against the NAACC schema.
        #
        # the schema model will attempt to type-cast any numbers stored as strings 
        # for only fields in the NaacCulvert dataclass; remove empty strings and 
        # replace with nulls
        
        
        validated_table = etl\
            .replaceall(raw_table, "", None)\
            .addfield(
                'validation_errors', 
                lambda rec: validate_petl_record_w_schema(rec, self.naacc_culvert_schema)
            )

        bad = etl.selectnotnone(validated_table, 'validation_errors')
        print("{0} rows did not pass initial validation against the NAACC schema".format(etl.nrows(bad)))
        # print(etl.vis.see(bad))

        
        hydrated_table = self._extend_and_hydrate(
            validated_table=validated_table,
            lookup_naac_inlet_shape=lookup_naac_inlet_shape,
            lookup_naac_inlet_type=lookup_naac_inlet_type
        )

        bad2 = etl.selectnotnone(hydrated_table, 'validation_errors')
        print("{0} input points did not pass secondary validation (capacity)".format(etl.nrows(bad2) - etl.nrows(bad)))
        # print(etl.vis.see(bad2))
        
        # clean_table = etl.replaceall(hydrated_table, "", None)
        
        
        # optionally save the table to a CSV file
        if output_path:

            # before saving to CSV, convert the content of the validation errors field to a JSON string.
            hydrated_table_for_csv = etl.convert(hydrated_table, 'validation_errors', lambda v: json.dumps(v))

            # save the complete table
            etl.tocsv(hydrated_table_for_csv, output_path)
            # save the filtered versions of the table (mimicking the v2.1 outputs)
            op = Path(output_path)
            field_data, not_extracted = etl.biselect(hydrated_table_for_csv, lambda r: r.include == True)
            # etl.tocsv(field_data, op.parent / "{}_field_data.csv".format(op.stem))
            # etl.tocsv(not_extracted, op.parent / "{}_not_extracted.csv".format(op.stem))
            etl.tocsv(field_data, op.parent / "{}_naacc_valid.csv".format(op.stem))
            etl.tocsv(not_extracted, op.parent / "{}_naacc_invalid.csv".format(op.stem))

        
        self.table = hydrated_table
        return self.table

    def generate_points_from_table(self):

        if not self.table:
            return None

        # ---------------------------------
        # Load into our DraintItPoint and nested NAACC dataclasses

        points = []
        for idx, r in enumerate(list(etl.dicts(self.table))):
            
            kwargs = dict(
                uid=r["Naacc_Culvert_Id"],
                group_id=r["Survey_Id"],
                lat=float(r["GIS_Latitude"]),
                lng=float(r["GIS_Longitude"]),
                spatial_ref_code=self.wkid,
                include=r['include'],
                # raw=r
            )

            # this will add validation_errors if they exist.
            # Because the parent function is sometimes called when reading
            # from on-disk spatial data that doesn't support JSON
            # as a field type, it will come in as string. we want
            # to make sure it serializes to a dict at this point.
            if r['validation_errors']:
                rve = r['validation_errors']
                if isinstance(rve, str):
                    if len(rve) > 0:
                        ve = json.loads(rve)
                    else:
                       ve = {} 
                else:
                    ve = rve
                kwargs['validation_errors'] = ve
            
            # load the NAACC fields into the NAACC model
            try:
                naacc = self.naacc_culvert_schema.load(data=r, partial=True)
                kwargs['naacc'] = naacc
            except ValidationError as e:
                # print("schema error | NAACC | Survey/Culvert {0}/{1}: {2}".format(r["Survey_Id"], r["Naacc_Culvert_Id"], e))
                kwargs['include'] = False

            # NOTE: in all cases, we want to load whatever we get and derive
            # from NAACC to the data model. Sometimes, certain fields may be 
            # empty. In order to take advantage of serialization mechanisms we 
            # already have without getting hung up on validation, we empty the 
            # dict of any keys with None values:
            capacity_fields = [f.name for f in fields(Capacity)]
            c = {k:v for k,v in r.items() if v is not None and k in capacity_fields}
            
            # once loaded via the serializer, those None values will be
            # replaced with the defaults spec'd in the models (usually None)

            try:
                capacity = self.capacity_schema.load(data=c, partial=True)
                # calculate capacity here
                capacity.calculate()
                kwargs['capacity'] = capacity                
            except:
                # print("schema error | CAPACITY | Survey/Culvert {0}/{1}: {2}".format(r["Survey_Id"], r["Naacc_Culvert_Id"], e))
                kwargs['include'] = False
                try:
                    kwargs['capacity'] = self.capacity_schema.load(data=c, partial=True)
                except:
                    pass

            
            p = DrainItPoint(**kwargs)
            points.append(p)
        
        self.points = points