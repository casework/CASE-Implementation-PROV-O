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

PYTHON3 ?= python3

top_srcdir := $(shell cd .. ; pwd)

all: \
  all-casework.github.io \
  all-Issue-88

.PHONY: \
  all-Issue-88 \
  all-casework.github.io \
  check-Issue-88 \
  check-casework.github.io \
  check-mypy \
  clean-Issue-88 \
  clean-casework.github.io \
  format

.venv.done.log: \
  $(top_srcdir)/.git_submodule_init.done.log \
  $(top_srcdir)/setup.cfg \
  $(top_srcdir)/setup.py
	rm -rf venv
	$(PYTHON3) -m venv \
	  venv
	source venv/bin/activate \
	  && pip install \
	    --upgrade \
	    pip \
	    setuptools \
	    wheel
	source venv/bin/activate \
	  && pip install \
	    --editable \
	    $(top_srcdir)[testing]
	touch $@

all-Issue-88: \
  check-Issue-88
	$(MAKE) \
	  --directory Issue-88

all-casework.github.io: \
  .venv.done.log
	$(MAKE) \
	  --directory casework.github.io/examples

check: \
  check-mypy \
  check-doctest \
  check-casework.github.io \
  check-Issue-88

check-Issue-88: \
  .venv.done.log
	$(MAKE) \
	  --directory Issue-88 \
	  check

check-casework.github.io: \
  .venv.done.log
	$(MAKE) \
	  --directory casework.github.io/examples \
	  check

check-doctest: \
  .venv.done.log
	source venv/bin/activate \
	  && pytest \
	    --doctest-modules \
	    --log-level=DEBUG \
	    $(top_srcdir)/case_prov

check-mypy: \
  .venv.done.log
	source venv/bin/activate \
	  && mypy \
	    --exclude venv \
	    --strict \
	    $(top_srcdir)/case_prov \
	    .

clean: \
  clean-Issue-88 \
  clean-casework.github.io
	@rm -f \
	  .venv.done.log
	@rm -rf \
	  venv

clean-Issue-88:
	@$(MAKE) \
	  --directory Issue-88 \
	  clean

clean-casework.github.io:
	@$(MAKE) \
	  --directory casework.github.io/examples \
	  clean
