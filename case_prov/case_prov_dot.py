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

"""
This script renders PROV-O elements of a graph according to the graphic design elements suggested by the PROV-O documentation page, Figure 1.

Any temporal ordering among the visible nodes is included as hidden (unless --display-time-links is passed) edges to impose topological, and generally downward-displaying, ordering.  This sorting assumes the non-normative alignment of TIME and PROV-O, available at:

https://github.com/w3c/sdw/blob/gh-pages/time/rdf/time-prov.ttl

prov:Activities and uco-action:Actions are further assumed to be time:ProperIntervals.
"""

# TODO - The label adjustment with "ID - " is a hack.  A hyphen forces
# pydot to quote the label string.  Colons don't.  Hence, if the label
# string is just alphanumeric characters and colons, the string won't
# get quoted.  This turns out to be a dot syntax error.  Need to report
# this upstream to pydot.

__version__ = "0.5.1"

import argparse
import collections
import copy
import hashlib
import logging
import os
import textwrap
import typing
import uuid

import case_utils.inherent_uuid
import cdo_local_uuid
import prov.constants  # type: ignore
import prov.dot  # type: ignore
import pydot  # type: ignore
import rdflib.plugins.sparql
from case_utils.namespace import NS_CASE_INVESTIGATION, NS_RDF, NS_RDFS, NS_UCO_CORE
from cdo_local_uuid import local_uuid

import case_prov

_logger = logging.getLogger(os.path.basename(__file__))

NS_EPHEMERAL = rdflib.Namespace("urn:example:ephemeral:")
NS_PROV = rdflib.PROV
NS_TIME = rdflib.TIME

# This one isn't among the prov constants.
PROV_COLLECTION = NS_PROV.Collection


def clone_style(prov_constant: rdflib.URIRef) -> typing.Dict[str, str]:
    retval: typing.Dict[str, str]
    if prov_constant == PROV_COLLECTION:
        retval = copy.deepcopy(prov.dot.DOT_PROV_STYLE[prov.constants.PROV_ENTITY])
    else:
        retval = copy.deepcopy(prov.dot.DOT_PROV_STYLE[prov_constant])

    # Adjust shapes and colors.
    if prov_constant == PROV_COLLECTION:
        retval["shape"] = "folder"
        retval["fillcolor"] = "khaki3"
    elif prov_constant == prov.constants.PROV_ENTITY:
        # This appeared to be the closest color name to the hex constant.
        retval["fillcolor"] = "khaki1"
    elif prov_constant == prov.constants.PROV_COMMUNICATION:
        retval["color"] = "blue3"

    return retval


