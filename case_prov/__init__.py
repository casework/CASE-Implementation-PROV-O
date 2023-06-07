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
from case_utils.namespace import NS_UCO_ACTION, NS_XSD

NS_PROV = rdflib.PROV
NS_TIME = rdflib.TIME

# This module returns sets of triples that might or might not be
# serialized into a graph.
#
# case_prov_dot augments the input graph with temporary triples that
# will not typically be serialized into a separate graph.  (If
# requested, they will be serialized into a debug graph.)  Because these
# temporary nodes only need to exist long enough to make a Dot source
# file, they are permitted to be blank nodes.  The type used for this is
# `case_prov.TmpTriplesType`.  Compare this with
# `case_prov_rdf.TmpPersistableTriplesType`, where blank nodes are
# excluded to avoid creating new nodes that would need to be reconciled
# later with mechanisms similar to `owl:sameAs`.
TmpTriplesType = typing.Set[
    typing.Tuple[rdflib.term.IdentifiedNode, rdflib.URIRef, rdflib.term.Node]
]


def interval_end_should_exist(
    graph: rdflib.Graph,
    n_interval: rdflib.term.IdentifiedNode,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> typing.Optional[bool]:
    """
    This function reviews the input graph to see if the requested interval uses a property that indicates an end is known to exist, such as a DatatypeProperty recording an ending timestamp, or a relationship with another interval that depends on a defined end.  Inverse relationships are also reviewed.
    :param n_interval: A RDFLib Node (URIRef or Blank Node) that represents a time:ProperInterval, prov:Activity, or uco-action:Action.
    :returns: Returns True if an interval end is implied to exist.  Returns None if existence can't be inferred with the information in the graph.  In accordance with the Open World assumption, False is not currently returned.

    >>> g = rdflib.Graph()
    >>> i = rdflib.BNode()
    >>> j = rdflib.BNode()
    >>> g.add((i, rdflib.TIME.intervalBefore, j))
    <Graph identifier=... (<class 'rdflib.graph.Graph'>)>
    >>> interval_end_should_exist(g, i)
    True
    >>> interval_end_should_exist(g, j)
    >>> x = rdflib.BNode()
    >>> y = rdflib.BNode()
    >>> g.add((x, rdflib.TIME.intervalAfter, y))
    <Graph identifier=... (<class 'rdflib.graph.Graph'>)>
    >>> interval_end_should_exist(g, x)
    >>> interval_end_should_exist(g, y)
    True
    >>> # Assert the two intervals with ends of previously unknown
    >>> # existence are equal, which implies that while the ends are not
    >>> # yet described absolutely in time-position, they are now known
    >>> # to exist and be equal in time-position to one another.
    >>> # The beginnings were already believed to exist, but now they
    >>> # are also believed to be equal in time-position.
    >>> g.add((j, rdflib.TIME.intervalEquals, x))
    <Graph identifier=... (<class 'rdflib.graph.Graph'>)>
    >>> interval_end_should_exist(g, j)
    True
    >>> interval_end_should_exist(g, x)
    True
    >>> # The general time:after relator implies the existence of an
    >>> # ending instant when any temporal entity comes after an
    >>> # interval.
    >>> # Be aware that it is somewhat out of scope of this function to
    >>> # determine if the nodes being related with time:before and
    >>> # time:after are time:ProperIntervals.  This information might
    >>> # not always be available (e.g. it might require RDFS or OWL
    >>> # inferencing first).
    >>> i = rdflib.BNode()
    >>> j = rdflib.BNode()
    >>> _ = g.add((i, rdflib.RDF.type, rdflib.TIME.ProperInterval))
    >>> _ = g.add((j, rdflib.TIME.after, i))
    >>> interval_end_should_exist(g, i)
    True
    >>> i = rdflib.BNode()
    >>> j = rdflib.BNode()
    >>> _ = g.add((i, rdflib.RDF.type, rdflib.TIME.ProperInterval))
    >>> _ = g.add((i, rdflib.TIME.before, j))
    >>> interval_end_should_exist(g, i)
    True
    >>> # The remainder of this docstring shows how each OWL-Time time
    >>> # interval relator affects whether an ending instant is
    >>> # expected.
    >>> # Note the "inverse" relators test j, following the notation of
    >>> # this figure:
    >>> # https://www.w3.org/TR/owl-time/#fig-thirteen-elementary-possible-relations-between-time-periods-af-97
    >>> i = rdflib.BNode()
    >>> _ = g.add((i, rdflib.TIME.intervalBefore, rdflib.BNode()))
    >>> interval_end_should_exist(g, i)
    True
    >>> i = rdflib.BNode()
    >>> _ = g.add((i, rdflib.TIME.intervalMeets, rdflib.BNode()))
    >>> interval_end_should_exist(g, i)
    True
    >>> i = rdflib.BNode()
    >>> _ = g.add((i, rdflib.TIME.intervalOverlaps, rdflib.BNode()))
    >>> interval_end_should_exist(g, i)
    True
    >>> i = rdflib.BNode()
    >>> _ = g.add((i, rdflib.TIME.intervalStarts, rdflib.BNode()))
    >>> interval_end_should_exist(g, i)
    True
    >>> i = rdflib.BNode()
    >>> _ = g.add((i, rdflib.TIME.intervalDuring, rdflib.BNode()))
    >>> interval_end_should_exist(g, i)
    True
    >>> i = rdflib.BNode()
    >>> _ = g.add((i, rdflib.TIME.intervalFinishes, rdflib.BNode()))
    >>> interval_end_should_exist(g, i)
    True
    >>> i = rdflib.BNode()
    >>> _ = g.add((i, rdflib.TIME.intervalEquals, rdflib.BNode()))
    >>> interval_end_should_exist(g, i)
    True
    >>> i = rdflib.BNode()
    >>> _ = g.add((i, rdflib.TIME.intervalIn, rdflib.BNode()))
    >>> interval_end_should_exist(g, i)
    True
    >>> i = rdflib.BNode()
    >>> _ = g.add((i, rdflib.TIME.intervalDisjoint, rdflib.BNode()))
    >>> interval_end_should_exist(g, i)
    True
    >>> j = rdflib.BNode()
    >>> _ = g.add((j, rdflib.TIME.intervalAfter, rdflib.BNode()))
    >>> interval_end_should_exist(g, j)
    >>> j = rdflib.BNode()
    >>> _ = g.add((j, rdflib.TIME.intervalMetBy, rdflib.BNode()))
    >>> interval_end_should_exist(g, j)
    >>> j = rdflib.BNode()
    >>> _ = g.add((j, rdflib.TIME.intervalOverlappedBy, rdflib.BNode()))
    >>> interval_end_should_exist(g, j)
    >>> j = rdflib.BNode()
    >>> _ = g.add((j, rdflib.TIME.intervalStartedBy, rdflib.BNode()))
    >>> interval_end_should_exist(g, j)
    >>> j = rdflib.BNode()
    >>> _ = g.add((j, rdflib.TIME.intervalContains, rdflib.BNode()))
    >>> interval_end_should_exist(g, j)
    >>> j = rdflib.BNode()
    >>> _ = g.add((j, rdflib.TIME.intervalFinishedBy, rdflib.BNode()))
    >>> interval_end_should_exist(g, j)
    True
    >>> j = rdflib.BNode()
    >>> _ = g.add((j, rdflib.TIME.intervalEquals, rdflib.BNode()))
    >>> interval_end_should_exist(g, j)
    True
    """
    for n_predicate in {
        NS_PROV.endedAtTime,
        NS_TIME.before,
        NS_TIME.intervalBefore,
        NS_TIME.intervalDisjoint,
        NS_TIME.intervalDuring,
        NS_TIME.intervalEquals,
        NS_TIME.intervalFinishedBy,
        NS_TIME.intervalFinishes,
        NS_TIME.intervalIn,
        NS_TIME.intervalMeets,
        NS_TIME.intervalOverlaps,
        NS_TIME.intervalStarts,
        NS_UCO_ACTION.endTime,
    }:
        for n_object in graph.objects(n_interval, n_predicate):
            return True
    for n_predicate in {
        NS_TIME.after,
        NS_TIME.intervalAfter,
        NS_TIME.intervalContains,
        NS_TIME.intervalEquals,
        NS_TIME.intervalFinishedBy,
        NS_TIME.intervalFinishes,
        NS_TIME.intervalMetBy,
        NS_TIME.intervalOverlappedBy,
        NS_TIME.intervalStartedBy,
    }:
        for n_inverse_subject in graph.subjects(n_predicate, n_interval):
            return True
    return None


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
