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

top_srcdir := $(shell cd ../.. ; pwd)

rdf_toolkit_jar := $(top_srcdir)/dependencies/casework.github.io/dependencies/CASE-develop/dependencies/UCO/lib/rdf-toolkit.jar

all: \
  example.svg

.example.ttl.case_validate.done.log: \
  $(top_srcdir)/tests/.venv.done.log \
  example.ttl
	source $(top_srcdir)/tests/venv/bin/activate \
	  && case_validate \
	    example.ttl
	touch $@

%.svg: \
  %.dot
	dot -T svg -o _$@ $<
	mv _$@ $@

# 'make check' does not build the SVG, because the testing environment
# is not assumed to have 'dot' available.
check: \
  example.dot

clean:
	@rm -f \
	  *.dot \
	  *.svg \
	  _* \
	  .*.log

example_prov.ttl: \
  $(top_srcdir)/case_prov/case_prov_rdf.py \
  .example.ttl.case_validate.done.log
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_rdf \
	      --use-deterministic-uuids \
	      __$@ \
	      example.ttl
	java -jar $(rdf_toolkit_jar) \
	  --inline-blank-nodes \
	  --source __$@ \
	  --source-format turtle \
	  --target _$@ \
	  --target-format turtle
	rm __$@
	mv _$@ $@

example.dot: \
  $(top_srcdir)/case_prov/case_prov_dot.py \
  example_prov.ttl
	export CDO_DEMO_NONRANDOM_UUID_BASE="$(top_srcdir)" \
	  && source $(top_srcdir)/tests/venv/bin/activate \
	    && case_prov_dot \
	      --use-deterministic-uuids \
	      _$@ \
	      example.ttl \
	      example_prov.ttl
	mv _$@ $@
