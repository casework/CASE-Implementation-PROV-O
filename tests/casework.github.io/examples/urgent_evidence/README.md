# Mapping of "Urgent Evidence" narrative to PROV-O

This directory includes some visual displays of the [CASE "Urgent Evidence" narrative](https://caseontology.org/examples/urgent_evidence/) mapped to PROV-O.

The depictions are:
* [All](urgent_evidence-prov-all.svg) - The entire narrative-mapping.
* [Activities](urgent_evidence-prov-activities.svg) - All `prov:Activity`s and their `prov:wasInformedBy` relationships.
* [Entities](urgent_evidence-prov-entities.svg) - All `prov:Entity`s (including `prov:Collection`s) and their `prov:wasDerivedFrom` (and `prov:hadMember`) relationships.
* [Agents](urgent_evidence-prov-agents.svg) - All `prov:Agent`s and their `prov:actedOnBehalfOf` relationships.
* The Activities, Entities, and Agents diagrams can also have pairs enabled:
   - [Activities and Agents](urgent_evidence-prov-activities-agents.svg)
   - [Activities and Entities](urgent_evidence-prov-activities-entities.svg)
   - [Agents and Entities](urgent_evidence-prov-agents-entities.svg)
* [All produced JPEG files](urgent_evidence-prov-all-focus-jpegs.svg) - All files of MIME type `image/jpeg`, as selected by [this query](select-jpegs.sparql).
* [Single extracted file](urgent_evidence-prov-all-focus-extracted-file-uuid-1.svg) - The provenance chain from a single extracted file, a JPEG, back to initial evidence submission.