def get_interval_boundary_instants(
    graph: rdflib.Graph,
    n_interval: rdflib.term.IdentifiedNode,
    beginning: bool,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> typing.Set[rdflib.term.IdentifiedNode]:
    """
    This method is designed to be compatible with owl:sameAs.
    """
    n_boundary_instants: typing.Set[rdflib.term.IdentifiedNode] = set()
    n_predicate = NS_TIME.hasBeginning if beginning else NS_TIME.hasEnd
    for n_object in graph.objects(n_interval, n_predicate):
        assert isinstance(n_object, rdflib.term.IdentifiedNode)
        n_boundary_instants.add(n_object)
    return n_boundary_instants


def get_beginnings(
    graph: rdflib.Graph,
    n_interval: rdflib.term.IdentifiedNode,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> typing.Set[rdflib.term.IdentifiedNode]:
    """
    Get all instants asserted to be the beginning of the requested time:Interval.

    This method is designed to be compatible with owl:sameAs.
    """
    return get_interval_boundary_instants(graph, n_interval, True)


def get_ends(
    graph: rdflib.Graph,
    n_interval: rdflib.term.IdentifiedNode,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> typing.Set[rdflib.term.IdentifiedNode]:
    """
    Get all instants asserted to be the end of the requested time:Interval.

    This method is designed to be compatible with owl:sameAs.
    """
    return get_interval_boundary_instants(graph, n_interval, False)


def iri_to_gv_node_id(n_thing: rdflib.term.IdentifiedNode) -> str:
    """
    This function returns a string safe to use as a Dot node identifier.  The main concern addressed is Dot syntax errors caused by use of colons in IRIs.

    >>> x = rdflib.URIRef("urn:example:kb:x")
    >>> iri_to_gv_node_id(x)
    '_b42f80365d50f29359b0a4d682366646248b4939a2b291e821a0f8bdaae4cd2a'
    """
    hasher = hashlib.sha256()
    hasher.update(str(n_thing).encode())
    return "_" + hasher.hexdigest()


def linked_temporal_entities(
    graph: rdflib.Graph,
    n_predicate: rdflib.URIRef,
    n_inverse_predicate: typing.Optional[rdflib.URIRef] = None,
) -> typing.Set[typing.Tuple[rdflib.term.IdentifiedNode, rdflib.term.IdentifiedNode]]:
    """
    Get all time:TemporalEntitys linked by the requested predicate.  The inverse, if supplied, will augment the returned set as though the inverse were OWL-expanded in the graph.
    """
    linked_temporal_entities: typing.Set[
        typing.Tuple[rdflib.term.IdentifiedNode, rdflib.term.IdentifiedNode]
    ] = set()
    for triple in graph.triples((None, n_predicate, None)):
        assert isinstance(triple[0], rdflib.term.IdentifiedNode)
        assert isinstance(triple[2], rdflib.term.IdentifiedNode)
        linked_temporal_entities.add((triple[0], triple[2]))
    if n_inverse_predicate is not None:
        for triple in graph.triples((None, n_inverse_predicate, None)):
            assert isinstance(triple[0], rdflib.term.IdentifiedNode)
            assert isinstance(triple[2], rdflib.term.IdentifiedNode)
            linked_temporal_entities.add((triple[2], triple[0]))
    return linked_temporal_entities


def expand_prov_activities_with_owl_time(
    graph: rdflib.Graph,
    ns_kb: rdflib.Namespace,
    use_deterministic_uuids: bool,
    *args: typing.Any,
    debug_graph_fh: typing.Optional[typing.TextIO] = None,
    **kwargs: typing.Any,
) -> None:
    """
    This procedure takes a graph and guarantees all time:ProperIntervals have reified Instant nodes as their beginnings and ends.  Following guidance from the non-normative time-prov alignment, prov:Activities are also inferred to be time:ProperIntervals, and prov:InstantaneousEvents (especially prov:Start and prov:End nodes) are inferred to be time:Instants.  prov:startedAtTime and prov:endedAtTime are used to infer time:Instant nodes as a last fallback.

    While most of this is done with SPARQL CONSTRUCT queries, there is a step in converting from xsd:dateTime to xsd:dateTimeStamp that, at this time, appears to require data validation that is more difficult to perform in SPARQL than in Python.
    """

    debug_graph = rdflib.Graph()

    def _dump_augments(
        tmp_triples: typing.Union[rdflib.Graph, case_prov.TmpTriplesType]
    ) -> None:
        """
        Macro: Copy tmp_triples into graph and debug graph.
        """
        _logger.debug("len(tmp_triples) = %d.", len(tmp_triples))
        if isinstance(tmp_triples, rdflib.Graph):
            for triple in tmp_triples.triples((None, None, None)):
                graph.add(triple)
                debug_graph.add(triple)
        else:
            for triple in tmp_triples:
                # _logger.debug("triple = %r.", triple)
                graph.add(triple)
                debug_graph.add(triple)

    def _build_augments_from_query(query: str) -> None:
        # _logger.debug("query = %r.", query)
        tmp_triples: case_prov.TmpTriplesType = set()
        for result in graph.query(query):
            # _logger.debug(result)
            assert isinstance(result, tuple)
            assert isinstance(result[0], rdflib.term.IdentifiedNode)
            assert isinstance(result[1], rdflib.URIRef)
            assert isinstance(result[2], rdflib.term.Node)
            tmp_triples.add((result[0], result[1], result[2]))
        _dump_augments(tmp_triples)

    # Do some manual domain inference.  (This subroutine depends on
    # prov:Activity types being explicit for some queries binding new
    # blank nodes.)
    query = """\
CONSTRUCT {
  ?nActivity a prov:Activity .
}
WHERE {
  { ?nActivity prov:endedAtTime ?x . }
  UNION
  { ?nActivity prov:qualifiedEnd ?x . }
  UNION
  { ?nActivity prov:qualifiedStart ?x . }
  UNION
  { ?nActivity prov:startedAtTime ?x . }
}
"""
    _build_augments_from_query(query)

    n_activities: typing.Set[rdflib.term.IdentifiedNode] = set()
    for n_subject in graph.subjects(NS_RDF.type, NS_PROV.Activity):
        assert isinstance(n_subject, rdflib.term.IdentifiedNode)
        n_activities.add(n_subject)

    # Ensure each prov:Activity has qualifiedStart---and where
    # appropriate, qualifiedEnd---populated.

    # Extend existing TIME individuals into PROV qualified Starts and
    # Ends.
    query = """\
CONSTRUCT {
  ?nActivity prov:qualifiedStart ?nInstantaneousEvent .
  ?nInstantaneousEvent a prov:Start .
}
WHERE {
  FILTER NOT EXISTS {
    ?nActivity prov:qualifiedStart ?nStart .
  }
  ?nActivity time:hasBeginning ?nInstantaneousEvent .
}
"""
    _build_augments_from_query(query)

    query = """\
CONSTRUCT {
  ?nActivity prov:qualifiedEnd ?nInstantaneousEvent .
  ?nInstantaneousEvent a prov:End .
}
WHERE {
  FILTER NOT EXISTS {
    ?nActivity prov:qualifiedEnd ?nEnd .
  }
  ?nActivity time:hasEnd ?nInstantaneousEvent .
}
"""
    _build_augments_from_query(query)

    # Guarantee all prov:Activities have a qualified Start node, and if
    # there is an indicator they end, an End node.

    for n_activity in sorted(n_activities):
        (_, start_graph) = case_prov.infer_interval_terminus(
            graph,
            n_activity,
            NS_PROV.qualifiedStart,
            ns_kb,
            use_deterministic_uuids=use_deterministic_uuids,
        )
        _dump_augments(start_graph)
        del start_graph

        if case_prov.interval_end_should_exist(graph, n_activity):
            (_, end_graph) = case_prov.infer_interval_terminus(
                graph,
                n_activity,
                NS_PROV.qualifiedEnd,
                ns_kb,
                use_deterministic_uuids=use_deterministic_uuids,
            )
            _dump_augments(end_graph)
            del end_graph

    def _fail_on_find(query: str) -> None:
        for result in graph.query(query):
            _logger.debug(query)
            _logger.debug(result)
            raise ValueError("Found result indicating process failure.")

    query = """\
SELECT ?nActivity
WHERE {
  ?nActivity a prov:Activity .
  FILTER NOT EXISTS {
    ?nActivity prov:qualifiedStart ?nStart .
  }
}
"""
    _fail_on_find(query)

    # Do TIME-PROV entailments.

    # First, entail superclasses, which is what RDFS inferencing would
    # devise with these axioms:
    #
    #     prov:Activity
    #         rdfs:subClassOf time:ProperInterval ;
    #         .
    #     prov:InstantaneousEvent
    #         rdfs:subClassOf time:Instant ;
    #         .
    #
    query = """\
CONSTRUCT {
  ?nActivity a time:ProperInterval .
} WHERE {
  ?nActivity a prov:Activity .
}
"""
    _build_augments_from_query(query)

    # This includes one level of PROV-based RDFS entailment, based on
    # the five explicit subclasses of prov:InstantaneousEvent.
    query = """\
CONSTRUCT {
  ?nInstantaneousEvent a time:Instant .
} WHERE {
  { ?nInstantaneousEvent a prov:InstantaneousEvent . }
  UNION
  { ?nInstantaneousEvent a prov:End . }
  UNION
  { ?nInstantaneousEvent a prov:Generation . }
  UNION
  { ?nInstantaneousEvent a prov:Invalidation . }
  UNION
  { ?nInstantaneousEvent a prov:Start . }
  UNION
  { ?nInstantaneousEvent a prov:Usage . }
}
"""
    _build_augments_from_query(query)

    # Augment links between prov:Activities and their Starts and Ends
    # with corresponding predicates from TIME.
    # This is what RDFS inference would devise with these axioms:
    #
    #     prov:qualifiedEnd
    #         rdfs:subPropertyOf time:hasEnd ;
    #         .
    #     prov:qualifiedStart
    #         rdfs:subPropertyOf time:hasBeginning ;
    #         .
    #
    query = """\
CONSTRUCT {
  ?nActivity
    time:hasBeginning ?nStart ;
    time:hasEnd ?nEnd ;
    .
}
WHERE {
  ?nActivity prov:qualifiedStart ?nStart .
  OPTIONAL {
    ?nActivity prov:qualifiedEnd ?nEnd .
  }
}
"""
    _build_augments_from_query(query)

    # Find all time:Instants without inXSDDateTimeStamp populated, and
    # assign values based on available data.

    def _build_datetimestamp_augments_from_query(query: str) -> None:
        _logger.debug("query = %r.", query)
        tmp_triples: case_prov.TmpTriplesType = set()
        for result in graph.query(query):
            assert isinstance(result, rdflib.query.ResultRow)
            assert isinstance(result[0], rdflib.term.IdentifiedNode)
            assert isinstance(result[1], rdflib.term.Literal)
            l_datetimestamp = case_prov.xsd_datetime_to_xsd_datetimestamp(result[1])
            if l_datetimestamp is not None:
                tmp_triples.add(
                    (
                        result[0],
                        NS_TIME.inXSDDateTimeStamp,
                        l_datetimestamp,
                    )
                )
        _dump_augments(tmp_triples)

    # Find from prov literal values in Event.
    query = """\
SELECT ?nStart ?lAtTime
WHERE {
  ?nStart prov:atTime ?lAtTime .
  FILTER NOT EXISTS {
    ?nStart time:inXSDDateTimeStamp ?lDateTimeStamp .
  }
}
"""
    _build_datetimestamp_augments_from_query(query)

    query = """\
SELECT ?nEnd ?lAtTime
WHERE {
  ?nEnd prov:atTime ?lAtTime .
  FILTER NOT EXISTS {
    ?nEnd time:inXSDDateTimeStamp ?lDateTimeStamp .
  }
}
"""
    _build_datetimestamp_augments_from_query(query)

    # Find from prov literal values on Activity.
    query = """\
SELECT ?nStart ?lStartedAtTime
WHERE {
  ?nActivity prov:startedAtTime ?lStartedAtTime .
  ?nActivity time:hasBeginning ?nStart .
  FILTER NOT EXISTS {
    ?nStart time:inXSDDateTimeStamp ?lDateTimeStamp .
  }
}
"""
    _build_datetimestamp_augments_from_query(query)

    query = """\
SELECT ?nEnd ?lEndedAtTime
WHERE {
  ?nActivity prov:endedAtTime ?lEndedAtTime .
  ?nActivity time:hasEnd ?nEnd .
  FILTER NOT EXISTS {
    ?nEnd time:inXSDDateTimeStamp ?lDateTimeStamp .
  }
}
"""
    _build_datetimestamp_augments_from_query(query)

    n_proper_intervals: typing.Set[rdflib.term.IdentifiedNode] = set()
    for n_subject in graph.subjects(NS_RDF.type, NS_TIME.ProperInterval):
        assert isinstance(n_subject, rdflib.term.IdentifiedNode)
        n_proper_intervals.add(n_subject)

    # For remaining time:ProperIntervals, guarantee they have beginning
    # and, if appropriate, ending nodes.
    for n_proper_interval in sorted(n_proper_intervals):
        (_, start_graph) = case_prov.infer_interval_terminus(
            graph,
            n_proper_interval,
            NS_TIME.hasBeginning,
            ns_kb,
            use_deterministic_uuids=use_deterministic_uuids,
        )
        _dump_augments(start_graph)
        del start_graph

        if case_prov.interval_end_should_exist(graph, n_proper_interval):
            (_, end_graph) = case_prov.infer_interval_terminus(
                graph,
                n_proper_interval,
                NS_TIME.hasEnd,
                ns_kb,
                use_deterministic_uuids=use_deterministic_uuids,
            )
            _dump_augments(end_graph)
            del end_graph

    # Infer time:inside relationships for Entities' InstantaneousEvents.

    query = """\
CONSTRUCT {
  ?nActivity time:inside ?nGeneration .
}
WHERE {
  ?nGeneration
    a prov:Generation ;
    prov:activity ?nActivity ;
    .
}
"""
    _build_augments_from_query(query)

    query = """\
CONSTRUCT {
  ?nActivity time:inside ?nInvalidation .
}
WHERE {
  ?nInvalidation
    a prov:Invalidation ;
    prov:activity ?nActivity ;
    .
}
"""
    _build_augments_from_query(query)

    query = """\
CONSTRUCT {
  ?nActivity time:inside ?nUsage .
}
WHERE {
  ?nActivity
    prov:qualifiedUsage ?nUsage ;
    .
}
"""
    _build_augments_from_query(query)

    # Infer "Witness" Instants for the three pairs of interval relations
    # that are visually affected by the latter interval having an ending
    # or not.  E.g., take Overlaps(i,j):
    #
    # i_b     i       i_e
    # |---------------|
    #             j_b     j       j_e
    #             |---------------|
    #                  xxxxxxxxxxx
    #
    # If the end of interval j (j_e) does not exist---say, because an
    # Activity is known to not have ended yet---then the rendered
    # Instant i_e cannot be related to anything about j except for j_b.
    # But because the assertion Overlaps(i,j) is in the graph, a
    # "witness" instant somewhere in j is known to exist and follow i_e,
    # somewhere in the region illustrated above with 'x's.

    def _define_witnesses(
        n_terminus_instant: rdflib.term.IdentifiedNode,
        n_wrapping_interval: rdflib.term.IdentifiedNode,
        n_relating_predicate: rdflib.term.URIRef,
    ) -> case_prov.TmpTriplesType:
        tmp_triples: case_prov.TmpTriplesType = set()
        n_witness: rdflib.term.IdentifiedNode
        if isinstance(n_terminus_instant, rdflib.URIRef) and isinstance(
            n_wrapping_interval, rdflib.URIRef
        ):
            if use_deterministic_uuids:
                base_uuid_namespace = case_utils.inherent_uuid.inherence_uuid(
                    n_wrapping_interval
                )
                uuid_namespace = base_uuid_namespace
                for n_thing in [
                    n_relating_predicate,
                    n_terminus_instant,
                    NS_TIME.after,
                ]:
                    uuid_namespace = uuid.uuid5(uuid_namespace, n_thing)
                node_uuid = str(uuid_namespace)
            else:
                node_uuid = local_uuid()
            n_witness = ns_kb["Instant-" + node_uuid]
        else:
            n_witness = rdflib.BNode()
        tmp_triples.add((n_witness, NS_RDF.type, NS_TIME.Instant))
        tmp_triples.add((n_witness, NS_RDF.type, NS_EPHEMERAL.WitnessInstant))
        tmp_triples.add((n_wrapping_interval, NS_TIME.inside, n_witness))
        tmp_triples.add((n_witness, NS_TIME.after, n_terminus_instant))
        tmp_triples.add((n_witness, NS_EPHEMERAL.witnesses, n_terminus_instant))
        return tmp_triples

    witness_tmp_triples: case_prov.TmpTriplesType = set()
    for n_predicate, n_inverse_predicate in [
        (NS_TIME.intervalOverlaps, NS_TIME.intervalOverlappedBy),
        (NS_TIME.intervalStarts, NS_TIME.intervalStartedBy),
        (NS_TIME.intervalDuring, NS_TIME.intervalContains),
    ]:
        for n_interval_i, n_interval_j in sorted(
            linked_temporal_entities(graph, n_predicate, n_inverse_predicate)
        ):
            n_instant_j_es = get_ends(graph, n_interval_j)
            if len(n_instant_j_es) == 0:
                # Interval j has no end.  Define "witness" Instants that
                # follows the end(s) of i.
                n_instant_i_es = get_ends(graph, n_interval_i)
                for n_instant_i_e in sorted(n_instant_i_es):
                    predicate_tmp_triples = _define_witnesses(
                        n_instant_i_e, n_interval_j, n_predicate
                    )
                    witness_tmp_triples |= predicate_tmp_triples
    _dump_augments(witness_tmp_triples)

    if debug_graph_fh is not None:
        debug_graph_fh.write(debug_graph.serialize(format="longturtle"))


def qname(graph: rdflib.Graph, n_thing: rdflib.term.IdentifiedNode) -> str:
    """
    This function provides, when a namespace is available, the prefixed form of the input node.  Blank nodes are rendered solely with str().
    """
    # TODO This function might be obviated by resolution of this issue:
    # https://github.com/RDFLib/rdflib/issues/2429
    if isinstance(n_thing, rdflib.URIRef):
        return graph.namespace_manager.qname(n_thing)
    else:
        return str(n_thing)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--debug-graph", type=argparse.FileType("x"))
    parser.add_argument(
        "--dash-unqualified",
        action="store_true",
        help="Use dash-style edges for graph nodes not also related by qualifying Influences.",
    )
    parser.add_argument(
        "--display-time-intervals",
        action="store_true",
        help="Display time:ProperIntervals whether or not they are `prov:Activity`s.  Without this flag, intervals are present for on-canvas sorting, but invisible.",
    )
    parser.add_argument(
        "--display-time-links",
        action="store_true",
        help="Use dotted-style edges for graph nodes linked by time: relations.  Without this flag, time links are present for on-canvas sorting, but invisible.  Implies --display-time-intervals.",
    )
    parser.add_argument(
        "--kb-iri",
        default="http://example.org/kb/",
        help="Fallback IRI to use for the knowledge base namespace.",
    )
    parser.add_argument(
        "--kb-prefix",
        default="kb",
        help="Knowledge base prefix for compacted IRI form.  If this prefix is already in the input graph, --kb-iri will be ignored.",
    )
    parser.add_argument(
        "--use-deterministic-uuids",
        action="store_true",
        help="Use UUIDs computed using the case_utils.inherent_uuid module.  This will stabilize generated Dot output when time:Instants are inferred.",
    )
    parser.add_argument(
        "--query-ancestry",
        help="Visualize the ancestry of the nodes returned by the SPARQL query in this file.  Query must be a SELECT that returns non-blank nodes.",
    )
    parser.add_argument(
        "--entity-ancestry",
        help="Visualize the ancestry of the node with this IRI.  If absent, entire graph is returned.",
    )  # TODO - Add inverse --entity-progeny as well.
    parser.add_argument("--from-empty-set", action="store_true")
    parser.add_argument("--omit-empty-set", action="store_true")
    parser.add_argument(
        "--wrap-comment",
        type=int,
        nargs="?",
        default=60,
        help="Number of characters to have before a line wrap in rdfs:label renders.",
    )
    subset_group = parser.add_argument_group(
        description="Use of any of these flags will reduce the displayed nodes to those pertaining to the chain of Communication (Activities), Delegation (Agents), or Derivation (Entities).  More than one of the flags can be used."
    )
    subset_group.add_argument(
        "--activity-informing",
        action="store_true",
        help="Display Activity nodes and wasInformedBy relationships.",
    )
    subset_group.add_argument(
        "--agent-delegating",
        action="store_true",
        help="Display Agent nodes and actedOnBehalfOf relationships.",
    )
    subset_group.add_argument(
        "--entity-deriving",
        action="store_true",
        help="Display Entity nodes and wasDerivedBy relationships.",
    )
    parser.add_argument("out_dot")
    parser.add_argument("in_graph", nargs="+")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    cdo_local_uuid.configure()

    graph = rdflib.Graph()
    for in_graph_filename in args.in_graph:
        graph.parse(in_graph_filename)

    graph.bind("case-investigation", NS_CASE_INVESTIGATION)
    graph.bind("prov", NS_PROV)
    graph.bind("time", NS_TIME)

    nsdict = {k: v for (k, v) in graph.namespace_manager.namespaces()}

    # Determine knowledge base prefix for new inherent nodes.
    if args.kb_prefix in nsdict:
        NS_KB = rdflib.Namespace(nsdict[args.kb_prefix])
    elif args.kb_iri in nsdict.values():
        NS_KB = rdflib.Namespace(args.kb_iri)
    else:
        NS_KB = rdflib.Namespace(args.kb_iri)

    use_deterministic_uuids = args.use_deterministic_uuids is True

    # Add a few axioms from PROV-O.
    graph.add((NS_PROV.Collection, NS_RDFS.subClassOf, NS_PROV.Entity))
    graph.add((NS_PROV.Person, NS_RDFS.subClassOf, NS_PROV.Agent))
    graph.add((NS_PROV.SoftwareAgent, NS_RDFS.subClassOf, NS_PROV.Agent))

    # The rest of this script follows this flow:
    # S1. Build the sets of PROV Things.
    # S2. Build the sets of TIME Things.
    # S3. Build the ways in which Things that will be displayed will be
    #     displayed [sic.].
    # S3.1. Build for PROV Things.
    # S3.2. Build for TIME Things.
    # S4. Build the sets of Things to display.  This is done after
    #     building how-to-display details in S3 in order to reuse query
    #     results from S3.
    # S5. Load the Things that will be displayed into a Pydot Graph.

    # S1.
    # Define sets of instances of the "Starting Point" PROV classes,
    # plus Collections.  These aren't necessarily instances that will
    # display in the Dot render; they are instead use for analytic
    # purposes to determine how to display things.  Thus, they should be
    # constructed maximally according to the input graph.

    n_activities: typing.Set[rdflib.term.IdentifiedNode] = set()
    n_agents: typing.Set[rdflib.term.IdentifiedNode] = set()
    n_collections: typing.Set[rdflib.term.IdentifiedNode] = {NS_PROV.EmptyCollection}
    n_entities: typing.Set[rdflib.term.IdentifiedNode] = {NS_PROV.EmptyCollection}
    # Defined later as a set-union.
    n_prov_basis_things: typing.Set[rdflib.term.IdentifiedNode]

    # Populate Activities.
    select_query_text = """\
SELECT ?nActivity
WHERE {
  ?nActivity a/rdfs:subClassOf* prov:Activity .
}
"""
    select_query_object = rdflib.plugins.sparql.processor.prepareQuery(
        select_query_text, initNs=nsdict
    )
    for result in graph.query(select_query_object):
        assert isinstance(result, rdflib.query.ResultRow)
        assert isinstance(result[0], rdflib.term.IdentifiedNode)
        n_activity = result[0]
        n_activities.add(n_activity)
    _logger.debug("len(n_activities) = %d.", len(n_activities))

    # Populate Agents.
    select_query_text = """\
SELECT ?nAgent
WHERE {
  ?nAgent a/rdfs:subClassOf* prov:Agent .
}
"""
    select_query_object = rdflib.plugins.sparql.processor.prepareQuery(
        select_query_text, initNs=nsdict
    )
    for result in graph.query(select_query_object):
        assert isinstance(result, rdflib.query.ResultRow)
        assert isinstance(result[0], rdflib.term.IdentifiedNode)
        n_agent = result[0]
        n_agents.add(n_agent)
    _logger.debug("len(n_agents) = %d.", len(n_agents))

    # Populate Collections.
    select_query_text = """\
SELECT ?nCollection
WHERE {
  ?nCollection a/rdfs:subClassOf* prov:Collection .
}
"""
    select_query_object = rdflib.plugins.sparql.processor.prepareQuery(
        select_query_text, initNs=nsdict
    )
    for record in graph.query(select_query_object):
        assert isinstance(record, rdflib.query.ResultRow)
        assert isinstance(record[0], rdflib.term.IdentifiedNode)
        n_collection = record[0]
        n_collections.add(n_collection)
    _logger.debug("len(n_collections) = %d.", len(n_collections))

    # Populate Entities.
    select_query_text = """\
SELECT ?nEntity
WHERE {
  ?nEntity a/rdfs:subClassOf* prov:Entity .
}
"""
    select_query_object = rdflib.plugins.sparql.processor.prepareQuery(
        select_query_text, initNs=nsdict
    )
    for record in graph.query(select_query_object):
        assert isinstance(record, rdflib.query.ResultRow)
        assert isinstance(record[0], rdflib.term.IdentifiedNode)
        n_entity = record[0]
        n_entities.add(n_entity)
    _logger.debug("len(n_entities) = %d.", len(n_entities))

    n_prov_basis_things = n_activities | n_agents | n_entities
    _logger.debug("len(n_prov_basis_things) = %d.", len(n_prov_basis_things))

    # S2.
    # Define the sets of TIME Things.

    # Expand the PROV things to also be TIME things.
    # Infer boundary Instants for time:ProperIntervals.
    expand_prov_activities_with_owl_time(
        graph, NS_KB, use_deterministic_uuids, debug_graph_fh=args.debug_graph
    )

    # "Interval" in variable names within this script is shorthand for
    # time:ProperInterval.
    n_instants: typing.Set[rdflib.term.IdentifiedNode] = set()
    n_intervals: typing.Set[rdflib.term.IdentifiedNode] = set()

    # Some instants are the beginning or end of a time:ProperInterval,
    # and will be rendered differently from other instants that will
    # otherwise be inside intervals.
    # Likewise, prov:Entitys will render similarly with their Generation
    # and Invalidation events.
    n_terminus_instants: typing.Set[rdflib.term.IdentifiedNode] = set()

    for n_subject in graph.subjects(NS_RDF.type, NS_TIME.Instant):
        assert isinstance(n_subject, rdflib.term.IdentifiedNode)
        n_instants.add(n_subject)

    for n_subject in graph.subjects(NS_RDF.type, NS_TIME.ProperInterval):
        assert isinstance(n_subject, rdflib.term.IdentifiedNode)
        n_intervals.add(n_subject)
        for n_predicate in {NS_TIME.hasBeginning, NS_TIME.hasEnd}:
            for n_object in graph.objects(n_subject, n_predicate):
                assert isinstance(n_object, rdflib.term.IdentifiedNode)
                n_terminus_instants.add(n_object)

    for n_instantaneous_event_type in {NS_PROV.Generation, NS_PROV.Invalidation}:
        for n_subject in graph.subjects(NS_RDF.type, n_instantaneous_event_type):
            assert isinstance(n_subject, rdflib.term.IdentifiedNode)
            n_terminus_instants.add(n_subject)

    _logger.debug("len(n_intervals) = %d.", len(n_intervals))
    _logger.debug("len(n_instants) = %d.", len(n_instants))
    _logger.debug("len(n_terminus_instants) = %d.", len(n_terminus_instants))

    # S3.
    # Define dicts to hold 1-to-manies of various string Literals -
    # comments, labels, names, descriptions, and exhibit numbers.  These
    # Literals will be rendered into the Dot label string.
    AnnoMapType = typing.DefaultDict[
        rdflib.term.IdentifiedNode, typing.Set[rdflib.Literal]
    ]
    n_thing_to_l_comments: AnnoMapType = collections.defaultdict(set)
    n_thing_to_l_labels: AnnoMapType = collections.defaultdict(set)
    n_provenance_record_to_l_exhibit_numbers: AnnoMapType = collections.defaultdict(set)
    n_uco_object_to_l_uco_descriptions: AnnoMapType = collections.defaultdict(set)
    n_uco_object_to_l_uco_name: AnnoMapType = collections.defaultdict(set)

    for triple in graph.triples((None, NS_RDFS.comment, None)):
        assert isinstance(triple[0], rdflib.term.IdentifiedNode)
        assert isinstance(triple[2], rdflib.Literal)
        n_thing_to_l_comments[triple[0]].add(triple[2])

    for triple in graph.triples((None, NS_RDFS.label, None)):
        assert isinstance(triple[0], rdflib.term.IdentifiedNode)
        assert isinstance(triple[2], rdflib.Literal)
        n_thing_to_l_labels[triple[0]].add(triple[2])

    for triple in graph.triples((None, NS_CASE_INVESTIGATION.exhibitNumber, None)):
        assert isinstance(triple[0], rdflib.term.IdentifiedNode)
        assert isinstance(triple[2], rdflib.Literal)
        n_provenance_record_to_l_exhibit_numbers[triple[0]].add(triple[2])

    for triple in graph.triples((None, NS_UCO_CORE.description, None)):
        assert isinstance(triple[0], rdflib.term.URIRef)
        assert isinstance(triple[2], rdflib.Literal)
        n_uco_object_to_l_uco_descriptions[triple[0]].add(triple[2])

    for triple in graph.triples((None, NS_UCO_CORE.name, None)):
        assert isinstance(triple[0], rdflib.term.URIRef)
        assert isinstance(triple[2], rdflib.Literal)
        n_uco_object_to_l_uco_name[triple[0]].add(triple[2])

    # S3.1.
    # Stash display data for PROV Things.

    # SPARQL queries are used to find these PROV classes rather than the
    # graph.triples() retrieval pattern, so the star operator can be
    # used to find subclasses without superclasses being asserted (or
    # having been inferred) in the input graph.

    # The nodes and edges dicts need to store information to construct,
    # not constructed objects.  There is a hidden dependency for edges
    # of a parent graph object not available until after some filtering
    # decisions are made.

    # IdentifiedNode -> pydot.Node's kwargs
    n_thing_to_pydot_node_kwargs: typing.Dict[
        rdflib.term.IdentifiedNode, typing.Dict[str, typing.Any]
    ] = dict()

    n_instant_to_tooltips: typing.DefaultDict[
        rdflib.term.IdentifiedNode, typing.Set[str]
    ] = collections.defaultdict(set)

    # IdentifiedNode (edge beginning node) -> IdentifiedNode (edge ending node) -> short predicate -> pydot.Edge's kwargs
    EdgesType = typing.DefaultDict[
        rdflib.term.IdentifiedNode,
        typing.DefaultDict[
            rdflib.term.IdentifiedNode, typing.Dict[str, typing.Dict[str, typing.Any]]
        ],
    ]
    edges: EdgesType = collections.defaultdict(lambda: collections.defaultdict(dict))

    include_activities: bool = False
    include_agents: bool = False
    include_entities: bool = False
    if args.activity_informing or args.agent_delegating or args.entity_deriving:
        if args.activity_informing:
            include_activities = True
        if args.agent_delegating:
            include_agents = True
        if args.entity_deriving:
            include_entities = True
    else:
        include_activities = True
        include_agents = True
        include_entities = True

    wrapper = textwrap.TextWrapper(
        break_long_words=True,
        drop_whitespace=False,
        replace_whitespace=False,
        width=args.wrap_comment,
    )

    # Add some general-purpose subroutines for augmenting Dot node labels.

    def _annotate_comments(
        n_thing: rdflib.term.IdentifiedNode, label_parts: typing.List[str]
    ) -> None:
        """
        Render `rdfs:comment`s.
        """
        if n_thing in n_thing_to_l_comments:
            for l_comment in sorted(n_thing_to_l_comments[n_thing]):
                label_parts.append("\n")
                label_parts.append("\n")
                label_part = "\n".join(wrapper.wrap(str(l_comment)))
                label_parts.append(label_part)

    def _annotate_descriptions(
        n_thing: rdflib.term.IdentifiedNode, label_parts: typing.List[str]
    ) -> None:
        """
        Render `uco-core:description`s.
        """
        if n_thing in n_uco_object_to_l_uco_descriptions:
            for l_uco_description in sorted(
                n_uco_object_to_l_uco_descriptions[n_thing]
            ):
                label_parts.append("\n")
                label_parts.append("\n")
                label_part = "\n".join(wrapper.wrap(str(l_uco_description)))
                label_parts.append(label_part)

    def _annotate_name(
        n_thing: rdflib.term.IdentifiedNode, label_parts: typing.List[str]
    ) -> None:
        """
        Render `uco-core:name`.

        SHACL constraints on UCO will mean there will be only one name.
        """
        if n_thing in n_uco_object_to_l_uco_name:
            label_parts.append("\n")
            for l_uco_name in sorted(n_uco_object_to_l_uco_name[n_thing]):
                label_part = "\n".join(wrapper.wrap(str(l_uco_name)))
                label_parts.append(label_part)

    def _annotate_labels(
        n_thing: rdflib.term.IdentifiedNode, label_parts: typing.List[str]
    ) -> None:
        """
        Render `rdfs:label`s.

        Unlike `rdfs:comment`s and `uco-core:description`s, labels don't have a blank line separating them.  This is just a design choice to keep what might be shorter string annotations together.
        """
        if n_thing in n_thing_to_l_labels:
            label_parts.append("\n")
            for l_label in sorted(n_thing_to_l_labels[n_thing]):
                label_parts.append("\n")
                label_part = "\n".join(wrapper.wrap(str(l_label)))
                label_parts.append(label_part)

    # Render Agents.
    for n_agent in n_agents:
        kwargs = clone_style(prov.constants.PROV_AGENT)
        kwargs["tooltip"] = "ID - " + str(n_agent)

        # Build label.
        dot_label_parts = ["ID - " + qname(graph, n_agent)]
        _annotate_name(n_agent, dot_label_parts)
        _annotate_labels(n_agent, dot_label_parts)
        _annotate_descriptions(n_agent, dot_label_parts)
        _annotate_comments(n_agent, dot_label_parts)
        dot_label = "".join(dot_label_parts)
        kwargs["label"] = dot_label

        # _logger.debug("Agent %r.", n_agent)
        n_thing_to_pydot_node_kwargs[n_agent] = kwargs
    # _logger.debug("n_thing_to_pydot_node_kwargs = %s." % pprint.pformat(n_thing_to_pydot_node_kwargs))

    # Render Entities.
    for n_entity in n_entities:
        if n_entity in n_collections:
            kwargs = clone_style(PROV_COLLECTION)
        else:
            kwargs = clone_style(prov.constants.PROV_ENTITY)
        kwargs["tooltip"] = "ID - " + str(n_entity)

        # Build label.
        dot_label_parts = ["ID - " + qname(graph, n_entity)]
        if n_entity in n_provenance_record_to_l_exhibit_numbers:
            for l_exhibit_number in sorted(
                n_provenance_record_to_l_exhibit_numbers[n_entity]
            ):
                dot_label_parts.append("\n")
                dot_label_parts.append("Exhibit - " + l_exhibit_number.toPython())
        _annotate_name(n_entity, dot_label_parts)
        _annotate_labels(n_entity, dot_label_parts)
        _annotate_descriptions(n_entity, dot_label_parts)
        _annotate_comments(n_entity, dot_label_parts)
        dot_label = "".join(dot_label_parts)
        kwargs["label"] = dot_label

        # _logger.debug("Entity %r.", n_entity)
        n_thing_to_pydot_node_kwargs[n_entity] = kwargs

        # Add to tooltips of associated InstantaneousEvents.
        for n_predicate, template in {
            (NS_PROV.qualifiedGeneration, "Generation of %s"),
            (NS_PROV.qualifiedInvalidation, "Invalidation of %s"),
        }:
            for n_instantaneous_event in graph.objects(n_entity, n_predicate):
                assert isinstance(n_instantaneous_event, rdflib.term.IdentifiedNode)
                n_instant_to_tooltips[n_instantaneous_event].add(template % n_entity)
    # _logger.debug("n_thing_to_pydot_node_kwargs = %s." % pprint.pformat(n_thing_to_pydot_node_kwargs))
    # _logger.debug("n_instant_to_tooltips = %s." % pprint.pformat(n_instant_to_tooltips))

    # Render Activities.
    for n_activity in n_activities:
        kwargs = clone_style(prov.constants.PROV_ACTIVITY)
        kwargs["tooltip"] = "ID - " + str(n_activity)

        # Retrieve start and end times from either their unqualified
        # forms or from the qualified Start/End objects.
        l_start_time: typing.Optional[rdflib.Literal] = None
        l_end_time: typing.Optional[rdflib.Literal] = None
        for l_value in graph.objects(n_activity, NS_PROV.startedAtTime):
            assert isinstance(l_value, rdflib.Literal)
            l_start_time = l_value
        if l_start_time is None:
            for n_start in graph.objects(n_activity, NS_PROV.qualifiedStart):
                for l_value in graph.objects(n_start, NS_PROV.atTime):
                    assert isinstance(l_value, rdflib.Literal)
                    l_start_time = l_value
        for l_value in graph.objects(n_activity, NS_PROV.endedAtTime):
            assert isinstance(l_value, rdflib.Literal)
            l_end_time = l_value
        if l_end_time is None:
            for n_end in graph.objects(n_activity, NS_PROV.qualifiedEnd):
                for l_value in graph.objects(n_end, NS_PROV.atTime):
                    assert isinstance(l_value, rdflib.Literal)
                    l_end_time = l_value

        # Build label.
        dot_label_parts = ["ID - " + qname(graph, n_activity)]
        if l_start_time is not None or l_end_time is not None:
            dot_label_parts.append("\n")
            section_parts = []
            if l_start_time is None:
                section_parts.append("(...")
            else:
                section_parts.append("[%s" % l_start_time)
            if l_end_time is None:
                section_parts.append("...)")
            else:
                section_parts.append("%s]" % l_end_time)
            dot_label_parts.append(", ".join(section_parts))
        _annotate_name(n_activity, dot_label_parts)
        _annotate_labels(n_activity, dot_label_parts)
        _annotate_descriptions(n_activity, dot_label_parts)
        _annotate_comments(n_activity, dot_label_parts)
        dot_label = "".join(dot_label_parts)
        kwargs["label"] = dot_label

        # _logger.debug("Activity %r.", n_activity)
        n_thing_to_pydot_node_kwargs[n_activity] = kwargs

        # Add to tooltips of associated InstantaneousEvents.
        for n_predicate, template in {
            (NS_PROV.qualifiedEnd, "End of %s"),
            (NS_PROV.qualifiedStart, "Start of %s"),
        }:
            for n_instantaneous_event in graph.objects(n_activity, n_predicate):
                assert isinstance(n_instantaneous_event, rdflib.term.IdentifiedNode)
                n_instant_to_tooltips[n_instantaneous_event].add(template % n_activity)
        for n_instantaneous_event in graph.objects(n_activity, NS_PROV.qualifiedUsage):
            assert isinstance(n_instantaneous_event, rdflib.term.IdentifiedNode)
            for n_object in graph.objects(n_instantaneous_event, NS_PROV.entity):
                assert isinstance(n_object, rdflib.term.IdentifiedNode)
                n_instant_to_tooltips[n_instantaneous_event].add(
                    "Usage of %s in %s" % (n_object, n_activity)
                )

    # _logger.debug("n_thing_to_pydot_node_kwargs = %s." % pprint.pformat(n_thing_to_pydot_node_kwargs))
    # _logger.debug("n_instant_to_tooltips = %s." % pprint.pformat(n_instant_to_tooltips))

    def _render_edges(
        select_query_text: str,
        short_edge_label: str,
        kwargs: typing.Dict[str, str],
        supplemental_dict: typing.Optional[EdgesType] = None,
    ) -> None:
        select_query_object = rdflib.plugins.sparql.processor.prepareQuery(
            select_query_text, initNs=nsdict
        )
        for record in graph.query(select_query_object):
            assert isinstance(record, rdflib.query.ResultRow)
            assert isinstance(record[0], rdflib.term.IdentifiedNode)
            assert isinstance(record[1], rdflib.term.IdentifiedNode)
            n_thing_1 = record[0]
            n_thing_2 = record[1]
            edges[n_thing_1][n_thing_2][short_edge_label] = kwargs
            if supplemental_dict is not None:
                supplemental_dict[n_thing_1][n_thing_2][short_edge_label] = kwargs

    if include_agents:
        # Render actedOnBehalfOf.
        select_query_text = """\
SELECT ?nAgent1 ?nAgent2
WHERE {
  ?nAgent1
    prov:actedOnBehalfOf ?nAgent2 ;
    .
}
"""
        kwargs = clone_style(prov.constants.PROV_DELEGATION)
        if args.dash_unqualified:
            kwargs["style"] = "dashed"
        _render_edges(select_query_text, "actedOnBehalfOf", kwargs)
        if args.dash_unqualified:
            # Render actedOnBehalfOf, with stronger line from Delegation.
            select_query_text = """\
SELECT ?nAgent1 ?nAgent2
WHERE {
  ?nAgent1
    prov:qualifiedDelegation ?nDelegation ;
    .
  ?nDelegation
    a prov:Delegation ;
    prov:agent ?nAgent2 ;
    .
}
"""
            kwargs = clone_style(prov.constants.PROV_DELEGATION)
            _render_edges(select_query_text, "actedOnBehalfOf", kwargs)

    if include_entities:
        # Render hadMember.
        select_query_text = """\
SELECT ?nCollection ?nEntity
WHERE {
  ?nCollection
    prov:hadMember ?nEntity ;
    .
}
"""
        kwargs = clone_style(prov.constants.PROV_MEMBERSHIP)
        _render_edges(select_query_text, "hadMember", kwargs)

    if include_activities and include_entities:
        # Render used.
        select_query_text = """\
SELECT ?nActivity ?nEntity
WHERE {
  ?nActivity
    prov:used ?nEntity ;
    .
}
"""
        kwargs = clone_style(prov.constants.PROV_USAGE)
        if args.dash_unqualified:
            kwargs["style"] = "dashed"
        _render_edges(select_query_text, "used", kwargs)
        if args.dash_unqualified:
            # Render used, with stronger line from Usage.
            select_query_text = """\
SELECT ?nActivity ?nEntity
WHERE {
  ?nActivity
    prov:qualifiedUsage ?nUsage ;
    .
  ?nUsage
    a prov:Usage ;
    prov:entity ?nEntity
    .
}
"""
            kwargs = clone_style(prov.constants.PROV_USAGE)
            _render_edges(select_query_text, "used", kwargs)

    if include_activities and include_agents:
        # Render wasAssociatedWith.
        select_query_text = """\
SELECT ?nActivity ?nAgent
WHERE {
  ?nActivity
    prov:wasAssociatedWith ?nAgent ;
    .
}
"""
        kwargs = clone_style(prov.constants.PROV_ASSOCIATION)
        if args.dash_unqualified:
            kwargs["style"] = "dashed"
        _render_edges(select_query_text, "wasAssociatedWith", kwargs)
        if args.dash_unqualified:
            # Render wasAssociatedWith, with stronger line from Association.
            select_query_text = """\
SELECT ?nActivity ?nAgent
WHERE {
  ?nActivity
    prov:qualifiedAssociation ?nAssociation ;
    .
  ?nAssociation
    a prov:Association ;
    prov:agent ?nAgent ;
    .
}
"""
            kwargs = clone_style(prov.constants.PROV_ASSOCIATION)
            _render_edges(select_query_text, "wasAssociatedWith", kwargs)

    if include_agents and include_entities:
        # Render wasAttributedTo.
        select_query_text = """\
SELECT ?nEntity ?nAgent
WHERE {
  ?nEntity
    prov:wasAttributedTo ?nAgent ;
    .
}
"""
        kwargs = clone_style(prov.constants.PROV_ATTRIBUTION)
        if args.dash_unqualified:
            kwargs["style"] = "dashed"
        _render_edges(select_query_text, "wasAttributedTo", kwargs)
        if args.dash_unqualified:
            # Render wasAttributedTo, with stronger line from Attribution.
            select_query_text = """\
SELECT ?nEntity ?nAgent
WHERE {
  ?nEntity
    prov:qualifiedAttribution ?nAttribution ;
    .
  ?nAttribution
    a prov:Attribution ;
    prov:agent ?nAgent ;
    .
}
"""
            kwargs = clone_style(prov.constants.PROV_ATTRIBUTION)
            _render_edges(select_query_text, "wasAttributedTo", kwargs)

    if include_entities:
        # Render wasDerivedFrom.
        select_query_text = """\
SELECT ?nEntity1 ?nEntity2
WHERE {
  ?nEntity1
    prov:wasDerivedFrom ?nEntity2 ;
    .
}
"""
        kwargs = clone_style(prov.constants.PROV_DERIVATION)
        if args.dash_unqualified:
            kwargs["style"] = "dashed"
        _render_edges(select_query_text, "wasDerivedFrom", kwargs)
        # Render wasDerivedFrom, with stronger line from Derivation.
        # Note that though PROV-O allows using prov:hadUsage and
        # prov:hadGeneration on a prov:Derivation, those are not currently
        # used on account of a couple matters.
        # * Some of the new nodes need to be referenced by two subjects. Blank
        #   nodes have been observed by at least one RDF engine to be
        #   repeatedly-defined without a blank-node identifier of the form
        #   "_:foo".  Naming new nodes is possible with a UUID binding
        #   ( c/o https://stackoverflow.com/a/55638001 ), but the UUID used by
        #   at least one RDF engine is UUIDv4 and not configurable (without
        #   swapping an imported library's function definition, which this
        #   project has opted to not do), causing many uninformative changes
        #   in each run on any pre-computed sample data.
        #   - A consistent UUID scheme could probably be implemented using
        #     some SPARQL built-in string-casting and hashing functions, but
        #     this is left for future work.
        # * Generating Usage and Generation nodes at the same time as
        #   Derivation nodes creates a requirement on some links being present
        #   that might not be pertinent to one of the Usage or the Generation.
        #   Hence, generating all qualification nodes at the same time could
        #   generate fewer qualification nodes.
        if args.dash_unqualified:
            select_query_text = """\
SELECT ?nEntity1 ?nEntity2
WHERE {
  ?nEntity1
    prov:qualifiedDerivation ?nDerivation ;
    .
  ?nDerivation
    a prov:Derivation ;
    prov:entity ?nEntity2 ;
    .
}
"""
            kwargs = clone_style(prov.constants.PROV_DERIVATION)
            _render_edges(select_query_text, "wasDerivedFrom", kwargs)

    if include_activities and include_entities:
        # Render wasGeneratedBy.
        select_query_text = """\
SELECT ?nEntity ?nActivity
WHERE {
  ?nEntity (prov:wasGeneratedBy|^prov:generated) ?nActivity .
}
"""
        kwargs = clone_style(prov.constants.PROV_GENERATION)
        if args.dash_unqualified:
            kwargs["style"] = "dashed"
        _render_edges(select_query_text, "wasGeneratedBy", kwargs)
        if args.dash_unqualified:
            # Render wasGeneratedBy, with stronger line from Generation.
            select_query_text = """\
SELECT ?nEntity ?nActivity
WHERE {
  ?nEntity
    prov:qualifiedGeneration ?nGeneration ;
    .
  ?nGeneration
    a prov:Generation ;
    prov:activity ?nActivity
    .
}
"""
            kwargs = clone_style(prov.constants.PROV_GENERATION)
            _render_edges(select_query_text, "wasGeneratedBy", kwargs)

    if include_activities:
        # Render wasInformedBy.
        select_query_text = """\
SELECT ?nActivity1 ?nActivity2
WHERE {
  ?nActivity1
    prov:wasInformedBy ?nActivity2 ;
    .
}
"""
        kwargs = clone_style(prov.constants.PROV_COMMUNICATION)
        if args.dash_unqualified:
            kwargs["style"] = "dashed"
        _render_edges(select_query_text, "wasInformedBy", kwargs)
        if args.dash_unqualified:
            # Render wasInformedBy, with stronger line from Communication.
            select_query_text = """\
SELECT ?nActivity1 ?nActivity2
WHERE {
  ?nActivity1
    prov:qualifiedCommunication ?nCommunication ;
    .
  ?nCommunication
    a prov:Communication ;
    prov:activity ?nActivity2
    .
}
"""
            kwargs = clone_style(prov.constants.PROV_COMMUNICATION)
            _render_edges(select_query_text, "wasInformedBy", kwargs)

    _logger.debug(
        "len(n_thing_to_pydot_node_kwargs) = %d.", len(n_thing_to_pydot_node_kwargs)
    )
    _logger.debug("len(edges) = %d.", len(edges))

    # S3.2.
    # Stash display data for TIME Things.

    # The set time_edge_node_pairs stores ordered pairs of
    # `time:TemporalEntity`s that precede each other in logical sequence.
    # I.e. (X,Y) being in the set means X sequentiallyPrecedes Y.  Here
    # is how Instants and Intervals work with sequentiallyPrecedes:
    # * An Instant sequentiallyPrecedes all Instants inside an Interval
    #   after the Interval's beginning Instant.
    # * All Instants inside an interval before the Interval's ending
    #   Instant sequentiallyPrecede an Instant.
    # * An Interval X sequentiallyPrecedes an Interval Y if and only if
    #   one of the "Allen algebra" relations Before(X,Y), Meets(X,Y),
    #   After(Y,X), or MetBy(Y,X) are true.
    # This definition is similar to `time:before`, except for the
    # boundary condition: Before(T_1,T_2) states "the end of T_1 is
    # before the beginning of T_2".  SequentiallyPrecedes(T_1,T_2) (with
    # T_1 and Instant, T_2 an Interval) lets T_1 potentially be equal to
    # the beginning of T_2.
    time_edge_node_pairs: typing.Set[
        typing.Tuple[rdflib.term.IdentifiedNode, rdflib.term.IdentifiedNode]
    ] = set()

    # These variables are "subscripted" i and j in keeping with Figure 2
    # on the OWL-Time documentation page:
    # https://www.w3.org/TR/2022/CRD-owl-time-20221115/#fig-thirteen-elementary-possible-relations-between-time-periods-af-97
    # The further "subscripts" b and e are interval beginnings and
    # endings.
    n_instant_i_b: typing.Optional[rdflib.term.IdentifiedNode]
    n_instant_i_e: typing.Optional[rdflib.term.IdentifiedNode]
    n_instant_j_b: typing.Optional[rdflib.term.IdentifiedNode]
    n_instant_j_e: typing.Optional[rdflib.term.IdentifiedNode]
    n_interval_i: rdflib.term.IdentifiedNode
    n_interval_j: rdflib.term.IdentifiedNode

    # Sequence all Intervals with their boundary Instants.
    for n_interval in n_intervals:
        for n_object in graph.objects(n_interval, NS_TIME.hasBeginning):
            assert isinstance(n_object, rdflib.term.IdentifiedNode)
            time_edge_node_pairs.add((n_object, n_interval))
        for n_object in graph.objects(n_interval, NS_TIME.hasEnd):
            assert isinstance(n_object, rdflib.term.IdentifiedNode)
            time_edge_node_pairs.add((n_interval, n_object))

    # Add tooltips for instants of intervals that aren't PROV
    # Activities.  (These tooltips are already kind-of provided by an
    # above loop for Activities.)
    for n_interval in n_intervals - n_activities:
        # Add to tooltips of associated Instants.
        for n_predicate, template in {
            (NS_TIME.hasBeginning, "Beginning of %s"),
            (NS_TIME.hasEnd, "End of %s"),
        }:
            for n_instant in graph.objects(n_interval, n_predicate):
                assert isinstance(n_instant, rdflib.term.IdentifiedNode)
                n_instant_to_tooltips[n_instant].add(template % n_interval)
    # _logger.debug("n_instant_to_tooltips = %s." % pprint.pformat(n_instant_to_tooltips))
    for triple in graph.triples((None, NS_EPHEMERAL.witnesses, None)):
        assert isinstance(triple[0], rdflib.term.IdentifiedNode)
        assert isinstance(triple[2], rdflib.term.IdentifiedNode)
        n_witness = triple[0]
        n_terminus_instant = triple[2]
        for n_subject in graph.subjects(NS_TIME.inside, n_witness):
            n_instant_to_tooltips[n_witness].add(
                "Instant in %s known to follow %s." % (n_subject, n_terminus_instant)
            )

    # Loop through the thirteen Allen Algebra relations.  Using
    # relationship-inverses, they break down into seven logic blocks.

    for n_interval_i, n_interval_j in linked_temporal_entities(
        graph, NS_TIME.intervalBefore, NS_TIME.intervalAfter
    ):
        n_instant_i_bs = get_beginnings(graph, n_interval_i)
        n_instant_i_es = get_ends(graph, n_interval_i)
        n_instant_j_bs = get_beginnings(graph, n_interval_j)
        n_instant_j_es = get_ends(graph, n_interval_j)
        for n_instant_i_b in n_instant_i_bs:
            time_edge_node_pairs.add((n_instant_i_b, n_interval_i))
        for n_instant_i_e in n_instant_i_es:
            time_edge_node_pairs.add((n_interval_i, n_instant_i_e))
        for n_instant_j_b in n_instant_j_bs:
            time_edge_node_pairs.add((n_instant_j_b, n_interval_j))
        for n_instant_j_e in n_instant_j_es:
            time_edge_node_pairs.add((n_interval_j, n_instant_j_e))
        for n_instant_i_e in n_instant_i_es:
            for n_instant_j_b in n_instant_j_bs:
                time_edge_node_pairs.add((n_instant_i_e, n_instant_j_b))

    for n_interval_i, n_interval_j in linked_temporal_entities(
        graph, NS_TIME.intervalMeets, NS_TIME.intervalMetBy
    ):
        n_instant_i_bs = get_beginnings(graph, n_interval_i)
        n_instant_i_es = get_ends(graph, n_interval_i)
        n_instant_j_bs = get_beginnings(graph, n_interval_j)
        n_instant_j_es = get_ends(graph, n_interval_j)
        for n_instant_i_b in n_instant_i_bs:
            time_edge_node_pairs.add((n_instant_i_b, n_interval_i))
        for n_instant_j_e in n_instant_j_es:
            time_edge_node_pairs.add((n_interval_j, n_instant_j_e))
        for n_instant_joint in n_instant_i_es | n_instant_j_bs:
            time_edge_node_pairs.add((n_interval_i, n_instant_joint))
            time_edge_node_pairs.add((n_instant_joint, n_interval_j))

    for n_interval_i, n_interval_j in linked_temporal_entities(
        graph, NS_TIME.intervalOverlaps, NS_TIME.intervalOverlappedBy
    ):
        n_instant_i_bs = get_beginnings(graph, n_interval_i)
        n_instant_i_es = get_ends(graph, n_interval_i)
        n_instant_j_bs = get_beginnings(graph, n_interval_j)
        n_instant_j_es = get_ends(graph, n_interval_j)
        for n_instant_i_b in n_instant_i_bs:
            time_edge_node_pairs.add((n_instant_i_b, n_interval_i))
        for n_instant_i_e in n_instant_i_es:
            time_edge_node_pairs.add((n_interval_i, n_instant_i_e))
        for n_instant_j_b in n_instant_j_bs:
            time_edge_node_pairs.add((n_instant_j_b, n_interval_j))
        for n_instant_j_e in n_instant_j_es:
            time_edge_node_pairs.add((n_interval_j, n_instant_j_e))
        for n_instant_j_b in n_instant_j_bs:
            for n_instant_i_e in n_instant_i_es:
                time_edge_node_pairs.add((n_instant_j_b, n_instant_i_e))

    for n_interval_i, n_interval_j in linked_temporal_entities(
        graph, NS_TIME.intervalStarts, NS_TIME.intervalStartedBy
    ):
        n_instant_i_bs = get_beginnings(graph, n_interval_i)
        n_instant_i_es = get_ends(graph, n_interval_i)
        n_instant_j_bs = get_beginnings(graph, n_interval_j)
        n_instant_j_es = get_ends(graph, n_interval_j)
        for n_instant_joint in n_instant_i_bs | n_instant_j_bs:
            time_edge_node_pairs.add((n_instant_joint, n_interval_i))
            time_edge_node_pairs.add((n_instant_joint, n_interval_j))
        for n_instant_i_e in n_instant_i_es:
            time_edge_node_pairs.add((n_interval_i, n_instant_i_e))
        for n_instant_j_e in n_instant_j_es:
            time_edge_node_pairs.add((n_interval_j, n_instant_j_e))
        for n_instant_i_e in n_instant_i_es:
            for n_instant_j_e in n_instant_j_es:
                time_edge_node_pairs.add((n_instant_i_e, n_instant_j_e))

    for n_interval_i, n_interval_j in linked_temporal_entities(
        graph, NS_TIME.intervalDuring, NS_TIME.intervalContains
    ):
        n_instant_i_bs = get_beginnings(graph, n_interval_i)
        n_instant_i_es = get_ends(graph, n_interval_i)
        n_instant_j_bs = get_beginnings(graph, n_interval_j)
        n_instant_j_es = get_ends(graph, n_interval_j)
        for n_instant_i_b in n_instant_i_bs:
            time_edge_node_pairs.add((n_instant_i_b, n_interval_i))
        for n_instant_i_e in n_instant_i_es:
            time_edge_node_pairs.add((n_interval_i, n_instant_i_e))
        for n_instant_j_b in n_instant_j_bs:
            time_edge_node_pairs.add((n_instant_j_b, n_interval_j))
        for n_instant_j_e in n_instant_j_es:
            time_edge_node_pairs.add((n_interval_j, n_instant_j_e))
        for n_instant_j_b in n_instant_j_bs:
            for n_instant_i_b in n_instant_i_bs:
                time_edge_node_pairs.add((n_instant_j_b, n_instant_i_b))
        for n_instant_i_e in n_instant_i_es:
            for n_instant_j_e in n_instant_j_es:
                time_edge_node_pairs.add((n_instant_i_e, n_instant_j_e))

    for n_interval_i, n_interval_j in linked_temporal_entities(
        graph, NS_TIME.intervalFinishes, NS_TIME.intervalFinishedBy
    ):
        n_instant_i_bs = get_beginnings(graph, n_interval_i)
        n_instant_i_es = get_ends(graph, n_interval_i)
        n_instant_j_bs = get_beginnings(graph, n_interval_j)
        n_instant_j_es = get_ends(graph, n_interval_j)
        for n_instant_i_b in n_instant_i_bs:
            time_edge_node_pairs.add((n_instant_i_b, n_interval_i))
        for n_instant_j_b in n_instant_j_bs:
            time_edge_node_pairs.add((n_instant_j_b, n_interval_j))
        for n_instant_joint in n_instant_i_es | n_instant_j_es:
            time_edge_node_pairs.add((n_interval_i, n_instant_joint))
            time_edge_node_pairs.add((n_interval_j, n_instant_joint))
        for n_instant_j_b in n_instant_j_bs:
            for n_instant_i_b in n_instant_i_bs:
                time_edge_node_pairs.add((n_instant_j_b, n_instant_i_b))

    for n_interval_i, n_interval_j in linked_temporal_entities(
        graph, NS_TIME.intervalEquals
    ):
        n_instant_i_bs = get_beginnings(graph, n_interval_i)
        n_instant_i_es = get_ends(graph, n_interval_i)
        n_instant_j_bs = get_beginnings(graph, n_interval_j)
        n_instant_j_es = get_ends(graph, n_interval_j)
        for n_instant_joint in n_instant_i_bs | n_instant_j_bs:
            time_edge_node_pairs.add((n_instant_joint, n_interval_i))
            time_edge_node_pairs.add((n_instant_joint, n_interval_j))
        for n_instant_joint in n_instant_i_es | n_instant_j_es:
            time_edge_node_pairs.add((n_interval_i, n_instant_joint))
            time_edge_node_pairs.add((n_interval_j, n_instant_joint))

    # Consider PROV Entities to have a temporal sequencing related to
    # their Generation and Invalidation events.
    # Entities' Usages can also be related to their Generation and
    # Invalidation events.

    for triple in graph.triples((None, NS_PROV.qualifiedGeneration, None)):
        assert isinstance(triple[0], rdflib.URIRef)
        assert isinstance(triple[2], rdflib.term.IdentifiedNode)
        n_entity = triple[0]
        n_generation = triple[2]
        time_edge_node_pairs.add((n_generation, n_entity))
        for n_object in graph.objects(n_entity, NS_PROV.qualifiedUsage):
            assert isinstance(n_object, rdflib.term.IdentifiedNode)
            n_usage = n_object
            time_edge_node_pairs.add((n_generation, n_usage))

    for triple in graph.triples((None, NS_PROV.qualifiedInvalidation, None)):
        assert isinstance(triple[0], rdflib.URIRef)
        assert isinstance(triple[2], rdflib.term.IdentifiedNode)
        n_entity = triple[0]
        n_invalidation = triple[2]
        time_edge_node_pairs.add((n_entity, n_invalidation))
        for n_object in graph.objects(n_entity, NS_PROV.qualifiedUsage):
            assert isinstance(n_object, rdflib.term.IdentifiedNode)
            n_usage = n_object
            time_edge_node_pairs.add((n_usage, n_invalidation))

    # time:inside relates Intervals to Instants within them.  Note that
    # even though an Instant inside an Interval is defined in TIME as
    # 'intended to include beginnings and ends of intervals,' we can
    # infer a discrete order between the Interval's starting and ending
    # Instants and the Instant inside the interval, if the Interval is
    # also a PROV Activity:
    #
    # * The definition of `prov:Start` includes "Any usage, generation,
    #   or invalidation involving an activity follows the activity's
    #   start."  (And likewise for `prov:End`: those
    #   `prov:InstantaneousEvent`s precede the `prov:End` Instant.)
    # * A `time:Instant` asserted to be inside this `prov:Activity` is
    #   consistent with the `prov:Activity` being aligned with
    #   `time:ProperInterval` (as opposed to `time:Interval`s that can
    #   be 0-length).
    for triple in graph.triples((None, NS_TIME.inside, None)):
        assert isinstance(triple[0], rdflib.term.IdentifiedNode)
        assert isinstance(triple[2], rdflib.term.IdentifiedNode)
        n_interval = triple[0]
        if n_interval not in n_activities:
            continue
        n_interval_bs = get_beginnings(graph, n_interval)
        n_interval_es = get_ends(graph, n_interval)

        n_instant = triple[2]

        for n_interval_b in n_interval_bs:
            time_edge_node_pairs.add((n_interval_b, n_instant))
            time_edge_node_pairs.add((n_interval_b, n_interval))
        for n_interval_e in n_interval_es:
            time_edge_node_pairs.add((n_instant, n_interval_e))
            time_edge_node_pairs.add((n_interval, n_interval_e))

    # Sequence time:before and time:after, which will mean handling the
    # mixes of `time:Instant`s and `time:Interval`s.
    # _logger.debug(
    #     "len(_linked_temporal_entities(NS_TIME.before, NS_TIME.after)) = %d.",
    #     len(_linked_temporal_entities(NS_TIME.before, NS_TIME.after)),
    # )
    for n_entity_i, n_entity_j in linked_temporal_entities(
        graph, NS_TIME.before, NS_TIME.after
    ):
        n_type_i: rdflib.URIRef
        n_type_j: rdflib.URIRef

        if (n_entity_i, NS_RDF.type, NS_TIME.Instant) in graph:
            n_type_i = NS_TIME.Instant
        elif (n_entity_i, NS_RDF.type, NS_TIME.ProperInterval) in graph:
            n_type_i = NS_TIME.ProperInterval
        else:
            continue

        if (n_entity_j, NS_RDF.type, NS_TIME.Instant) in graph:
            n_type_j = NS_TIME.Instant
        elif (n_entity_j, NS_RDF.type, NS_TIME.ProperInterval) in graph:
            n_type_j = NS_TIME.ProperInterval
        else:
            continue

        if n_type_i == NS_TIME.Instant and n_type_j == NS_TIME.Instant:
            time_edge_node_pairs.add((n_entity_i, n_entity_j))
        elif n_type_i == NS_TIME.Instant and n_type_j == NS_TIME.ProperInterval:
            n_instant = n_entity_i
            n_interval = n_entity_j
            n_interval_bs = get_beginnings(graph, n_interval)
            for n_interval_b in n_interval_bs:
                time_edge_node_pairs.add((n_instant, n_interval_b))
                time_edge_node_pairs.add((n_interval_b, n_interval))
        elif n_type_i == NS_TIME.ProperInterval and n_type_j == NS_TIME.Instant:
            n_instant = n_entity_j
            n_interval = n_entity_i
            n_interval_es = get_ends(graph, n_interval)
            for n_interval_e in n_interval_es:
                time_edge_node_pairs.add((n_interval_e, n_instant))
                time_edge_node_pairs.add((n_interval, n_interval_e))
        elif n_type_i == NS_TIME.ProperInterval and n_type_j == NS_TIME.ProperInterval:
            n_instant_i_bs = get_beginnings(graph, n_entity_i)
            n_instant_i_es = get_ends(graph, n_entity_i)
            n_instant_j_bs = get_beginnings(graph, n_entity_j)
            n_instant_j_es = get_ends(graph, n_entity_j)
            for n_instant_i_b in n_instant_i_bs:
                time_edge_node_pairs.add((n_instant_i_b, n_entity_i))
            for n_instant_i_e in n_instant_i_es:
                time_edge_node_pairs.add((n_entity_i, n_instant_i_e))
            for n_instant_j_b in n_instant_j_bs:
                time_edge_node_pairs.add((n_instant_j_b, n_entity_j))
            for n_instant_j_e in n_instant_j_es:
                time_edge_node_pairs.add((n_entity_j, n_instant_j_e))
            for n_instant_i_e in n_instant_i_es:
                for n_instant_j_b in n_instant_j_bs:
                    time_edge_node_pairs.add((n_instant_i_e, n_instant_j_b))
        else:
            _logger.info("n_type_i = %s.", n_type_i)
            _logger.info("n_type_j = %s.", n_type_j)
            raise NotImplementedError("Unimplemented combination of node types.")

    for triple in graph.triples((None, NS_EPHEMERAL.witnesses, None)):
        assert isinstance(triple[0], rdflib.term.IdentifiedNode)
        assert isinstance(triple[2], rdflib.term.IdentifiedNode)
        n_witness = triple[0]
        n_terminus_instant = triple[2]
        time_edge_node_pairs.add((n_terminus_instant, n_witness))

    # S4.
    # Build the sets of Things to include in the display.
    # Each of these sets will be built up, rather than started maximally
    # and reduced down.
    # If no filtering is requested, all PROV and TIME Things are
    # included.
    # If any filtering is requested, the set of Things to display is
    # reduced from the universe of all PROV things and TIME things.
    # The PROV things are reduced by:
    # - The union of the chains of communication, delegation, and
    #   derivation, referred to as "the chain of influence" in this script;
    # - Intersected with the chain of all histories of the requested set
    #   of terminal Things, referred to as "the chain of ancestry" in
    #   this script.
    # The TIME Things are then reduced by ties to the remaining PROV
    # Things.

    n_prov_things_to_display: typing.Set[rdflib.term.IdentifiedNode] = set()
    n_time_things_to_display: typing.Set[rdflib.term.IdentifiedNode] = set()

    reduce_by_prov_chain_of_ancestry: bool = False
    if args.entity_ancestry or args.query_ancestry or args.from_empty_set:
        reduce_by_prov_chain_of_ancestry = True

    reduce_by_prov_chain_of_influence: bool = False
    if args.activity_informing or args.agent_delegating or args.entity_deriving:
        reduce_by_prov_chain_of_influence = True

    n_prov_things_in_chain_of_ancestry: typing.Set[rdflib.term.IdentifiedNode] = set()
    n_prov_things_in_chain_of_influence: typing.Set[rdflib.term.IdentifiedNode] = set()

    # Build chain of specific ancestry.
    if args.from_empty_set:
        n_prov_things_in_chain_of_ancestry.add(NS_PROV.EmptyCollection)
        select_query_actions_text = """\
SELECT ?nDerivingAction
WHERE {
  # Identify action at end of path.
  ?nDerivingAction
    prov:used prov:EmptyCollection ;
    .
}
"""
        select_query_agents_text = """\
SELECT ?nAgent
WHERE {
  # Identify action at end of path.
  ?nDerivingAction
    prov:used prov:EmptyCollection ;
    .

  # Get each agent involved in the chain.
  ?nDerivingAction prov:wasAssociatedWith ?nAssociatedAgent .
  ?nAssociatedAgent prov:actedOnBehalfOf* ?nAgent .

}
"""
        select_query_entities_text = """\
SELECT ?nEntity
WHERE {
  # Identify all entities in chain.
  ?nEntity prov:wasDerivedFrom prov:EmptyCollection .
}
"""
        for select_query_label, select_query_text in [
            ("activities", select_query_actions_text),
            ("agents", select_query_agents_text),
            ("entities", select_query_entities_text),
        ]:
            _logger.debug("Running %s filtering query.", select_query_label)
            select_query_object = rdflib.plugins.sparql.processor.prepareQuery(
                select_query_text, initNs=nsdict
            )
            for record in graph.query(select_query_object):
                assert isinstance(record, rdflib.query.ResultRow)
                assert isinstance(record[0], rdflib.term.IdentifiedNode)
                n_include = record[0]
                n_prov_things_in_chain_of_ancestry.add(n_include)
            _logger.debug(
                "len(n_prov_things_in_chain_of_ancestry) = %d.",
                len(n_prov_things_in_chain_of_ancestry),
            )
    elif args.entity_ancestry or args.query_ancestry:
        n_terminal_things: typing.Set[rdflib.term.IdentifiedNode] = set()
        if args.entity_ancestry:
            n_prov_things_in_chain_of_ancestry.add(rdflib.URIRef(args.entity_ancestry))
            n_terminal_things.add(rdflib.URIRef(args.entity_ancestry))
        elif args.query_ancestry:
            query_ancestry_text: typing.Optional[str] = None
            with open(args.query_ancestry, "r") as in_fh:
                query_ancestry_text = in_fh.read(2**22)  # 4KiB
            assert query_ancestry_text is not None
            _logger.debug("query_ancestry_text = %r.", query_ancestry_text)
            query_ancestry_object = rdflib.plugins.sparql.processor.prepareQuery(
                query_ancestry_text, initNs=nsdict
            )
            for result in graph.query(query_ancestry_object):
                assert isinstance(result, rdflib.query.ResultRow)
                for result_member in result:
                    if not isinstance(result_member, rdflib.URIRef):
                        raise ValueError(
                            "Query in file %r must return URIRefs."
                            % args.query_ancestry
                        )
                    n_terminal_things.add(result_member)
        _logger.debug(
            "len(n_prov_things_in_chain_of_ancestry) = %d.",
            len(n_prov_things_in_chain_of_ancestry),
        )
        _logger.debug("len(n_terminal_things) = %d.", len(n_terminal_things))

        select_query_actions_text = """\
SELECT ?nDerivingAction
WHERE {
  # Identify action at end of path.
  ?nTerminalThing
    prov:wasGeneratedBy ?nEndAction ;
    .

  # Identify all actions in chain.
  ?nEndAction prov:wasInformedBy* ?nDerivingAction .
}
"""
        select_query_agents_text = """\
SELECT ?nAgent
WHERE {
  # Identify action at end of path.
  ?nTerminalThing
    prov:wasGeneratedBy ?nEndAction ;
    .

  # Identify all actions in chain.
  ?nEndAction prov:wasInformedBy* ?nDerivingAction .

  # Get each agent involved in the chain.
  ?nDerivingAction prov:wasAssociatedWith ?nAssociatedAgent .
  ?nAssociatedAgent prov:actedOnBehalfOf* ?nAgent .

}
"""
        select_query_entities_text = """\
SELECT ?nPrecedingEntity
WHERE {
  # Identify all objects in chain.
  ?nTerminalThing prov:wasDerivedFrom* ?nPrecedingEntity .
}
"""
        for select_query_label, select_query_text in [
            ("activities", select_query_actions_text),
            ("agents", select_query_agents_text),
            ("entities", select_query_entities_text),
        ]:
            _logger.debug("Running %s filtering query.", select_query_label)
            select_query_object = rdflib.plugins.sparql.processor.prepareQuery(
                select_query_text, initNs=nsdict
            )

            for n_terminal_thing in n_terminal_things:
                for record in graph.query(
                    select_query_object,
                    initBindings={"nTerminalThing": n_terminal_thing},
                ):
                    assert isinstance(record, rdflib.query.ResultRow)
                    assert isinstance(record[0], rdflib.term.IdentifiedNode)
                    n_include = record[0]
                    n_prov_things_in_chain_of_ancestry.add(n_include)
            _logger.debug(
                "len(n_prov_things_in_chain_of_ancestry) = %d.",
                len(n_prov_things_in_chain_of_ancestry),
            )
    else:
        # Ancestry reduction is a nop.
        n_prov_things_in_chain_of_ancestry = {x for x in n_prov_basis_things}

    # Build chain of influence.
    # Include Things that are in the PROV base class, but not chained,
    # so they can be displayed as unchained.  In the case of Activities,
    # they might still be temporally sorted, if not chained.
    # This code is brief thanks to relying on PROV edges defined above.
    for n_thing_1 in edges:
        n_prov_things_in_chain_of_influence.add(n_thing_1)
        for n_thing_2 in edges[n_thing_1]:
            n_prov_things_in_chain_of_influence.add(n_thing_2)
        if include_activities:
            n_prov_things_in_chain_of_influence |= n_activities
        if include_agents:
            n_prov_things_in_chain_of_influence |= n_agents
        if include_entities:
            n_prov_things_in_chain_of_influence |= n_entities

    if reduce_by_prov_chain_of_ancestry or reduce_by_prov_chain_of_influence:
        n_prov_things_to_display = (
            n_prov_things_in_chain_of_ancestry & n_prov_things_in_chain_of_influence
        )
    else:
        n_prov_things_to_display = {x for x in n_prov_basis_things}

    if args.omit_empty_set:
        n_prov_things_to_display -= {NS_PROV.EmptyCollection}

    _logger.debug("len(n_prov_things_to_display) = %d.", len(n_prov_things_to_display))
    # _logger.debug(
    #     "n_prov_things_to_display = %s.", pprint.pformat(n_prov_things_to_display)
    # )

    if reduce_by_prov_chain_of_ancestry or reduce_by_prov_chain_of_influence:

        def _add_time_things_of_activity(
            n_activity: rdflib.term.IdentifiedNode,
        ) -> None:
            # _logger.debug("_add_time_things_of_activity(%r)", n_activity)
            for n_predicate in {
                NS_TIME.hasBeginning,
                NS_TIME.hasEnd,
            }:
                for n_instant in graph.objects(n_activity, n_predicate):
                    # _logger.debug("n_instant = %r.", n_instant)
                    assert isinstance(n_instant, rdflib.term.IdentifiedNode)
                    n_time_things_to_display.add(n_instant)
            for n_predicate in {
                NS_PROV.qualifiedEnd,
                NS_PROV.qualifiedStart,
            }:
                for n_entity_influence in graph.objects(n_activity, n_predicate):
                    # _logger.debug("n_entity_influence = %r.", n_entity_influence)
                    assert isinstance(n_entity_influence, rdflib.term.IdentifiedNode)
                    n_time_things_to_display.add(n_entity_influence)
                    for n_entity in graph.objects(n_entity_influence, NS_PROV.entity):
                        # Note - Entity is not added.
                        assert isinstance(n_entity, rdflib.term.IdentifiedNode)
                        _add_time_things_of_entity(n_entity)

        def _add_time_things_of_entity(n_entity: rdflib.term.IdentifiedNode) -> None:
            # _logger.debug("_add_time_things_of_entity(%r)", n_entity)
            for n_predicate in {
                NS_PROV.qualifiedGeneration,
                NS_PROV.qualifiedInvalidation,
                NS_PROV.qualifiedUsage,
            }:
                for n_activity_influence in graph.objects(n_entity, n_predicate):
                    assert isinstance(n_activity_influence, rdflib.term.IdentifiedNode)
                    n_time_things_to_display.add(n_activity_influence)
                    for n_activity in graph.objects(
                        n_activity_influence, NS_PROV.activity
                    ):
                        # Note - Activity is not added.
                        assert isinstance(n_activity, rdflib.term.IdentifiedNode)
                        _add_time_things_of_activity(n_activity)

        if include_activities:
            # _logger.debug(
            #     "len(n_activities & n_prov_things_to_display) = %d.",
            #     len(n_activities & n_prov_things_to_display),
            # )
            for n_activity in n_activities & n_prov_things_to_display:
                n_time_things_to_display.add(n_activity)
                _add_time_things_of_activity(n_activity)

        if include_agents:
            # TODO - No design has been considered yet for timelining
            # delegations.
            pass

        if include_entities:
            for n_entity in n_entities & n_prov_things_to_display:
                n_time_things_to_display.add(n_entity)
                _add_time_things_of_entity(n_entity)

        _logger.debug(
            "len(n_time_things_to_display) = %d.", len(n_time_things_to_display)
        )
        # _logger.debug(
        #     "n_time_things_to_display = %s.", pprint.pformat(n_time_things_to_display)
        # )
    else:
        n_time_things_to_display = n_instants | n_intervals

    # Sort Instants within the things-to-display set by their timestamp
    # value.
    # Include in the sorting the granularity of the timestamp.  An
    # Instant specified to the minute might or might not be before one
    # specified to the same minute with seconds included.
    n_instants_orderer: typing.DefaultDict[
        int,
        typing.DefaultDict[
            str,
            typing.Set[rdflib.term.IdentifiedNode],
        ],
    ] = collections.defaultdict(lambda: collections.defaultdict(set))
    for n_instant in n_instants & n_time_things_to_display:
        for l_datetimestamp in graph.objects(n_instant, NS_TIME.inXSDDateTimeStamp):
            assert isinstance(l_datetimestamp, rdflib.Literal)
            s_datetimestamp = str(l_datetimestamp)
            if s_datetimestamp[-1] == "Z":
                zulu_dts = s_datetimestamp[:-1]
            elif s_datetimestamp[-3] == ":":
                if s_datetimestamp[-5:] == "00:00":
                    zulu_dts = s_datetimestamp[:-6] + "Z"
                else:
                    # TODO: Convert non-GMT timestamps to GMT.
                    continue
            n_instants_orderer[len(zulu_dts)][zulu_dts].add(n_instant)
    # _logger.debug("n_instants_orderer = %s.", pprint.pformat(n_instants_orderer))
    for timestamp_length in sorted(n_instants_orderer.keys()):
        # _logger.debug("  timestamp_length = %d.", timestamp_length)
        n_prior_zulu_dts_instants: typing.Set[rdflib.term.IdentifiedNode] = set()
        for zulu_dts in sorted(n_instants_orderer[timestamp_length]):
            # _logger.debug("    zulu_dts = %s.", zulu_dts)
            # _logger.debug(
            #     "      n_prior_zulu_dts_instants = %r.", n_prior_zulu_dts_instants
            # )
            n_current_zulu_dts_instants = n_instants_orderer[timestamp_length][zulu_dts]
            # _logger.debug(
            #     "      n_current_zulu_dts_instants = %r.", n_current_zulu_dts_instants
            # )
            for n_prior_zulu_dts_instant in n_prior_zulu_dts_instants:
                for n_current_zulu_dts_instant in n_current_zulu_dts_instants:
                    # _logger.debug(
                    #     "        %r -> %r",
                    #     n_prior_zulu_dts_instant,
                    #     n_current_zulu_dts_instant,
                    # )
                    time_edge_node_pairs.add(
                        (n_prior_zulu_dts_instant, n_current_zulu_dts_instant)
                    )
            n_prior_zulu_dts_instants = n_current_zulu_dts_instants

    # S5.
    # Load the Things that will be displayed into a Pydot Graph.

    dot_graph = pydot.Dot("PROV-O render", graph_type="digraph", rankdir="BT")

    # Build the PROV chain's Pydot Nodes and Edges.
    for n_thing in sorted(n_prov_things_to_display):
        kwargs = n_thing_to_pydot_node_kwargs[n_thing]
        dot_node = pydot.Node(iri_to_gv_node_id(n_thing), **kwargs)
        dot_graph.add_node(dot_node)
    for n_thing_1 in sorted(edges.keys()):
        if n_thing_1 not in n_prov_things_to_display:
            continue
        for n_thing_2 in sorted(edges[n_thing_1].keys()):
            if n_thing_2 not in n_prov_things_to_display:
                continue
            for short_edge_label in sorted(edges[n_thing_1][n_thing_2]):
                # short_edge_label is intentionally not used aside from
                # as a selector.  Edge labelling was already handled as
                # the edge kwargs were being constructed.
                node_id_1 = iri_to_gv_node_id(n_thing_1)
                node_id_2 = iri_to_gv_node_id(n_thing_2)
                kwargs = edges[n_thing_1][n_thing_2][short_edge_label]
                dot_edge = pydot.Edge(node_id_1, node_id_2, **kwargs)
                dot_graph.add_edge(dot_edge)

    # Render time:Instants.
    for n_instant in sorted(n_instants & n_time_things_to_display):
        node_id = iri_to_gv_node_id(n_instant)
        # _logger.debug("%r -> %r", n_instant, node_id)
        style = "filled" if args.display_time_links else "invis"
        instant_kwargs = {
            "color": "dimgray",
            "fillcolor": "lightgray",
            "shape": "point",
            "style": style,
        }
        if n_instant in n_instant_to_tooltips:
            instant_kwargs["tooltip"] = " ;\n".join(
                sorted(n_instant_to_tooltips[n_instant])
            )
        else:
            # This will only occur for time:Instants in the input that
            # aren't related to the provenance chains.
            _logger.debug("Instant did not have tooltips: %r.", n_instant)
        dot_node = pydot.Node(
            node_id,
            **instant_kwargs,
        )
        dot_graph.add_node(dot_node)

    display_time_intervals = args.display_time_intervals or args.display_time_links

    # Render time:ProperIntervals that are not prov:Activities.
    for n_interval in sorted((n_intervals - n_activities) & n_time_things_to_display):
        # Build label.
        dot_label_parts = ["ID - " + qname(graph, n_interval), "\n"]
        _annotate_name(n_interval, dot_label_parts)
        _annotate_labels(n_interval, dot_label_parts)
        _annotate_descriptions(n_interval, dot_label_parts)
        _annotate_comments(n_interval, dot_label_parts)
        dot_label = "".join(dot_label_parts)

        style = "dotted" if display_time_intervals else "invis"
        dot_node = pydot.Node(
            iri_to_gv_node_id(n_interval),
            color="dimgray",
            fillcolor="lightgray",
            label=dot_label,
            shape="box",
            style=style,
            tooltip="ID - " + str(n_interval),
        )
        dot_graph.add_node(dot_node)

    # Use union of PROV and TIME things to display to determine which
    # strictly-temporal edges will be rendered.  This covers cases where
    # e.g. a PROV Entity is display-sequenced after its Generation event.
    n_things_to_display = n_prov_things_to_display | n_time_things_to_display

    n_time_boundable_things = (n_intervals | n_entities) & n_things_to_display

    # _logger.debug("len(time_edge_node_pairs) = %d.", len(time_edge_node_pairs))
    # _logger.debug("time_edge_node_pairs = %s.", pprint.pformat(time_edge_node_pairs))
    for time_edge_node_pair in sorted(time_edge_node_pairs):
        if time_edge_node_pair[0] not in n_things_to_display:
            continue
        if time_edge_node_pair[1] not in n_things_to_display:
            continue
        node_id_1 = iri_to_gv_node_id(time_edge_node_pair[0])
        node_id_2 = iri_to_gv_node_id(time_edge_node_pair[1])
        style = "dotted" if args.display_time_links else "invis"
        relator_kwargs = {
            "color": "dimgray",
            "style": style,
        }
        if time_edge_node_pair[0] in n_terminus_instants:
            if time_edge_node_pair[1] in n_time_boundable_things:
                relator_kwargs["arrowhead"] = "tee"
                relator_kwargs["arrowtail"] = "none"
        if time_edge_node_pair[1] in n_terminus_instants:
            if time_edge_node_pair[0] in n_time_boundable_things:
                relator_kwargs["arrowhead"] = "none"
                relator_kwargs["arrowtail"] = "tee"
                relator_kwargs["dir"] = "back"
        # Edge direction is "backwards" in time, favoring use of the
        # "inverse" Allen relationship.  This is so time will flow
        # downwards with the case_prov_dot chart directionality.  This
        # is in alignment with the PROV-O edges' directions being in
        # direction of dependency (& thus reverse of time flow).
        dot_edge = pydot.Edge(node_id_2, node_id_1, **relator_kwargs)
        dot_graph.add_edge(dot_edge)

    dot_graph.write_raw(args.out_dot)


if __name__ == "__main__":
    main()
