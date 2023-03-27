import json
import click
from typing import List
from pathlib import Path
from collections import OrderedDict
from dataclasses import fields
import pdb

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
    CAPACITY_NUMERIC_FIELDS
)
from ..utils import (
    validate_petl_record_w_schema, 
    convert_value_via_xwalk,
    read_csv_with_petl
)
from .naacc_config import (
    NAACC_HEADER_LOOKUP, 
    NAACC_INLET_SHAPE_CROSSWALK, 
    NAACC_INLET_TYPE_CROSSWALK
)

units = pint.UnitRegistry()

# pi. Note that Cornell source script used a precision 5 float instead of 
# Python's available math.pi constant, the latter likely being more precise
PI = 3.14159 #math.pi


class NaaccEtl:

    def __init__(
        self,
        naacc_csv_file=None,
        naacc_petl_table=None,
        output_path=None,
        lookup_naac_inlet_shape=NAACC_INLET_SHAPE_CROSSWALK,
        lookup_naac_inlet_type=NAACC_INLET_TYPE_CROSSWALK,
        wkid=4326,
        naacc_x="GIS_Longitude",
        naacc_y="GIS_Latitude",
        naacc_uid="Naacc_Culvert_Id",
        naacc_groupid="Survey_Id"
        ) ->  None:

        self.naacc_csv_file=naacc_csv_file
        self.naacc_petl_table=naacc_petl_table
        self.output_path=output_path
        self.lookup_naac_inlet_shape=lookup_naac_inlet_shape
        self.lookup_naac_inlet_type=lookup_naac_inlet_type
        self.wkid=wkid

        self.naacc_x = naacc_x
        self.naacc_y = naacc_y
        self.naacc_uid = naacc_uid
        self.naacc_groupid = naacc_groupid

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
    
    def _xwalk_naacc_to_capacity(self, row):
        """crosswalk values from the NAACC fields to Capacity fields, type-casting
        numeric fields from strings along the way if necessary

        :param row: a single NAACC table row, where the table is from extract_naacc_table
        :type row: petl.Record
        :return: the row, w/ transformed or derived values
        :rtype: tuple
        """
        
        r = OrderedDict({i[0]: i[1] for i in zip(row.flds, row)})
        # print(capacity_numeric_fields)
        for n_field, cap_field in NAACC_HEADER_LOOKUP.items():
            # for numeric fields, cast values to the specified python type based on the lookup above
            if cap_field in CAPACITY_NUMERIC_FIELDS.keys():
                number_type = CAPACITY_NUMERIC_FIELDS[cap_field]
                try:
                    r[cap_field] = number_type(r[n_field])
                except:
                    r[cap_field] = r.get(n_field)
            # otherwise just copy them over
            else:
                r[cap_field] = r.get(n_field)
        # print({k:v for k,v in r.items() if k in capacity_numeric_fields})
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
        # print("row.flds\n", row.flds)
        # print("row\n", row)
        # convert PETL Record object to an ordered dictionary
        r = OrderedDict({i[0]: i[1] for i in zip(row.flds, row)})
        # print("\nrow\n",r)
        # print(len(row), len(row.flds), len(r.keys()))
        
        # if r['validation_errors'] is not None:
        #   return tuple(r.values())
        
        # try:

        
        # collect any reasons for exclusion here:
        validation_errors = {}

        # -----------------------------
        # check 1: only specific xing_types
        OK_CROSSING_TYPES = [i.lower() for i in [
            'Culvert', 
            'Multiple Culvert'
        ]]

        if r.get("xing_type","").lower() not in OK_CROSSING_TYPES:
            r["include"] = False
            validation_errors.setdefault('xing_type', []).append("Not a culvert or multi-culvert ({0})".format(r["in_shape"]))

        # -----------------------------
        # Check 2: bad geometry

        CULVERT_GEOMETRY_FIELDS_TO_CHECK_1 = [
            "in_a", 
            "in_b", 
            "hw", 
            "length"
        ]

        # check if all values in culvert_geometry_fields are floats:
        culvert_geometry_fields_are_floats = [
            isinstance(r[f], float)
            for f in CULVERT_GEOMETRY_FIELDS_TO_CHECK_1
        ]
        # check if any values in culvert_geometry_fields are < 0:
        culvert_geometry_fields_are_lt0 = [
            v < 0 for v in 
            [r[f] for f in CULVERT_GEOMETRY_FIELDS_TO_CHECK_1]
            if v is not None
        ]

        if not all(culvert_geometry_fields_are_floats):
            r["include"] = False
            for f, v in zip(CULVERT_GEOMETRY_FIELDS_TO_CHECK_1, culvert_geometry_fields_are_floats):
                if v is None:
                    validation_errors.setdefault(f, []).append("cannot be None.")
                else:
                    validation_errors.setdefault(f, []).append("must be a number ({0})".format(v))
            # validation_errors.append("Required culvert geometry is missing: {0}".format([f for f,v in zip(culvert_geometry_fields, culvert_geometry_fields_are_floats) if not v]))
        elif any(culvert_geometry_fields_are_lt0):
            r["include"] = False
            for f, v in zip(CULVERT_GEOMETRY_FIELDS_TO_CHECK_1, culvert_geometry_fields_are_lt0):
                if v:
                    validation_errors.setdefault(f, []).append("must be a greater than zero ({0})".format(v))
            # validation_errors.append("Required culvert geometry is negative: {0}".format([f for f,v in zip(culvert_geometry_fields, culvert_geometry_fields_are_gt0) if not v]))
        else:
            pass

        # -----------------------------
        # Check 3: missing slope values
        # NOTE: moved this logic to _derive_capacity_parameters
        # -1 as an integer in the slope field indicates a missing slope value.
        # Per this issue https://github.com/civicmapper/culvert-toolkit/issues/6 
        # Let slope with a -1 through (include=True), but include a validation 
        # error message in the validation_errors field, and set slope to 0
        # slope = r.get("slope")
        # if slope == -1 or slope is None:
        #     r['slope'] = 0
        #     validation_errors\
        #         .setdefault('slope', [])\
        #         .append("slope missing (-1). Assuming 0 slope for capacity calculation")
            
        # -------------------------------------------------
        # Compile all validation errors and write to field

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
        
        # ----------------------------------------------------------------------
        # safety valve: minimal processing if record is invalid
        if row.get('include') == False:

            # -----------------------------------------------------
            # imperial to metric conversions
            # NAACC data uses imperial, these calculations use metric
            for f in ["length", "in_a", "in_b", "hw", "out_a", "out_b"]:
                try:
                    # these measurements all should be positive
                    if row[f] >= 0:
                        row[f] = (row[f] * units.foot).to(units.meter).magnitude
                    # if not, the source data was invalid anyway
                    else:
                        row[f] = None
                except:
                    # exceptions may be raised with NoneTypes
                    pass

            return tuple(row.values())

        # ----------------------------------------------------------------------
        # proceed with unit conversion and derivation of capacity parameter

        try:

            # -----------------------------------------------------
            # constants 

            # pi. Note: the Cornell source script used a precision 5 float instead of 
            # Python's available math.pi constant, the latter likely being more precise
            pi = PI

            # -----------------------------------------------------
            # imperial to metric conversions
            # NAACC data uses imperial, these calculations use metric

            row["length"] = (row["length"] * units.foot).to(units.meter).magnitude
            row["in_a"] = (row["in_a"] * units.foot).to(units.meter).magnitude
            row["in_b"] = (row["in_b"] * units.foot).to(units.meter).magnitude
            row["hw"] = (row["hw"] * units.foot).to(units.meter).magnitude
            row["out_a"] = (row["out_a"] * units.foot).to(units.meter).magnitude
            row["out_b"] = (row["out_b"] * units.foot).to(units.meter).magnitude

            # -----------------------------------------------------
            # variable defaults

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
            # culvert slope as rise/run
            
            if row["slope"] == -1:
                comments.append("slope missing (-1), defaulting to 0.")
            else:
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
        """
        Derive params used for capacity & overflow calculations
        
        This will extend the table with Capacity fields, cross-walk from NAACC to Capacity
        model, and apply validation steps for shapes, materials, and dimensions 
        spec'd by Cornell Culvert 2.1.
        
        Add fields from the Capacity model to the table and crosswalk to generic fields and values.
        * add capacity fields
        * copy values from naacc fields / convert values using lookups
        * set include/exclude based on capacity field values
        
        """

        # Extend the table with fields from the Capacity model
        # Remove any columns that already exist (this will remove any data that 
        # may have existed in those columns in the input table)
        capacity_model_columns = [(f.name, f.default) for f in fields(Capacity)]
        already_exists = [h[0] for h in capacity_model_columns if h[0] in etl.header(validated_table)]
        extended_table = etl\
            .cutout(validated_table, *already_exists)\
            .addfields(capacity_model_columns)
        # get the new header
        extended_table_header = list(etl.header(extended_table))
        # hydrate the table: copy values from the NAACC fields to the Capacity fields,
        # crosswalk values, and derive parameters required for calculating capacity
        hydrated_table = etl\
            .rowmap(
                extended_table,
                self._xwalk_naacc_to_capacity, 
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

        # pdb.set_trace()

        return hydrated_table


    # ------------------------------------------------------------------------------
    # NAACC ETL FUNCTIONS

    def validate_extend_hydrate_naacc_table(
        self, 
        naacc_csv_file=None,
        naacc_petl_table=None,
        output_path=None,
        lookup_naac_inlet_shape=NAACC_INLET_SHAPE_CROSSWALK,
        lookup_naac_inlet_type=NAACC_INLET_TYPE_CROSSWALK,
        wkid=4326
        ) -> List[DrainItPoint]:
        """performs ETL of a raw NAACC table to a PETL Table Object that has been
        extended with fields used by the calculators.

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

        click.echo("Performing NAACC data ingest")

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
            raw_table = read_csv_with_petl(naacc_csv_file)

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

        has_rows = etl.nrows(raw_table) > 0
        
        if not has_rows:
            click.echo('No rows. Creating empty outputs.')
        
        
        # Create a fieldmap. Most fields are 1:1, except for validation_errors,
        # which is updated with validation error messages
        validated_table_fieldmap = OrderedDict([(h, h) for h in etl.header(raw_table)])
        validated_table_fieldmap['validation_errors'] = lambda rec: validate_petl_record_w_schema(rec, self.naacc_culvert_schema)
        # run the transform
        validated_table = etl\
            .replaceall(raw_table, "", None)\
            .fieldmap(validated_table_fieldmap)
        
        if has_rows:
            bad = etl.selectnotnone(validated_table, 'validation_errors')
            bad_ct = etl.nrows(bad)
            if bad_ct > 0:
                click.echo("> {0} rows did do not conform to the NAACC schema".format(bad_ct))
            else:
                click.echo("> All rows conform to the NAACC schema")
        # print(etl.vis.see(bad))


        # ----------------------------------------------------------------------------
        # Hydrate the table: 
        #
        # This step entails deriving params used for capacity & overflow 
        # calculations from NAACC columns.
        #

        hydrated_table = self._extend_and_hydrate(
            validated_table=validated_table,
            lookup_naac_inlet_shape=lookup_naac_inlet_shape,
            lookup_naac_inlet_type=lookup_naac_inlet_type
        )

        if has_rows:
            bad2 = etl.selectnotnone(hydrated_table, 'validation_errors')
            bad2_ct = etl.nrows(bad2) - bad_ct
            if bad2_ct > 0:
                click.echo("> {0} rows do not have all the data required for capacity calculations".format(bad2_ct))
            else:
                click.echo("> All rows have all the data required for capacity calculations")

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
            click.echo("No point data.")
            return None

        # ---------------------------------
        # Load into our DraintItPoint and nested NAACC dataclasses
        src_points = list(etl.dicts(self.table))

        click.echo("Generating {0} points from table".format(len(src_points)))

        points = []
        for idx, r in enumerate(src_points):
            
            kwargs = dict(
                uid=r["Naacc_Culvert_Id"],
                group_id=r["Survey_Id"],
                lng=float(r[self.naacc_x]),
                lat=float(r[self.naacc_y]),
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