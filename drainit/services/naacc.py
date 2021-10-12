
from types import List
from pathlib import Path
from collections import OrderedDict
import pint
import petl as etl
from marshmallow import ValidationError

from . import validate_petl_record_w_schema, convert_value_via_xwalk
from ..models import (
    NaaccCulvert,
    NaaccCulvertSchema,
    Point
)
from ..calculators.capacity import (
    Capacity,
    CapacitySchema,
    capacity_numeric_fields
)

from ..config import (
    NAACC_HEADER_LOOKUP,
    NAACC_INLET_SHAPE_CROSSWALK,
    NAACC_INLET_TYPE_CROSSWALK
)

units = pint.UnitRegistry()

# ------------------------------------------------------------------------------
# NAACC ETL HELPER FUNCTIONS

def _copy_naac_to_capacity(row):
    """copy values from the NAACC fields to Capacity fields, type-casting
    numeric fields from strings along the way if necessary

    :param row: a single NAACC table row, where the table is from extract_naacc_table
    :type row: petl.Record
    :return: the row, w/ transformed or derived values
    :rtype: tuple    
    """
    
    r = OrderedDict({i[0]: i[1] for i in zip(row.flds, row)})
    
    for n_field, cap_field in NAACC_HEADER_LOOKUP.items():
        if cap_field in capacity_numeric_fields.keys():
            typ = capacity_numeric_fields[cap_field]
            try:
                r[cap_field] = typ(r[n_field])
            except:
                r[cap_field] = r[n_field]
        
    return tuple(r.values())

def _naacc_exclude_tests(row):
    """determines whether a naacc culvert can be included for analysis based
    on a number of conditions.
    Used within the context of a petl.rowmap function; writes to a boolean 
    `include` column and the validation_errors column

    :param row: a single NAACC table row, where the table is from extract_naacc_table
    :type row: petl.Record
    :return: the row, w/ transformed or derived values
    :rtype: tuple

    """

    # convert PETL Record object to an ordered dictionary
    r = OrderedDict({i[0]: i[1] for i in zip(row.flds, row)})
    
    #if r['validation_errors'] is not None:
    #   return tuple(r.values())
    
    try:
        
        exclusion_comments = []

        # wrong bridge type
        if all([
            r["crossing_type"] == "Bridge",
            r["in_shape"]
            not in ["Box/Bridge with Abutments", "Open Bottom Arch Bridge/Culvert"],
        ]):
            r["exclude"] = True
            exclusion_comments.append("Wrong bridge type")

        # wrong bridge width
        if all([
            r["crossing_type"] == "Bridge", 
            r["in_a"] is not None and r["in_a"] >= 20
        ]):
            r["exclude"] = True
            exclusion_comments.append("Bridge wider than 20 ft")

        # bad geometry
        if not all([
            isinstance(r["in_a"], float),
            isinstance(r["in_b"], float),
            isinstance(r["hw"], float),
            isinstance(r["length"], float)
        ]):
            r["include"] = False
            exclusion_comments.append("Required culvert geometry is missing")
        elif any([
            r["in_a"] < 0,
            r["in_b"] < 0,
            r["hw"] < 0,
            r["length"] < 0
        ]):
            r["include"] = False
            exclusion_comments.append("Required culvert geometry is negative.")
        else:
            pass
        
        if exclusion_comments:
            if r['validation_errors'] is not None:
                r['validation_errors']['Capacity'] = exclusion_comments
            else:
                r['validation_errors'] = {'Capacity': exclusion_comments}

        # return as a tuple of values for the row
        return tuple(r.values())
    
    except TypeError as e:
        print('_naacc_exclude_tests', e, r['Survey_Id'])
        #print(r)
        return tuple(r.values())

def _derive_capacity_parameters(row):
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
                row["comments"].append("Filler c & Y values.")
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
                    row["comments"].append("Filler c & Y values.")
                else:
                    coefficient_c = 0.04  # c = 1.0
                    coefficient_y = 0.65  # Y = 1.0 #filler numbers -Sharon
                    row["comments"].append("Filler c & Y values.")
            elif row["culv_mat"] == "Wood":
                coefficient_c = 0.038
                coefficient_y = 0.87
            elif row["culv_mat"] == "Combination":
                coefficient_c = 0.038
                coefficient_y = 0.7  # filler values -Sharon
                row["comments"].append("Filler c & Y values.")
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
                row["comments"].append("Filler c & Y values.")
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
                row["comments"].append("Filler c & Y values.")
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
        print(e.with_traceback())
        return tuple(row.values())

# ------------------------------------------------------------------------------
# NAACC ETL FUNCTION

