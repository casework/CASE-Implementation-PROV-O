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

top_srcdir := $(shell cd ../../.. ; pwd)

exdirs := $(shell find * -maxdepth 0 -type d | sort | egrep -v '^src$$')

ttl_files := $(foreach exdir,$(exdirs),$(exdir)/$(exdir)-prov.ttl)

all:

check: \
  prov-constraints.log

clean:
	@rm -f \
	  _* \
	  prov-constraints.log

prov-constraints.log: \
  $(top_srcdir)/dependencies/prov-check/provcheck/provconstraints.py \
  $(ttl_files)
	source $(top_srcdir)/tests/venv/bin/activate \
	  && python3 $(top_srcdir)/dependencies/prov-check/provcheck/provconstraints.py \
	    --debug \
	    $(ttl_files) \
	    > _$@ \
	    2>&1
	mv _$@ $@
