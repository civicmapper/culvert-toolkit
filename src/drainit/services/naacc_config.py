"""NAACC CONSTANTS & LOOKUPS
"""


NAACC_INLET_SHAPE_CROSSWALK = {
    'Round Culvert': 'Round',
    'Pipe Arch/Elliptical Culvert': 'Elliptical',
    'Box Culvert': 'Box',
    'Box/Bridge with Abutments': 'Box',
    'Bridge with Abutments and Side Slopes': 'Box',
    'Open Bottom Arch Bridge/Culvert': 'Arch'
}

NAACC_INLET_TYPE_CROSSWALK = {
    "Headwall and Wingwalls": "Wingwall and Headwall",
    "Wingwalls": "Wingwall",
    "None": "Projecting"
}

# crosswalk NaaccCulvert fields with Capacity fields
NAACC_HEADER_XWALK = [
    # {'field_idx': 0, 'field_name': 'Survey_Id', 'field_short': 'group_id' },
    # {'field_idx': 35, 'field_name': 'Naacc_Culvert_Id', 'field_short': 'uid'},
    # {'field_idx': 20, 'field_name': 'GIS_Latitude', 'field_short': 'lat', 'field_type': float},
    # {'field_idx': 19, 'field_name': 'GIS_Longitude', 'field_short': 'lng', 'field_type': float},
    # {'field_idx': 26, 'field_name': 'Road', 'field_short': 'rd_name'},
    {'field_idx': 11, 'field_name': 'Crossing_Type', 'field_short': 'crossing_type'},
    {'field_idx': 8,  'field_name': 'Crossing_Comment', 'field_short': 'comments'}
    {'field_idx': 39, 'field_name': 'Crossing_Structure_Length', 'field_short': 'length', 'field_type': float},    
    {'field_idx': 22, 'field_name': 'Inlet_Type', 'field_short': 'in_type'},
    {'field_idx': 44, 'field_name': 'Inlet_Structure_Type', 'field_short': 'in_shape'},
    {'field_idx': 47, 'field_name': 'Inlet_Width', 'field_short': 'in_a', 'field_type': float},
    {'field_idx': 43, 'field_name': 'Inlet_Height', 'field_short': 'in_b', 'field_type': float},
    {'field_idx': 49, 'field_name': 'Material', 'field_short': 'culv_mat'},    
    {'field_idx': 55, 'field_name': 'Outlet_Structure_Type', 'field_short': 'out_shape'},
    {'field_idx': 58, 'field_name': 'Outlet_Width', 'field_short': 'out_a', 'field_type': float},
    {'field_idx': 54, 'field_name': 'Outlet_Height', 'field_short': 'out_b', 'field_type': float},
    {'field_idx': 27, 'field_name': 'Road_Fill_Height', 'field_short': 'hw', 'field_type': float},
    {'field_idx': 61, 'field_name': 'Slope_Percent', 'field_short': 'slope', 'field_type': float},


    # {'field_idx': 24, 'field_name': 'Number_Of_Culverts', 'field_short': 'flags', 'field_type': int}
]

NAACC_HEADER_LOOKUP = {i['field_name']: i['field_short'] for i in NAACC_HEADER_XWALK}

NAACC_TYPECASTS = {
    i['field_short']: i['field_type'] 
    for i in 
    NAACC_HEADER_XWALK
    if 'field_type' in i.keys()
}

NAACC_TYPECASTS_FULLNAME = {
    i['field_name']: i['field_type'] 
    for i in 
    NAACC_HEADER_XWALK
    if 'field_type' in i.keys()
}