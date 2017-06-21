import pytest

import traitlets as T
from .. import jstraitlets as jst
from ..jstraitlets import undefined


def test_undefined_singleton():
    assert jst.UndefinedType() is undefined


def generate_test_cases():
    """yield tuples of (trait, failcases, passcases)"""
    # Nulls
    yield (jst.JSONNull(), [0, "None"], [None, undefined])
    yield (jst.JSONNull(allow_undefined=False), [undefined], [])

    # Booleans
    yield (jst.JSONBoolean(), [0, 2, 'abc'], [True, False])
    yield (jst.JSONBoolean(allow_undefined=False), [undefined], [])

    # Numbers
    yield (jst.JSONNumber(), [None, '123'], [-10.5, 42, 3.14, undefined])
    yield (jst.JSONNumber(allow_undefined=False), [undefined], [])
    yield (jst.JSONNumber(minimum=0, maximum=100, multipleOf=0.5),
           [-10, 110, 33.3], [0, 50, 60.5, 100])
    yield (jst.JSONNumber(minimum=0, maximum=100,
                          exclusiveMinimum=True, exclusiveMaximum=True),
           [0, 100], [0.01, 0.99])

    # Integers
    yield (jst.JSONInteger(minimum=0, maximum=100, multipleOf=2),
           [-10, 110, 29], [0, 50, 62, 100])
    yield (jst.JSONInteger(allow_undefined=False), [undefined], [])
    yield (jst.JSONInteger(minimum=0, maximum=100,
                          exclusiveMinimum=True, exclusiveMaximum=True),
           [0, 100], [1, 99])
    yield (jst.JSONInteger(), [None, '123', 3.14], [-10, 0, 42])

    # Strings
    yield (jst.JSONString(), [50, None, True], ['abc', undefined])
    yield (jst.JSONString(allow_undefined=False), [undefined], [])

    # Arrays
    yield (jst.JSONArray(jst.JSONString()),
           ["a", [1, 'b']], [["a", "b"], ['a'], undefined])
    yield (jst.JSONArray(jst.JSONString(), allow_undefined=False),
           [undefined], [])
    yield (jst.JSONArray(jst.JSONInteger(), minItems=1, maxItems=2),
           [[], [1, 2, 3]], [[1], [1, 2]])

    # Enums
    yield (jst.JSONEnum([1, "2", None]), ["1", 2, [1]],
                        [1, "2", None, undefined])
    yield (jst.JSONEnum([1, "2", None], allow_undefined=False), [undefined], [])

    # Instances
    yield (jst.JSONInstance(dict), [{1}, (1,), [1]], [{1:2}, undefined])
    yield (jst.JSONInstance(dict, allow_undefined=False), [undefined], [])

    # Unions and other collections
    yield (jst.JSONUnion([jst.JSONInteger(), jst.JSONString()]),
           [3.14, None], [42, "42", undefined])
    yield (jst.JSONAnyOf([jst.JSONInteger(), jst.JSONString()]),
           [3.14, None], [42, "42"])
    yield (jst.JSONOneOf([jst.JSONInteger(), jst.JSONNumber()]),
           [None, 3], [3.14])
    yield (jst.JSONAllOf([jst.JSONInteger(), jst.JSONNumber()]),
           [None, 3.14], [3])
    yield (jst.JSONNot(jst.JSONString()), ['a', 'abc'], [1, False, None])


@pytest.mark.parametrize('trait,failcases,passcases', generate_test_cases())
def test_traits(trait, failcases, passcases):
    obj = T.HasTraits()  # needed to pass to validate()

    for passcase in passcases:
        trait.validate(obj, passcase)

    for failcase in failcases:
        with pytest.raises(T.TraitError) as err:
            trait.validate(obj, failcase)