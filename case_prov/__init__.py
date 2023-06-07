#!/usr/bin/env python3

# This software was developed at the National Institute of Standards
# and Technology by employees of the Federal Government in the course
# of their official duties. Pursuant to title 17 Section 105 of the
# United States Code this software is not subject to copyright
# protection and is in the public domain. NIST assumes no
# responsibility whatsoever for its use by other parties, and makes
# no guarantees, expressed or implied, about its quality,
# reliability, or any other characteristic.
#
# We would appreciate acknowledgement if the software is used.

__version__ = "0.7.0"

import datetime
import typing
import warnings

import rdflib
from case_utils.namespace import NS_XSD


def xsd_datetime_to_xsd_datetimestamp(
    l_literal: rdflib.term.Literal,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> typing.Optional[rdflib.term.Literal]:
    """
    This function converts a `rdflib.Literal` with datatype of xsd:dateTime to one with xsd:dateTimeStamp, unless the conditions of a dateTimeStamp can't be met (such as the input `rdflib.Literal` not having a timezone).

    >>> x = rdflib.Literal("2020-01-02T03:04:05", datatype=rdflib.XSD.dateTime)
    >>> xsd_datetime_to_xsd_datetimestamp(x)  # Note: returns None
    >>> y = rdflib.Literal("2020-01-02T03:04:05Z", datatype=rdflib.XSD.dateTime)
    >>> xsd_datetime_to_xsd_datetimestamp(y)
    rdflib.term.Literal('2020-01-02T03:04:05+00:00', datatype=rdflib.term.URIRef('http://www.w3.org/2001/XMLSchema#dateTimeStamp'))
    >>> z = rdflib.Literal("2020-01-02T03:04:05+01:00", datatype=rdflib.XSD.dateTime)
    >>> xsd_datetime_to_xsd_datetimestamp(z)
    rdflib.term.Literal('2020-01-02T03:04:05+01:00', datatype=rdflib.term.URIRef('http://www.w3.org/2001/XMLSchema#dateTimeStamp'))
    """
    _datetime = l_literal.toPython()
    if not isinstance(_datetime, datetime.datetime):
        warnings.warn(
            "Literal %r did not cast as datetime.datetime Python object." % l_literal
        )
        return None
    if _datetime.tzinfo is None:
        return None
    return rdflib.term.Literal(_datetime, datatype=NS_XSD.dateTimeStamp)
