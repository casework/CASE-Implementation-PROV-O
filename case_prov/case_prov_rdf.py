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
This script executes CONSTRUCT queries and other data translation, returning a supplemental graph.
"""

__version__ = "0.4.1"

import argparse
import importlib.resources
import logging
import os
import typing
import uuid

import case_utils.inherent_uuid
import cdo_local_uuid
import rdflib.plugins.sparql
from case_utils.namespace import (
    NS_CASE_INVESTIGATION,
    NS_RDF,
    NS_UCO_ACTION,
    NS_UCO_CORE,
    NS_UCO_IDENTITY,
)
from cdo_local_uuid import local_uuid

import case_prov

from . import queries

_logger = logging.getLogger(os.path.basename(__file__))

NS_PROV = rdflib.PROV
NS_TIME = rdflib.TIME

# This script augments the input graph with temporary triples that will
# be serialized into a separate graph.  Some nodes that would be created
# as part of the augmentation (e.g. inferred `prov:InstantaneousEvent`s)
# might already be defined in the input graph as blank nodes.  To avoid
# reliance on `owl:sameAs`, this script does not create extra IRI
# references to attempt to supplant those blank nodes.
# Because this script is not updating the original graph directly (i.e.
# because the updates are written to a separate file), updates based on
# blank nodes will not persist and link correctly, and thus are excluded
# from the augmentations.  Compare this type with
# `case_prov_dot.TmpTriplesType`, where blank nodes are included in
# visualization-rendering logic.
TmpPersistableTriplesType = typing.Set[
    typing.Tuple[
        rdflib.URIRef, rdflib.URIRef, typing.Union[rdflib.URIRef, rdflib.Literal]
    ]
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("--allow-empty-results", action="store_true")
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
        help="Use UUIDs computed using the case_utils.inherent_uuid module.",
    )
    parser.add_argument("out_file")
    parser.add_argument("in_graph", nargs="+")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    cdo_local_uuid.configure()

    in_graph = rdflib.Graph()
    out_graph = rdflib.Graph()

    for in_graph_filename in args.in_graph:
        in_graph.parse(in_graph_filename)

    # Guarantee prov: and minimal CASE and UCO prefixes are in input and output contexts.
    in_graph.namespace_manager.bind("case-investigation", NS_CASE_INVESTIGATION)
    in_graph.namespace_manager.bind("prov", NS_PROV)
    in_graph.namespace_manager.bind("uco-action", NS_UCO_ACTION)
    in_graph.namespace_manager.bind("uco-core", NS_UCO_CORE)
    in_graph.namespace_manager.bind("uco-identity", NS_UCO_IDENTITY)

    # Inherit prefixes defined in input context dictionary.
    nsdict = {k: v for (k, v) in in_graph.namespace_manager.namespaces()}
    for prefix in nsdict:
        out_graph.namespace_manager.bind(prefix, nsdict[prefix])

    # Determine knowledge base prefix for new inherent nodes.
    if args.kb_prefix in nsdict:
        NS_KB = rdflib.Namespace(nsdict[args.kb_prefix])
    elif args.kb_iri in nsdict.values():
        NS_KB = rdflib.Namespace(args.kb_iri)
    else:
        NS_KB = rdflib.Namespace(args.kb_iri)
        out_graph.bind(args.kb_prefix, NS_KB)

    use_deterministic_uuids = args.use_deterministic_uuids is True

    # Resource file loading c/o https://stackoverflow.com/a/20885799
    query_filenames = []
    for resource_filename in importlib.resources.contents(queries):
        if not resource_filename.startswith("construct-"):
            continue
        if not resource_filename.endswith(".sparql"):
            continue
        query_filenames.append(resource_filename)
    assert len(query_filenames) > 0, "Failed to load list of query files."

    n_activity: rdflib.URIRef
    n_agent: rdflib.URIRef
    n_entity: rdflib.URIRef

    # Generate inherent nodes.
    # These graph augmentations are order-independent of the CONSTRUCT
    # queries for the unqualified PROV predicates.
    n_actions: typing.Set[rdflib.URIRef] = set()
    for n_action in in_graph.subjects(
        NS_RDF.type, NS_CASE_INVESTIGATION.InvestigativeAction
    ):
        assert isinstance(n_action, rdflib.URIRef)
        n_actions.add(n_action)
    for n_action in sorted(n_actions):
        if not isinstance(n_action, rdflib.URIRef):
            continue
        action_inherence_uuid = case_utils.inherent_uuid.inherence_uuid(n_action)

        # Generate Starts.
        (n_start, inference_triples) = case_prov.infer_interval_terminus(
            in_graph,
            n_action,
            NS_PROV.qualifiedStart,
            NS_KB,
            use_deterministic_uuids=use_deterministic_uuids,
        )
        if isinstance(n_start, rdflib.URIRef):
            out_graph += inference_triples
            for l_object in in_graph.objects(n_action, NS_UCO_ACTION.startTime):
                assert isinstance(l_object, rdflib.Literal)
                out_graph.add((n_start, NS_PROV.atTime, l_object))

        # Generate Ends, if there's a sign an end should exist.
        if case_prov.interval_end_should_exist(in_graph, n_action):
            (n_end, inference_triples) = case_prov.infer_interval_terminus(
                in_graph,
                n_action,
                NS_PROV.qualifiedEnd,
                NS_KB,
                use_deterministic_uuids=use_deterministic_uuids,
            )
            if isinstance(n_end, rdflib.URIRef):
                out_graph += inference_triples
                for l_object in in_graph.objects(n_action, NS_UCO_ACTION.endTime):
                    assert isinstance(l_object, rdflib.Literal)
                    out_graph.add((n_end, NS_PROV.atTime, l_object))

        # Generate Associations.
        qualified_association_uuid_namespace = uuid.uuid5(
            action_inherence_uuid, str(NS_PROV.qualifiedAssociation)
        )
        for n_agency_predicate in [
            NS_UCO_ACTION.instrument,
            NS_UCO_ACTION.performer,
        ]:
            _n_agents: typing.Set[rdflib.URIRef] = set()
            for _n_agent in in_graph.objects(n_action, n_agency_predicate):
                assert isinstance(_n_agent, rdflib.URIRef)
                _n_agents.add(_n_agent)
            for n_agent in sorted(_n_agents):
                n_association: typing.Optional[rdflib.term.IdentifiedNode] = None
                # See if Association between this Action and Agent
                # exists before trying to create one.
                for n_object in in_graph.objects(
                    n_action, NS_PROV.qualifiedAssociation
                ):
                    assert isinstance(n_object, rdflib.term.IdentifiedNode)
                    for triple in in_graph.triples((n_object, NS_PROV.agent, n_agent)):
                        n_association = n_object
                if n_association is None:
                    if use_deterministic_uuids:
                        association_uuid = str(
                            uuid.uuid5(
                                qualified_association_uuid_namespace, str(n_agent)
                            )
                        )
                    else:
                        association_uuid = local_uuid()
                    n_association = NS_KB["Association-" + association_uuid]
                    out_graph.add(
                        (n_action, NS_PROV.qualifiedAssociation, n_association)
                    )
                    out_graph.add((n_association, NS_RDF.type, NS_PROV.Association))
                    out_graph.add((n_association, NS_PROV.agent, n_agent))

        # Generate Delegations.
        # A uco-action:Action may have at most one performer, and any
        # number of instruments.
        qualified_delegation_uuid_namespace = uuid.uuid5(
            action_inherence_uuid, str(NS_PROV.qualifiedDelegation)
        )
        for n_performer in in_graph.objects(n_action, NS_UCO_ACTION.performer):
            delegation_for_performer_uuid_namespace = uuid.uuid5(
                qualified_delegation_uuid_namespace, str(n_performer)
            )
            for n_instrument in in_graph.objects(n_action, NS_UCO_ACTION.instrument):
                n_delegation: typing.Optional[rdflib.term.IdentifiedNode] = None
                # See if Delegation between this Instrument and Performer
                # exists before trying to create one.
                for n_object in in_graph.objects(
                    n_instrument, NS_PROV.qualifiedDelegation
                ):
                    assert isinstance(n_object, rdflib.term.IdentifiedNode)
                    for triple0 in in_graph.triples(
                        (n_object, NS_PROV.agent, n_performer)
                    ):
                        for triple1 in in_graph.triples(
                            (n_object, NS_PROV.hadActivity, n_action)
                        ):
                            n_delegation = n_object
                if n_delegation is None:
                    if use_deterministic_uuids:
                        delegation_uuid = str(
                            uuid.uuid5(
                                delegation_for_performer_uuid_namespace,
                                str(n_instrument),
                            )
                        )
                    else:
                        delegation_uuid = local_uuid()
                    n_delegation = NS_KB["Delegation-" + delegation_uuid]
                    out_graph.add(
                        (n_instrument, NS_PROV.qualifiedDelegation, n_delegation)
                    )
                    out_graph.add((n_delegation, NS_RDF.type, NS_PROV.Delegation))
                    out_graph.add((n_delegation, NS_PROV.agent, n_performer))
                    out_graph.add((n_delegation, NS_PROV.hadActivity, n_action))

    # Run all entailing CONSTRUCT queries.
    case_entailment_tally = 0
    for query_filename in query_filenames:
        _logger.debug("Running query in %r." % query_filename)
        construct_query_text = importlib.resources.read_text(queries, query_filename)
        construct_query_object = rdflib.plugins.sparql.processor.prepareQuery(
            construct_query_text, initNs=nsdict
        )
        # https://rdfextras.readthedocs.io/en/latest/working_with.html
        construct_query_result = in_graph.query(construct_query_object)
        _logger.debug("len(construct_query_result) = %d." % len(construct_query_result))
        for row_no, row in enumerate(construct_query_result):
            if row_no == 0:
                _logger.debug("row[0] = %r." % (row,))
            case_entailment_tally = row_no + 1
            # TODO: Handle type review with implementation to RDFLib Issue 2283.
            # https://github.com/RDFLib/rdflib/issues/2283
            out_graph.add(row)  # type: ignore

    # Run inherent qualification steps that are dependent on PROV-O
    # properties being present.

    # Use tmp_graph to store the current updated knowledge over
    # in_graph.  tmp_graph is ephemeral and will not be persisted.
    tmp_graph = in_graph + out_graph

    # Store further modifications in tmp_triples, to avoid modifying
    # out_graph while iterating over so-far-updated in_graph and
    # out_graph.  tmp_triples will only be augmenting the output graph
    # with durable references.  So, BNodes are excluded via the type
    # restrictions.
    tmp_triples: TmpPersistableTriplesType = set()

    # Build Attributions.
    # Modeling assumption over PROV-O: An Attribution inheres in both
    # the Entity and Agent.
    for triple in sorted(tmp_graph.triples((None, NS_PROV.wasAttributedTo, None))):
        if not isinstance(triple[0], rdflib.URIRef):
            continue
        if not isinstance(triple[2], rdflib.URIRef):
            continue
        n_entity = triple[0]
        n_agent = triple[2]

        n_attribution: typing.Optional[rdflib.term.IdentifiedNode] = None
        for n_object in in_graph.objects(n_entity, NS_PROV.qualifiedAttribution):
            if (n_object, NS_PROV.agent, n_agent) in in_graph:
                assert isinstance(n_object, rdflib.term.IdentifiedNode)
                n_attribution = n_object
        if n_attribution is not None:
            # No creation necessary.
            continue

        entity_uuid_namespace = case_utils.inherent_uuid.inherence_uuid(n_entity)
        qualifed_attribution_uuid_namespace = uuid.uuid5(
            entity_uuid_namespace, str(NS_PROV.qualifiedAttribution)
        )

        if use_deterministic_uuids:
            attribution_uuid = str(
                uuid.uuid5(qualifed_attribution_uuid_namespace, str(n_agent))
            )
        else:
            attribution_uuid = local_uuid()

        n_attribution = NS_KB["Attribution-" + attribution_uuid]
        tmp_triples.add((n_entity, NS_PROV.qualifiedAttribution, n_attribution))
        tmp_triples.add((n_attribution, NS_RDF.type, NS_PROV.Attribution))
        tmp_triples.add((n_attribution, NS_PROV.agent, n_agent))

    def _pull_inference_triples(inference_triples: case_prov.TmpTriplesType) -> None:
        """
        This subroutine is provided to supplement case_prov.infer_prov_instantaneous_influence_event usage.
        """
        nonlocal tmp_triples
        for inference_triple in inference_triples:
            if not isinstance(inference_triple[0], rdflib.URIRef):
                continue
            assert isinstance(inference_triple[1], rdflib.URIRef)
            if not isinstance(inference_triple[2], rdflib.URIRef):
                continue
            tmp_triples.add(
                (inference_triple[0], inference_triple[1], inference_triple[2])
            )

    # Build Communications.
    # Modeling assumption over PROV-O: A Communication inheres in both
    # the informed Activity and informant Activity.
    for triple in sorted(tmp_graph.triples((None, NS_PROV.wasInformedBy, None))):
        if not isinstance(triple[0], rdflib.URIRef):
            continue
        if not isinstance(triple[2], rdflib.URIRef):
            continue
        n_informed_activity = triple[0]
        n_informant_activity = triple[2]

        (
            n_communication,
            inference_triples,
        ) = case_prov.infer_prov_instantaneous_influence_event(
            tmp_graph,
            n_informed_activity,
            NS_PROV.qualifiedCommunication,
            n_informant_activity,
            NS_KB,
            use_deterministic_uuids=use_deterministic_uuids,
        )

        _pull_inference_triples(inference_triples)

    # Build Derivations.
    # Modeling assumption over PROV-O: A Derivation inheres in both the
    # input Entity and output Entity.
    for triple in sorted(tmp_graph.triples((None, NS_PROV.wasDerivedFrom, None))):
        if not isinstance(triple[0], rdflib.URIRef):
            continue
        if not isinstance(triple[2], rdflib.URIRef):
            continue
        n_action_result = triple[0]
        n_action_object = triple[2]

        (
            n_derivation,
            inference_triples,
        ) = case_prov.infer_prov_instantaneous_influence_event(
            tmp_graph,
            n_action_result,
            NS_PROV.qualifiedDerivation,
            n_action_object,
            NS_KB,
            use_deterministic_uuids=use_deterministic_uuids,
        )

        _pull_inference_triples(inference_triples)
        if isinstance(n_derivation, rdflib.URIRef):
            for n_object in tmp_graph.objects(n_action_result, NS_PROV.wasGeneratedBy):
                if isinstance(n_object, rdflib.URIRef):
                    tmp_triples.add((n_derivation, NS_PROV.hadActivity, n_object))

    # Build Generations.
    # Modeling assumption over PROV-O: A Generation inheres solely in
    # the Entity.
    # Also note that Entities will not be assigned a Generation event,
    # as they don't necessarily have one.  Take for example the idea
    # prov:EmptyCollection, as the mathematical abstraction also known
    # as the empty set.
    for triple in sorted(tmp_graph.triples((None, NS_PROV.wasGeneratedBy, None))):
        if not isinstance(triple[0], rdflib.URIRef):
            continue
        if not isinstance(triple[2], rdflib.URIRef):
            continue
        n_entity = triple[0]
        n_activity = triple[2]

        (
            n_generation,
            inference_triples,
        ) = case_prov.infer_prov_instantaneous_influence_event(
            tmp_graph,
            n_entity,
            NS_PROV.qualifiedGeneration,
            n_activity,
            NS_KB,
            use_deterministic_uuids=use_deterministic_uuids,
        )

        _pull_inference_triples(inference_triples)

    # Build Invalidations.
    # Modeling assumption over PROV-O: An Invalidation inheres solely in
    # the Entity.
    for triple in sorted(tmp_graph.triples((None, NS_PROV.wasInvalidatedBy, None))):
        if not isinstance(triple[0], rdflib.URIRef):
            continue
        if not isinstance(triple[2], rdflib.URIRef):
            continue
        n_entity = triple[0]
        n_activity = triple[2]

        (
            n_invalidation,
            inference_triples,
        ) = case_prov.infer_prov_instantaneous_influence_event(
            tmp_graph,
            n_entity,
            NS_PROV.qualifiedInvalidation,
            n_activity,
            NS_KB,
            use_deterministic_uuids=use_deterministic_uuids,
        )

        _pull_inference_triples(inference_triples)

    # Build Usages.
    # Modeling assumption over PROV-O: A Usage inheres in both the
    # Activity and Entity.
    for triple in sorted(tmp_graph.triples((None, NS_PROV.used, None))):
        if not isinstance(triple[0], rdflib.URIRef):
            continue
        if not isinstance(triple[2], rdflib.URIRef):
            continue
        n_activity = triple[0]
        n_entity = triple[2]

        (
            n_usage,
            inference_triples,
        ) = case_prov.infer_prov_instantaneous_influence_event(
            tmp_graph,
            n_activity,
            NS_PROV.qualifiedUsage,
            n_entity,
            NS_KB,
            use_deterministic_uuids=use_deterministic_uuids,
        )

        _pull_inference_triples(inference_triples)

    for tmp_triple in tmp_triples:
        out_graph.add(tmp_triple)
        tmp_graph.add(tmp_triple)
    prov_existential_entailment_tally = len(tmp_triples)

    # Do TIME-PROV entailments.

    tmp_triples = set()
    time_entailment_tally = 0

    # Some of the entailments require knowledge from the input and
    # output graphs.

    # Entailments will NOT be performed on blank nodes, due to inability
    # to associate the new blank node in the serialized graph with the
    # prior blank node in the input graph without using owl:sameAs.

    # Entail superclasses, which is what RDFS inferencing would devise
    # with these axioms:
    #
    #     prov:Activity
    #         rdfs:subClassOf time:ProperInterval ;
    #         .
    #     prov:InstantaneousEvent
    #         rdfs:subClassOf time:Instant ;
    #         .
    #
    # Entail interval classes first:
    n_activities: typing.Set[rdflib.URIRef] = set()
    n_proper_intervals: typing.Set[rdflib.URIRef] = set()
    for graph in [in_graph, out_graph]:
        for n_subject in graph.subjects(NS_RDF.type, NS_PROV.Activity):
            if isinstance(n_subject, rdflib.URIRef):
                n_activities.add(n_subject)
        for n_subject in graph.subjects(NS_RDF.type, NS_TIME.ProperInterval):
            if isinstance(n_subject, rdflib.URIRef):
                n_proper_intervals.add(n_subject)
    for n_activity in n_activities:
        tmp_triples.add((n_activity, NS_RDF.type, NS_TIME.ProperInterval))
    n_proper_intervals |= n_activities

    # Then entail instant classes:
    n_instants: typing.Set[rdflib.URIRef] = set()
    n_instantaneous_events: typing.Set[rdflib.URIRef] = set()
    for graph in [in_graph, out_graph]:
        for n_prov_instantaneous_event_class in {
            NS_PROV.InstantaneousEvent,
            NS_PROV.End,
            NS_PROV.Generation,
            NS_PROV.Invalidation,
            NS_PROV.Start,
            NS_PROV.Usage,
        }:
            for n_subject in graph.subjects(
                NS_RDF.type, n_prov_instantaneous_event_class
            ):
                if isinstance(n_subject, rdflib.URIRef):
                    n_instantaneous_events.add(n_subject)
        for n_subject in graph.subjects(NS_RDF.type, NS_TIME.Instant):
            if isinstance(n_subject, rdflib.URIRef):
                n_instants.add(n_subject)
    for n_instantaneous_event in n_instantaneous_events:
        tmp_triples.add((n_instantaneous_event, NS_RDF.type, NS_TIME.Instant))
    n_instants |= n_instantaneous_events

    # Entail superproperties, which is what RDFS inference would devise
    # with these axioms:
    #
    #     prov:qualifiedEnd
    #         rdfs:subPropertyOf time:hasEnd ;
    #         .
    #     prov:qualifiedStart
    #         rdfs:subPropertyOf time:hasBeginning ;
    #         .
    #
    for graph in [in_graph, out_graph]:
        for n_activity in n_activities:
            for n_object in graph.objects(n_activity, NS_PROV.qualifiedEnd):
                if isinstance(n_object, rdflib.URIRef):
                    if n_object in n_instants:
                        tmp_triples.add((n_activity, NS_TIME.hasEnd, n_object))
            for n_object in graph.objects(n_activity, NS_PROV.qualifiedStart):
                if isinstance(n_object, rdflib.URIRef):
                    if n_object in n_instants:
                        tmp_triples.add((n_activity, NS_TIME.hasBeginning, n_object))

    # Augment out_graph now - further work is centered on TIME and PROV
    # properties, and might have been inferred in some of the above
    # loops.
    for tmp_triple in tmp_triples:
        out_graph.add(tmp_triple)
        tmp_graph.add(tmp_triple)
    time_entailment_tally += len(tmp_triples)
    tmp_triples = set()

    # Build beginning and ending nodes for all time:ProperIntervals that
    # lack the bounding instants.
    for n_proper_interval in sorted(n_proper_intervals):
        # Generate Ends.
        (n_time_end, end_graph) = case_prov.infer_interval_terminus(
            tmp_graph,
            n_proper_interval,
            NS_TIME.hasEnd,
            NS_KB,
            use_deterministic_uuids=use_deterministic_uuids,
        )
        if isinstance(n_time_end, rdflib.URIRef):
            n_instants.add(n_time_end)
        _pull_inference_triples(end_graph)
        del end_graph

        # Generate Beginnings.
        (n_time_beginning, beginning_graph) = case_prov.infer_interval_terminus(
            tmp_graph,
            n_proper_interval,
            NS_TIME.hasBeginning,
            NS_KB,
            use_deterministic_uuids=use_deterministic_uuids,
        )
        if isinstance(n_time_beginning, rdflib.URIRef):
            n_instants.add(n_time_beginning)
        _pull_inference_triples(beginning_graph)
        del beginning_graph

    # Augment out_graph now - further work is centered on Instants that
    # may have just been created.
    for tmp_triple in tmp_triples:
        out_graph.add(tmp_triple)
    time_entailment_tally += len(tmp_triples)
    tmp_triples = set()

    # Populate time:inXSDDateTimeStamp on all IRI-identified
    # time:Instants, where data are available.
    # All of the inferencing in this script should have led to
    # prov:InstantaneousEvents having the property prov:atTime populated
    # (whether from data encoded in PROV-O, or data encoded in CASE).
    # The TIME entailments now let a review happen using TIME and PROV
    # concepts.
    for n_instant in n_instants:
        if not isinstance(n_instant, rdflib.URIRef):
            continue
        l_datetime: typing.Optional[rdflib.Literal] = None
        l_datetimestamp: typing.Optional[rdflib.Literal] = None
        for graph in [in_graph, out_graph]:
            for l_value in graph.objects(n_instant, NS_TIME.inXSDDateTimeStamp):
                assert isinstance(l_value, rdflib.Literal)
                l_datetimestamp = l_value
            if l_datetimestamp is not None:
                break
            for l_value in graph.objects(n_instant, NS_PROV.atTime):
                assert isinstance(l_value, rdflib.Literal)
                l_datetime = l_value
        if l_datetimestamp is not None:
            continue
        if l_datetime is not None:
            l_datetimestamp = case_prov.xsd_datetime_to_xsd_datetimestamp(l_datetime)
            if l_datetimestamp is not None:
                tmp_triples.add(
                    (
                        n_instant,
                        NS_TIME.inXSDDateTimeStamp,
                        l_datetimestamp,
                    )
                )

    # Augment out_graph for timestamps.
    for tmp_triple in tmp_triples:
        out_graph.add(tmp_triple)
    time_entailment_tally += len(tmp_triples)

    # Add time:insides for the qualified PROV Entity events.
    tmp_triples = set()
    for graph in [in_graph, out_graph]:
        for triple in graph.triples((None, NS_PROV.qualifiedGeneration, None)):
            if not isinstance(triple[0], rdflib.URIRef):
                continue
            if not isinstance(triple[2], rdflib.URIRef):
                continue
            n_entity = triple[0]
            n_generation = triple[2]
            for n_object in graph.objects(n_generation, NS_PROV.activity):
                if not isinstance(n_object, rdflib.URIRef):
                    continue
                n_activity = n_object
                tmp_triples.add((n_activity, NS_TIME.inside, n_generation))
        for triple in graph.triples((None, NS_PROV.qualifiedInvalidation, None)):
            if not isinstance(triple[0], rdflib.URIRef):
                continue
            if not isinstance(triple[2], rdflib.URIRef):
                continue
            n_entity = triple[0]
            n_invalidation = triple[2]
            for n_object in graph.objects(n_invalidation, NS_PROV.activity):
                if not isinstance(n_object, rdflib.URIRef):
                    continue
                n_activity = n_object
                tmp_triples.add((n_activity, NS_TIME.inside, n_invalidation))
        for triple in graph.triples((None, NS_PROV.qualifiedUsage, None)):
            if not isinstance(triple[0], rdflib.URIRef):
                continue
            if not isinstance(triple[2], rdflib.URIRef):
                continue
            n_activity = triple[0]
            n_usage = triple[2]
            tmp_triples.add((n_activity, NS_TIME.inside, n_usage))

    for tmp_triple in tmp_triples:
        out_graph.add(tmp_triple)
        tmp_graph.add(tmp_triple)
    time_entailment_tally += len(tmp_triples)

    # Generally order PROV Generations, Usages, and Invalidations.
    tmp_triples = set()
    tmp_graph = in_graph + out_graph
    for query in [
        """\
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX time: <http://www.w3.org/2006/time#>
CONSTRUCT {
    ?nGeneration time:before ?nUsage .
}
WHERE {
    ?nEntity prov:qualifiedGeneration ?nGeneration .
    ?nActivity prov:qualifiedUsage ?nUsage .
    ?nUsage prov:entity ?nEntity .
}
""",
        """\
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX time: <http://www.w3.org/2006/time#>
CONSTRUCT {
    ?nGeneration time:before ?nInvalidation .
}
WHERE {
    ?nEntity
        prov:qualifiedGeneration ?nGeneration ;
        prov:qualifiedInvalidation ?nInvalidation ;
        .
}
""",
        """\
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX time: <http://www.w3.org/2006/time#>
CONSTRUCT {
    ?nUsage time:before ?nInvalidation .
}
WHERE {
    ?nEntity prov:qualifiedInvalidation ?nInvalidation .
    ?nActivity prov:qualifiedUsage ?nUsage .
    ?nUsage prov:entity ?nEntity .
}
""",
    ]:
        for row in tmp_graph.query(query):
            assert isinstance(row, tuple)
            if not isinstance(row[0], rdflib.URIRef):
                continue
            assert isinstance(row[1], rdflib.URIRef)
            if not isinstance(row[2], rdflib.URIRef):
                continue
            tmp_triples.add((row[0], row[1], row[2]))

    for tmp_triple in tmp_triples:
        out_graph.add(tmp_triple)
    time_entailment_tally += len(tmp_triples)
    del tmp_triples

    if (
        case_entailment_tally == 0
        and prov_existential_entailment_tally == 0
        and time_entailment_tally == 0
    ):
        if not args.allow_empty_results:
            raise ValueError("Failed to construct any results.")

    out_graph.serialize(args.out_file)


if __name__ == "__main__":
    main()
