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
"""

# TODO - The label adjustment with "ID - " is a hack.  A hyphen forces
# pydot to quote the label string.  Colons don't.  Hence, if the label
# string is just alphanumeric characters and colons, the string won't
# get quoted.  This turns out to be a dot syntax error.  Need to report
# this upstream to pydot.

__version__ = "0.4.1"

import argparse
import collections
import copy
import hashlib
import logging
import os
import textwrap
import typing

import prov.constants  # type: ignore
import prov.dot  # type: ignore
import pydot  # type: ignore
import rdflib.plugins.sparql
from case_utils.namespace import NS_CASE_INVESTIGATION, NS_RDFS, NS_UCO_CORE

_logger = logging.getLogger(os.path.basename(__file__))

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


def iri_to_gv_node_id(n_thing: rdflib.term.IdentifiedNode) -> str:
    hasher = hashlib.sha256()
    hasher.update(str(n_thing).encode())
    return "_" + hasher.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--dash-unqualified",
        action="store_true",
        help="Use dash-style edges for graph nodes not also related by qualifying Influences.",
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

    graph = rdflib.Graph()
    for in_graph_filename in args.in_graph:
        graph.parse(in_graph_filename)

    graph.bind("case-investigation", NS_CASE_INVESTIGATION)
    graph.bind("prov", NS_PROV)

    nsdict = {k: v for (k, v) in graph.namespace_manager.namespaces()}

    # Add a few axioms from PROV-O.
    graph.add((NS_PROV.Collection, NS_RDFS.subClassOf, NS_PROV.Entity))
    graph.add((NS_PROV.Person, NS_RDFS.subClassOf, NS_PROV.Agent))
    graph.add((NS_PROV.SoftwareAgent, NS_RDFS.subClassOf, NS_PROV.Agent))

    # The rest of this script follows this flow:
    # S1. Build the sets of PROV Things.
    # S2. Build the ways in which PROV Things that will be displayed
    #     will be displayed [sic.].
    # S3. Build the sets of Things to display.  This is done after
    #     building how-to-display details in S2 in order to reuse query
    #     results from S2.
    # S4. Load the Things that will be displayed into a Pydot Graph.

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
        dot_label_parts = ["ID - " + graph.namespace_manager.qname(n_agent)]
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
        dot_label_parts = ["ID - " + graph.namespace_manager.qname(n_entity)]
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
        dot_label_parts = ["ID - " + graph.namespace_manager.qname(n_activity)]
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

    # S3.
    # Build the sets of Things to include in the display.
    # Each of these sets will be built up, rather than started maximally
    # and reduced down.
    # If no filtering is requested, all PROV Things are included.
    # If any filtering is requested, the set of Things to display is
    # reduced from the universe of all PROV things.  The PROV things are
    # reduced by:
    # - The union of the chains of communication, delegation, and
    #   derivation, referred to as "the chain of influence" in this
    #   script;
    # - Intersected with the chain of all histories of the requested set
    #   of terminal Things, referred to as "the chain of ancestry" in
    #   this script.
    n_prov_things_to_display: typing.Set[rdflib.term.IdentifiedNode] = set()

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
    # so they can be displayed as unchained.
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

    # S4.
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

    # Include any temporal ordering among the filtered nodes as hidden edges to impose ordering.
    # This sorting assumes the non-normative alignment of TIME and PROV-O, available at:
    # https://github.com/w3c/sdw/blob/gh-pages/time/rdf/time-prov.ttl
    invisible_edge_node_pairs: typing.Set[
        typing.Tuple[rdflib.URIRef, rdflib.URIRef]
    ] = set()
    order: str
    for n_predicate, order in {
        (NS_TIME.after, "rtl"),
        (NS_TIME.before, "ltr"),
        (NS_TIME.intervalAfter, "rtl"),
        (NS_TIME.intervalBefore, "ltr"),
    }:
        for triple in graph.triples((None, n_predicate, None)):
            if not isinstance(triple[0], rdflib.URIRef):
                continue
            if not isinstance(triple[2], rdflib.URIRef):
                continue
            if triple[0] not in n_prov_things_to_display:
                continue
            if triple[2] not in n_prov_things_to_display:
                continue

            if order == "ltr":
                invisible_edge_node_pairs.add((triple[0], triple[2]))
            else:
                invisible_edge_node_pairs.add((triple[2], triple[0]))
    _logger.debug(
        "len(invisible_edge_node_pairs) = %d.", len(invisible_edge_node_pairs)
    )
    for invisible_edge_node_pair in invisible_edge_node_pairs:
        node_id_1 = iri_to_gv_node_id(invisible_edge_node_pair[0])
        node_id_2 = iri_to_gv_node_id(invisible_edge_node_pair[1])
        # Edge direction is "backwards" in time, favoring use of the
        # "inverse" Allen relationship.  This is so time will flow
        # downwards with the case_prov_dot chart directionality.  This
        # is in alignment with the PROV-O edges' directions being in
        # direction of dependency (& thus reverse of time flow).
        dot_edge = pydot.Edge(node_id_2, node_id_1, style="invis")
        dot_graph.add_edge(dot_edge)

    dot_graph.write_raw(args.out_dot)


if __name__ == "__main__":
    main()
