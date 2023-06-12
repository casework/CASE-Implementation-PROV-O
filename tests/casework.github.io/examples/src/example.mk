#!/usr/bin/make -f

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

SHELL := /bin/bash

top_srcdir := $(shell cd ../../../.. ; pwd)

subjectdir_basename := $(shell basename $$PWD)

qc_srcdir := $(top_srcdir)/dependencies/CASE-Examples-QC

example_srcdir := $(qc_srcdir)/dependencies/casework.github.io/examples/$(subjectdir_basename)

rdf_toolkit_jar := $(qc_srcdir)/dependencies/CASE-Examples/dependencies/CASE-develop/dependencies/UCO/lib/rdf-toolkit.jar

subject_json := $(example_srcdir)/$(subjectdir_basename).json

check_shape_files := $(wildcard $(top_srcdir)/case_prov/shapes/*.ttl)

construct_sparql_files := $(wildcard $(top_srcdir)/case_prov/queries/construct-*.sparql)

tests_srcdir := $(top_srcdir)/tests

# Pass "no" to have case_prov_check pass on finding breakages in provenance chains.
# TODO - When provenance issues are resolved, remove this flag.
CASE_PROV_CHECK_STRICT ?=
ifeq ($(CASE_PROV_CHECK_STRICT),no)
case_prov_check_strict_flag := --allow-warnings
else
case_prov_check_strict_flag :=
endif

all: \
  $(subjectdir_basename)-prov-activities.svg \
  $(subjectdir_basename)-prov-all.svg \
  $(subjectdir_basename)-prov-agents.svg \
  $(subjectdir_basename)-prov-entities.svg \
  $(subjectdir_basename)-prov-originals.svg \
  prov-constraints.log

.PHONY: \
  all-prov-time \
  check-prov-constraints \
  check-pytest

%.svg: \
  %.dot
	dot \
	  -o _$@ \
	  -T svg \
	  $<
	mv _$@ $@

$(subjectdir_basename)-prov.ttl: \
  $(subject_json) \
  $(construct_sparql_files) \
  $(tests_srcdir)/.venv.done.log \
  $(top_srcdir)/case_prov/case_prov_rdf.py
	export CASE_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(tests_srcdir)/venv/bin/activate \
	    && case_prov_rdf \
	      --allow-empty-results \
	      --debug \
	      --use-deterministic-uuids \
	      __$@ \
	      $<
	java -jar $(rdf_toolkit_jar) \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

$(subjectdir_basename)-prov-activities.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --activity-informing \
	    --dash-unqualified \
	    --debug \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-activities-agents.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --activity-informing \
	    --agent-delegating \
	    --dash-unqualified \
	    --debug \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-activities-entities.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --activity-informing \
	    --entity-deriving \
	    --dash-unqualified \
	    --debug \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-agents.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --agent-delegating \
	    --dash-unqualified \
	    --debug \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-agents-entities.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --agent-delegating \
	    --entity-deriving \
	    --dash-unqualified \
	    --debug \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-all.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --dash-unqualified \
	    --debug \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-entities.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --dash-unqualified \
	    --debug \
	    --entity-deriving \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-originals.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --dash-unqualified \
	    --debug \
	    --from-empty-set \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-time-activities.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --activity-informing \
	    --dash-unqualified \
	    --debug \
	    --display-time-links \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-time-activities-agents.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --activity-informing \
	    --agent-delegating \
	    --dash-unqualified \
	    --debug \
	    --display-time-links \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-time-activities-entities.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --activity-informing \
	    --entity-deriving \
	    --dash-unqualified \
	    --debug \
	    --display-time-links \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-time-agents.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --agent-delegating \
	    --dash-unqualified \
	    --debug \
	    --display-time-links \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-time-agents-entities.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --agent-delegating \
	    --entity-deriving \
	    --dash-unqualified \
	    --debug \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-time-all.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --dash-unqualified \
	    --debug \
	    --display-time-links \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

$(subjectdir_basename)-prov-time-entities.dot: \
  $(subjectdir_basename)-prov.ttl \
  $(top_srcdir)/case_prov/case_prov_dot.py
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_dot \
	    --dash-unqualified \
	    --debug \
	    --entity-deriving \
	    --display-time-links \
	    --use-deterministic-uuids \
	    _$@ \
	    $<
	mv _$@ $@

all-prov-time: \
  $(subjectdir_basename)-prov-time-activities.svg \
  $(subjectdir_basename)-prov-time-activities-agents.svg \
  $(subjectdir_basename)-prov-time-activities-entities.svg \
  $(subjectdir_basename)-prov-time-all.svg \
  $(subjectdir_basename)-prov-time-agents.svg \
  $(subjectdir_basename)-prov-time-agents-entities.svg \
  $(subjectdir_basename)-prov-time-entities.svg

case_prov_check.ttl: \
  $(check_shape_files) \
  $(top_srcdir)/case_prov/case_prov_check.py \
  $(subjectdir_basename)-prov.ttl
	rm -f _$@
	source $(tests_srcdir)/venv/bin/activate \
	  && case_prov_check \
	    --format turtle \
	    $(case_prov_check_strict_flag) \
	    $(subjectdir_basename)-prov.ttl \
	    > __$@
	java -jar $(rdf_toolkit_jar) \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

check: \
  check-prov-constraints \
  check-pytest

check-prov-constraints: \
  prov-constraints.log
	@test 1 -eq $$(tail -n1 $< | grep 'True' | wc -l) \
	  || (echo "ERROR:example.mk:$(subjectdir_basename):prov-constraints reported a constraint error." >&2 ; exit 1)

check-pytest: \
  case_prov_check.ttl
	test 0 -eq $$(ls test_*.py 2>/dev/null | wc -l) \
	  || ( \
	    source $(tests_srcdir)/venv/bin/activate \
	      && pytest \
	        --log-level=DEBUG \
	  )

clean:
	@rm -f \
	  *.dot \
	  *.svg \
	  *.ttl \
	  prov-constraints.log

prov-constraints.log: \
  $(top_srcdir)/dependencies/prov-check/provcheck/provconstraints.py \
  $(subjectdir_basename)-prov.ttl
	source $(tests_srcdir)/venv/bin/activate \
	  && python3 $(top_srcdir)/dependencies/prov-check/provcheck/provconstraints.py \
	    --debug \
	    $(subjectdir_basename)-prov.ttl \
	    > _$@ \
	    2>&1
	mv _$@ $@
