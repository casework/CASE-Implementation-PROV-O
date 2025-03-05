#!/usr/bin/make -f

# Portions of this file contributed by NIST are governed by the
# following statement:
#
# This software was developed at the National Institute of Standards
# and Technology by employees of the Federal Government in the course
# of their official duties. Pursuant to Title 17 Section 105 of the
# United States Code, this software is not subject to copyright
# protection within the United States. NIST assumes no responsibility
# whatsoever for its use by other parties, and makes no guarantees,
# expressed or implied, about its quality, reliability, or any other
# characteristic.
#
# We would appreciate acknowledgement if the software is used.

SHELL := /bin/bash

top_srcdir := $(shell cd .. ; pwd)

rdf_toolkit_jar := $(top_srcdir)/dependencies/casework.github.io/dependencies/CASE-develop/dependencies/UCO/lib/rdf-toolkit.jar

all: \
  readme-actions-ordered-by-timestamp-constraints.log \
  readme-actions-ordered-by-timestamp-invisible.svg \
  readme-actions-ordered-by-timestamp-visible.svg \
  readme-activities.svg \
  readme-activities-related-by-intervals-invisible.svg \
  readme-activities-related-by-intervals-with-intervals.svg \
  readme-activities-related-by-intervals-visible.svg \
  readme-activity-vs-proper-interval-visible.svg \
  readme-allen-relations-invisible.svg \
  readme-allen-relations-visible.svg \
  readme-attribution.svg \
  readme-eapi-bounded-visible.svg \
  readme-eapi-default-visible.svg \
  readme-provenance-records.svg \
  readme-time-instants-invisible.svg \
  readme-time-instants-visible.svg \
  readme-two-files-constraints.log \
  readme-two-files-invisible.svg \
  readme-two-files-visible.svg

.PRECIOUS: \
  readme-actions-ordered-by-timestamp-invisible.dot \
  readme-actions-ordered-by-timestamp-visible.dot \
  readme-activities.dot \
  readme-activities-related-by-intervals-invisible.dot \
  readme-activities-related-by-intervals-with-intervals.dot \
  readme-activities-related-by-intervals-visible.dot \
  readme-activity-vs-proper-interval-visible.dot \
  readme-allen-relations-invisible.dot \
  readme-allen-relations-visible.dot \
  readme-attribution.dot \
  readme-eapi-bounded-visible.dot \
  readme-eapi-default-visible.dot \
  readme-provenance-records.dot \
  readme-time-instants-invisible.dot \
  readme-time-instants-visible.dot \
  readme-two-files-invisible.dot \
  readme-two-files-visible.dot

%-constraints.log: \
  %-folded.ttl \
  $(top_srcdir)/dependencies/prov-check/provcheck/provconstraints.py
	source $(top_srcdir)/tests/venv/bin/activate \
	  && python3 $(top_srcdir)/dependencies/prov-check/provcheck/provconstraints.py \
	    --debug \
	    $< \
	    > _$@ \
	    2>&1
	test 1 -eq $$(tail -n1 _$@ | grep ' True' | wc -l)
	mv _$@ $@

%.svg: \
  %.dot
	dot -o _$@ -T svg $<
	mv _$@ $@

clean:
	@rm -f \
	  *.dot \
	  *.svg \
	  *-constraints.log \
	  *-expanded.ttl \
	  *-validation.ttl

readme-actions-ordered-by-timestamp-expanded.ttl: \
  readme-actions-ordered-by-timestamp.json \
  readme-actions-ordered-by-timestamp-validation.ttl \
  $(rdf_toolkit_jar) \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_check.py \
  $(top_srcdir)/case_prov/case_prov_rdf.py \
  $(top_srcdir)/case_prov/shapes/prov-shapes.ttl \
  $(top_srcdir)/dependencies/prov-check/provcheck/provconstraints.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_rdf \
	      __$@ \
	      $<
	source $(top_srcdir)/tests/venv/bin/activate \
	  && python3 $(top_srcdir)/dependencies/prov-check/provcheck/provconstraints.py \
	    --debug \
	    __$@
	source $(top_srcdir)/tests/venv/bin/activate \
	  && case_prov_check \
	    --allow-warnings \
	    $< \
	    __$@
	java -jar $(rdf_toolkit_jar) \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

readme-actions-ordered-by-timestamp-folded.ttl: \
  readme-actions-ordered-by-timestamp-expanded.ttl
	source $(top_srcdir)/tests/venv/bin/activate \
	  && rdfpipe \
	    --output-format turtle \
	    readme-actions-ordered-by-timestamp.json \
	    readme-actions-ordered-by-timestamp-expanded.ttl \
	    > __$@
	java -jar $(rdf_toolkit_jar) \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

