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

__version__ = "0.12.0"

import datetime
import typing
import uuid
import warnings

import case_utils.inherent_uuid
import rdflib
from case_utils.namespace import NS_RDF, NS_UCO_ACTION, NS_XSD
from cdo_local_uuid import local_uuid

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


def infer_prov_instantaneous_influence_event(
    in_graph: rdflib.Graph,
    n_prov_thing: rdflib.term.IdentifiedNode,
    n_predicate: rdflib.URIRef,
    n_prov_related_thing: rdflib.term.IdentifiedNode,
    rdf_namespace: rdflib.Namespace,
    *args: typing.Any,
    use_deterministic_uuids: bool = False,
    **kwargs: typing.Any,
) -> typing.Tuple[rdflib.term.IdentifiedNode, TmpTriplesType]:
    """
    PROV InstantaneousEvents that are also Influences need to be defined inhering in the two things related by the unqualified property.

    :returns: Returns a node N matching the pattern 'n_prov_thing n_predicate N', as well as a supplemental set of triples.  If a node N is not found in the graph, a node is created and linked in the supplemental triples; hence the length of the supplemental triples being >0 can be used as an indicator that the node was created.
    """
    slug = {
        NS_PROV.qualifiedCommunication: "Communication-",
        NS_PROV.qualifiedDerivation: "Derivation-",
        NS_PROV.qualifiedGeneration: "Generation-",
        NS_PROV.qualifiedInvalidation: "Invalidation-",
        NS_PROV.qualifiedUsage: "Usage-",
    }[n_predicate]

    ret_triples: TmpTriplesType = set()
    n_instantaneous_event: typing.Optional[rdflib.IdentifiedNode] = None
    for n_value in in_graph.objects(n_prov_thing, n_predicate):
        assert isinstance(n_value, rdflib.term.IdentifiedNode)
        n_instantaneous_event = n_value
        break
    if n_instantaneous_event is None:
        # Define event node.
        if isinstance(n_prov_thing, rdflib.URIRef) and isinstance(
            n_prov_related_thing, rdflib.URIRef
        ):
            if use_deterministic_uuids:
                prov_thing_uuid_namespace = case_utils.inherent_uuid.inherence_uuid(
                    n_prov_thing
                )
                predicated_uuid_namespace = uuid.uuid5(
                    prov_thing_uuid_namespace, str(n_predicate)
                )
                node_uuid = str(
                    uuid.uuid5(predicated_uuid_namespace, str(n_prov_related_thing))
                )
            else:
                node_uuid = local_uuid()
            n_instantaneous_event = rdf_namespace[slug + node_uuid]
        else:
            n_instantaneous_event = rdflib.BNode()
        # Link event node.
        ret_triples.add((n_prov_thing, n_predicate, n_instantaneous_event))
        # Type event node.
        n_instantaneous_event_type = {
            NS_PROV.qualifiedCommunication: NS_PROV.Communication,
            NS_PROV.qualifiedDerivation: NS_PROV.Derivation,
            NS_PROV.qualifiedGeneration: NS_PROV.Generation,
            NS_PROV.qualifiedInvalidation: NS_PROV.Invalidation,
            NS_PROV.qualifiedUsage: NS_PROV.Usage,
        }[n_predicate]
        ret_triples.add(
            (n_instantaneous_event, NS_RDF.type, n_instantaneous_event_type)
        )
        # Port timestamp to event node.
        if n_instantaneous_event_type == NS_PROV.Generation:
            for l_object in in_graph.objects(n_prov_thing, NS_PROV.generatedAtTime):
                assert isinstance(l_object, rdflib.Literal)
                ret_triples.add((n_instantaneous_event, NS_PROV.atTime, l_object))
        elif n_instantaneous_event_type == NS_PROV.Invalidation:
            for l_object in in_graph.objects(n_prov_thing, NS_PROV.invalidatedAtTime):
                assert isinstance(l_object, rdflib.Literal)
                ret_triples.add((n_instantaneous_event, NS_PROV.atTime, l_object))
        # Link provenentially-tied node to event node.
        n_inherent_influence_predicate = {
            NS_PROV.qualifiedCommunication: NS_PROV.activity,
            NS_PROV.qualifiedDerivation: NS_PROV.entity,
            NS_PROV.qualifiedGeneration: NS_PROV.activity,
            NS_PROV.qualifiedInvalidation: NS_PROV.activity,
            NS_PROV.qualifiedUsage: NS_PROV.entity,
        }[n_predicate]
        ret_triples.add(
            (
                n_instantaneous_event,
                n_inherent_influence_predicate,
                n_prov_related_thing,
            )
        )
    return (n_instantaneous_event, ret_triples)


def infer_interval_terminus(
    in_graph: rdflib.Graph,
    n_proper_interval: rdflib.term.IdentifiedNode,
    n_predicate: rdflib.URIRef,
    rdf_namespace: rdflib.Namespace,
    *args: typing.Any,
    use_deterministic_uuids: bool = False,
    **kwargs: typing.Any,
) -> typing.Tuple[typing.Optional[rdflib.term.IdentifiedNode], TmpTriplesType]:
    """
    :returns: Returns a node N matching the pattern 'n_proper_interval n_predicate N', as well as a supplemental set of triples.  If a node N is not found in the graph, and a node should exist (which is relevant when considering ends), a node is created and linked in the supplemental triples; hence the length of the supplemental triples being >0 can be used as an indicator that the node was created.  If the requested property indicates a search for an end, the graph is first reviewed to see if an end should exist.
    """
    slug = {
        NS_PROV.qualifiedEnd: "End-",
        NS_PROV.qualifiedStart: "Start-",
        NS_TIME.hasBeginning: "Instant-",
        NS_TIME.hasEnd: "Instant-",
    }[n_predicate]

    # See if we should even check for an end.
    if n_predicate in {NS_PROV.qualifiedEnd, NS_TIME.hasEnd}:
        if not interval_end_should_exist(in_graph, n_proper_interval):
            return (None, set())

    ret_triples: TmpTriplesType = set()
    n_terminus: typing.Optional[rdflib.IdentifiedNode] = None
    for n_value in in_graph.objects(n_proper_interval, n_predicate):
        assert isinstance(n_value, rdflib.term.IdentifiedNode)
        n_terminus = n_value
        break
    if n_terminus is None:
        # Define instant node.
        if isinstance(n_proper_interval, rdflib.URIRef):
            uuid_namespace = case_utils.inherent_uuid.inherence_uuid(n_proper_interval)
            if use_deterministic_uuids:
                node_uuid = str(uuid.uuid5(uuid_namespace, str(n_predicate)))
            else:
                node_uuid = local_uuid()
            n_terminus = rdf_namespace[slug + node_uuid]
        else:
            n_terminus = rdflib.BNode()
        # Link instant node.
        ret_triples.add((n_proper_interval, n_predicate, n_terminus))
        # Type instant node.
        n_instant_type = {
            NS_PROV.qualifiedEnd: NS_PROV.End,
            NS_PROV.qualifiedStart: NS_PROV.Start,
            NS_TIME.hasBeginning: NS_TIME.Instant,
            NS_TIME.hasEnd: NS_TIME.Instant,
        }[n_predicate]
        ret_triples.add((n_terminus, NS_RDF.type, n_instant_type))
    return (n_terminus, ret_triples)


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
