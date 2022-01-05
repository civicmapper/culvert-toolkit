
def validate_petl_record_w_schema(row, schema):
    """takes a PETL table row (Record) and validates it against a Marshmallow Schema.

    :param row: a single PETL table row/record object
    :type row: petl.Record
    :param schema: a Marshmallow schema used to validate the values in the row
    :type schema: marshmallow.schema
    :return: a list of errors returned by the schema validation
    :rtype: list
    """
    r = {i[0]: i[1] for i in zip(row.flds, row)}
    errors = schema.validate(r)
    if errors:
        return errors
    return None

def convert_value_via_xwalk(k, crosswalk, preserve_non_matches=True, no_match_value=None):
    """Returns match from a lookup (dictionary), with add'l params for fallbacks.
    Used with the context of an petl.convert lambda

    :param k: [description]
    :type k: [type]
    :param crosswalk: [description]
    :type crosswalk: [type]
    :param no_match_value: [description], defaults to None
    :type no_match_value: [type], optional
    :return: [description]
    :rtype: [type]
    """
    if k in crosswalk.keys():
        return crosswalk[k]
    else:
        if preserve_non_matches:
            return k
        else:
            return no_match_value