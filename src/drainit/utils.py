from collections.abc import Mapping, Iterable
from dataclasses import is_dataclass, fields
from functools import partial, wraps
from chardet.universaldetector import UniversalDetector

import petl as etl

def fxio(preprocess=None, postprocess=None):
    """https://stackoverflow.com/q/55564330

    Args:
        preprocess (function, optional): [description]. Defaults to None.
        postprocess (function, optional): [description]. Defaults to None.
    """
    def decorator(func):
        if preprocess and postprocess:
            def func_wrapper(*args, **kwargs):
                return postprocess(func(preprocess(*args, **kwargs)))
        elif preprocess:
            def func_wrapper(*args, **kwargs):
                return func(preprocess(*args, **kwargs))
        elif postprocess:
            def func_wrapper(*args, **kwargs):
                return postprocess(func(*args, **kwargs))
        else:  
            return func

        return wraps(func)(func_wrapper)

    return decorator

def stringify(obj, indent=4, _indents=0):
    if isinstance(obj, str):
        return f"'{obj}'"

    if not is_dataclass(obj) and not isinstance(obj, (Mapping, Iterable)):
        return str(obj)

    this_indent = indent * _indents * ' '
    next_indent = indent * (_indents + 1) * ' '
    start, end = f'{type(obj).__name__}(', ')'  # dicts, lists, and tuples will re-assign this

    if is_dataclass(obj):
        body = '\n'.join(
            f'{next_indent}{field.name}='
            f'{stringify(getattr(obj, field.name), indent, _indents + 1)},' for field in fields(obj)
        )

    elif isinstance(obj, Mapping):
        if isinstance(obj, dict):
            start, end = '{}'

        body = '\n'.join(
            f'{next_indent}{stringify(key, indent, _indents + 1)}: '
            f'{stringify(value, indent, _indents + 1)},' for key, value in obj.items()
        )

    else:  # is Iterable
        if isinstance(obj, list):
            start, end = '[]'
        elif isinstance(obj, tuple):
            start = '('

        body = '\n'.join(
            f'{next_indent}{stringify(item, indent, _indents + 1)},' for item in obj
        )

    return f'{start}\n{body}\n{this_indent}{end}'

def pretty_print(obj, indent=4):
    """
    Pretty prints a (possibly deeply-nested) dataclass.
    Each new block will be indented by `indent` spaces (default is 4).

    https://stackoverflow.com/questions/66807878/pretty-print-dataclasses-prettier
    """
    print(stringify(obj, indent))

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
    # d = schema.load(r, partial=True)
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

def get_type(typ, fallback=str):
    """gets the definitive type of the thing, handling Unions types by returning
    the first possible type that isn't NoneType.
    """
    if type(typ) is not type:
        types = [t for t in typ.__args__ if t != type(None)]
        if len(types) > 0:
            return types[0]
        else: 
            return fallback
    return typ


def read_csv_with_petl(source, **kwargs):
    """reads a CSV into PETL, handling different file encodings to ensure a
    clean result (i.e., no BOM in the header).

    Args:
        source (_type_): _description_

    Returns:
        _type_: _description_
    """

    file_encoding = None
    detector = UniversalDetector()
    file_open = open(source, 'rb')
    for line in file_open.readlines():
        detector.feed(line)
        if detector.done: break
    detector.close()
    file_open.close()
    file_encoding = detector.result['encoding']
    
    # with open(source, "rb") as file:
    #     beginning = file.read(4)
    #     # The order of these if-statements is important
    #     # otherwise UTF32 LE may be detected as UTF16 LE
    #     # or utf-8-sig may be detected as utf-8
    #     if beginning ==         b'\xef\xbb\xbfS':
    #         file_encoding =     "utf_8_sig"
    #     if beginning ==         b'\x00\x00\xfe\xff':
    #         file_encoding=      "utf_32_be"
    #     elif beginning ==       b'\xff\xfe\x00\x00':
    #         file_encoding =     "utf_32_le"
    #     elif beginning[0:3] ==  b'\xef\xbb\xbf':
    #         file_encoding =     "utf_8"
    #     elif beginning[0:2] ==  b'\xff\xfe':
    #         file_encoding =     "utf_16_le"
    #     elif beginning[0:2] ==  b'\xfe\xff':
    #         file_encoding ==    "utf_16_be"
    #     else:
    #         print("Unknown file encoding or no BOM")
    print("CSV file encoding:", file_encoding)

    return etl.fromcsv(source=source, encoding=file_encoding, **kwargs)
       