def etl_naacc_table(
    naacc_csv_file=None,
    naacc_petl_table=None,
    output_path=None,
    lookup_naac_inlet_shape=NAACC_INLET_SHAPE_CROSSWALK,
    lookup_naac_inlet_type=NAACC_INLET_TYPE_CROSSWALK,
    spatial_ref_code=4326
    ) -> List[Point]:
    """performs ETL of a raw NAACC table to the appropriate Drain-It models.

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
    # validate all rows against the schema
    # TODO: move this to a separate validation step
    #
    # the schema model will attempt to type-cast any numbers stored as strings 
    # for only fields in the NaacCulvert dataclass; remove empty strings and 
    # replace with nulls

    naacc_culvert_schema = NaaccCulvertSchema()
    
    validated_table = etl\
        .replaceall(raw_table, "", None)\
        .addfield(
            'validation_errors', 
            lambda rec: validate_petl_record_w_schema(rec, naacc_culvert_schema)
        )

    bad = etl.selectnotnone(validated_table, 'validation_errors')
    print("{0} NAACC rows did not pass intial validation".format(etl.nrows(bad)))

    
    # ----------------------------------------------------------------------------
    # Derive params used for capacity & overflow calculations
    # TODO: move everything below to a separate "extend and hyrdate" function

    # Add fields from the Capacity model to the table and crosswalk to generic fields and values.
    # * add capacity fields
    # * copy values from naacc fields / convert values using lookups
    # * set include/exclude based on capacity field values

    # extend the table with fields from the Capacity model
    extended_table = etl\
        .addfields(
            validated_table, 
            [(k, v.default) for k,v in Capacity.__dataclass_fields__.items()]
        )
    # get the new header
    extended_table_header = list(etl.header(extended_table))

    # hydrate the table: copy values from the NAACC fields to the Capacity fields,
    # crosswalk values, and derive parameters required for calculating capacity
    hydrated_table = etl\
        .rowmap(
            extended_table,
            _copy_naac_to_capacity, 
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
        .convert("comments",lambda v: [])\
        .rowmap(
            _naacc_exclude_tests, 
            header=extended_table_header, 
            failonerror=True
        )\
        .rowmap(
            _derive_capacity_parameters,
            header=extended_table_header, 
            failonerror=True
        )

    bad = etl.selectnotnone(hydrated_table, 'validation_errors')
    print("{0} input points did not pass secondary validation".format(etl.nrows(bad)))


    # TODO: determine if we need to still incorporate the old barrier ID 
    # generation method:
    # Assign the Barrier ID, after all the unmodelable rows are removed
    # UPDATED Jan 2018 - in case watershed name is longer than 3 characters, the ID still needs only 3
    # FieldData = FieldData.assign(BarrierID = [str(i+1) + ws_name[:3].upper() for i in range(len(FieldData))])

    # TODO: determine if the aim of this legacy code is needed now:
    # Re-assign the number of culverts for each crossing location based on how many culverts were kept
    # for SI in FieldData.loc[FieldData['Flags']>1]['Survey_ID'].unique():
    #     NC = FieldData.loc[FieldData['Survey_ID'] == SI]['Survey_ID'].count() # Number of culverts we will model at site
    #     ONC = FieldData.loc[FieldData['Survey_ID'] == SI]['Flags'].max() # Number culverts noted at site
    #     if NC <> ONC:
    #         FieldData.loc[FieldData['Survey_ID'] == SI, 'Modeling_notes'] = "Not all culverts modeled at crossing. Started with " + str(ONC)
    #         print "Not all culverts modeled at Survey ID " + str(SI) + " . Started with " + str(ONC) + " but kept " + str(NC)
    #     FieldData.loc[FieldData['Survey_ID'] == SI, 'Flags'] = NC


    # ---------------------------------
    # Load into our Point and nested NAACC dataclasses

    capacity_schema = CapacitySchema()

    points = []
    for idx, r in enumerate(list(etl.dicts(hydrated_table))):
        
        kwargs = dict(
            uid=r["Naacc_Culvert_Id"],
            group_id=r["Survey_Id"],
            lat=float(r["GIS_Latitude"]),
            lng=float(r["GIS_Longitude"]),
            spatial_ref_code=spatial_ref_code,
            include=r['include'],
            raw=r
        )

        if r['validation_errors']:
            kwargs['validation_errors'] = {'naacc': r['validation_errors']}
        
        try:
            naacc = naacc_culvert_schema.load(data=r)
            capacity = capacity_schema.load(data=r)
            # calculatue capacity here
            capacity.calculate()
            
            kwargs['naacc'] = naacc
            kwargs['capacity'] = capacity
            
        except ValidationError as e:
            print("Naacc_Culvert_Id {0}: {1}".format(r["Naacc_Culvert_Id"], e))
            kwargs['include'] = False
        
        p = Point(**kwargs)
        points.append(p)
    
    
    # optionally save the table to a CSV file
    if output_path:
        # save the complete table
        etl.tocsv(hydrated_table, output_path)
        # save the filtered versions of the table (mimicking the v2.1 outputs)
        op = Path(output_path)
        field_data, not_extracted = etl.selecteq(hydrated_table, "include", True, complement=True)
        # etl.tocsv(field_data, op.parent / "{}_field_data.csv".format(op.stem))
        # etl.tocsv(not_extracted, op.parent / "{}_not_extracted.csv".format(op.stem))
        etl.tocsv(field_data, op.parent / "{}_naacc_valid.csv".format(op.stem))
        etl.tocsv(not_extracted, op.parent / "{}_naacc_invalid.csv".format(op.stem))        

    
    return points