readme-actions-ordered-by-timestamp-invisible.dot: \
  readme-actions-ordered-by-timestamp.json \
  readme-actions-ordered-by-timestamp-expanded.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --omit-empty-set \
	      _$@ \
	      readme-actions-ordered-by-timestamp.json \
	      readme-actions-ordered-by-timestamp-expanded.ttl
	mv _$@ $@

readme-actions-ordered-by-timestamp-validation.ttl: \
  readme-actions-ordered-by-timestamp.json \
  $(rdf_toolkit_jar) \
  $(top_srcdir)/tests/.venv.done.log
	rm -f __$@ _$@
	source $(top_srcdir)/tests/venv/bin/activate \
	  && case_validate \
	    --allow-infos \
	    --format turtle \
	    --output __$@ \
	    $<
	java -jar $(rdf_toolkit_jar) \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

readme-actions-ordered-by-timestamp-visible.dot: \
  readme-actions-ordered-by-timestamp.json \
  readme-actions-ordered-by-timestamp-expanded.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --display-time-links \
	      --omit-empty-set \
	      _$@ \
	      readme-actions-ordered-by-timestamp.json \
	      readme-actions-ordered-by-timestamp-expanded.ttl
	mv _$@ $@

readme-activities.dot: \
  readme-activities.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --omit-empty-set \
	      --use-deterministic-uuids \
	      _$@ \
	      $<
	mv _$@ $@

readme-activities-related-by-intervals-invisible.dot: \
  readme-activities-related-by-intervals.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --debug \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-activities-related-by-intervals-visible.dot: \
  readme-activities-related-by-intervals.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --debug \
	      --display-time-links \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-activities-related-by-intervals-with-intervals.dot: \
  readme-activities-related-by-intervals.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --debug \
	      --display-time-intervals \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-activity-vs-proper-interval-visible.dot: \
  readme-activity-vs-proper-interval.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --debug \
	      --display-time-links \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-allen-relations-invisible.dot: \
  readme-allen-relations.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --debug \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-allen-relations-visible.dot: \
  readme-allen-relations.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --debug \
	      --display-time-links \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-attribution.dot: \
  readme-attribution.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --dash-unqualified \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-eapi-bounded-visible.dot: \
  readme-eapi-bounded.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --display-time-links \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-eapi-default-visible.dot: \
  readme-eapi-default.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --display-time-links \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-provenance-records.dot: \
  readme-provenance-records.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-time-instants-invisible.dot: \
  readme-time-instants.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --debug \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-time-instants-visible.dot: \
  readme-time-instants.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --debug \
	      --display-time-links \
	      --omit-empty-set \
	      _$@ \
	      $<
	mv _$@ $@

readme-two-files-expanded.ttl: \
  readme-two-files.json \
  readme-two-files-validation.ttl \
  $(rdf_toolkit_jar) \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_check.py \
  $(top_srcdir)/case_prov/case_prov_rdf.py \
  $(top_srcdir)/case_prov/shapes/prov-shapes.ttl \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_rdf \
	      __$@ \
	      $<
	source $(top_srcdir)/tests/venv/bin/activate \
	  && case_prov_check \
	    --allow-warnings \
	    $< \
	    __$@
	java -jar $(rdf_toolkit_jar) \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

readme-two-files-folded.ttl: \
  readme-two-files-expanded.ttl
	source $(top_srcdir)/tests/venv/bin/activate \
	  && rdfpipe \
	    --output-format turtle \
	    readme-two-files.json \
	    readme-two-files-expanded.ttl \
	    > __$@
	java -jar $(rdf_toolkit_jar) \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

readme-two-files-invisible.dot: \
  readme-two-files.json \
  readme-two-files-expanded.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --omit-empty-set \
	      _$@ \
	      readme-two-files.json \
	      readme-two-files-expanded.ttl
	mv _$@ $@

readme-two-files-validation.ttl: \
  readme-two-files.json \
  $(rdf_toolkit_jar) \
  $(top_srcdir)/tests/.venv.done.log
	rm -f __$@ _$@
	source $(top_srcdir)/tests/venv/bin/activate \
	  && case_validate \
	    --allow-infos \
	    --format turtle \
	    --output __$@ \
	    $<
	java -jar $(rdf_toolkit_jar) \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

readme-two-files-visible.dot: \
  readme-two-files.json \
  readme-two-files-expanded.ttl \
  $(top_srcdir)/case_prov/__init__.py \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  $(top_srcdir)/tests/.venv.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --display-time-links \
	      --omit-empty-set \
	      _$@ \
	      readme-two-files.json \
	      readme-two-files-expanded.ttl
	mv _$@ $@
