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

all: \
  .venv-pre-commit/var/.pre-commit-built.log \
  .git_submodule_init-casework.github.io.done.log
	$(MAKE) \
	  PYTHON3=$(PYTHON3) \
	  --directory tests
	$(MAKE) \
	  --directory figures

.PHONY: \
  check-supply-chain \
  check-supply-chain-pre-commit \
  clean-figures \
  clean-tests

.git_submodule_init.done.log: \
  .gitmodules
	git submodule update --init
	touch $@

.git_submodule_init-casework.github.io.done.log: \
  dependencies/casework.github.io/.gitmodules
	$(MAKE) \
	  PYTHON3=$(PYTHON3) \
	  --directory dependencies/casework.github.io \
	  .git_submodule_init.done.log
	touch $@

# This virtual environment is meant to be built once and then persist, even through 'make clean'.
# If a recipe is written to remove this flag file, it should first run `pre-commit uninstall`.
.venv-pre-commit/var/.pre-commit-built.log:
	rm -rf .venv-pre-commit
	test -r .pre-commit-config.yaml \
	  || (echo "ERROR:Makefile:pre-commit is expected to install for this repository, but .pre-commit-config.yaml does not seem to exist." >&2 ; exit 1)
	$(PYTHON3) -m venv \
	  .venv-pre-commit
	source .venv-pre-commit/bin/activate \
	  && pip install \
	    --upgrade \
	    pip \
	    setuptools \
	    wheel
	source .venv-pre-commit/bin/activate \
	  && pip install \
	    pre-commit
	source .venv-pre-commit/bin/activate \
	  && pre-commit install
	mkdir -p \
	  .venv-pre-commit/var
	touch $@

check: \
  .git_submodule_init-casework.github.io.done.log \
  check-mypy
	$(MAKE) \
	  --directory case_prov/shapes \
	  check
	$(MAKE) \
	  --directory tests \
	  check

check-mypy: \
  .git_submodule_init.done.log \
  .venv-pre-commit/var/.pre-commit-built.log
	$(MAKE) \
	  PYTHON3=$(PYTHON3) \
	  --directory tests \
	  check-mypy

# This target's dependencies potentially modify the working directory's Git state, so it is intentionally not a dependency of check.
check-supply-chain: \
  check-supply-chain-pre-commit \
  check-mypy

# This target is scheduled to run as part of prerelease review.
#
# Update pre-commit configuration and use the updated config file to
# review code.  Only have Make exit if 'pre-commit run' modifies files.
check-supply-chain-pre-commit: \
  .venv-pre-commit/var/.pre-commit-built.log
	source .venv-pre-commit/bin/activate \
	  && pre-commit autoupdate
	git diff \
	  --exit-code \
	  .pre-commit-config.yaml \
	  || ( \
	      source .venv-pre-commit/bin/activate \
	        && pre-commit run \
	          --all-files \
	          --config .pre-commit-config.yaml \
	    ) \
	    || git diff \
	      --stat \
	      --exit-code \
	      || ( \
	          echo \
	            "WARNING:Makefile:pre-commit configuration can be updated.  It appears the updated would change file formatting." \
	            >&2 \
	            ; exit 1 \
                )
	@git diff \
	  --exit-code \
	  .pre-commit-config.yaml \
	  || echo \
	    "INFO:Makefile:pre-commit configuration can be updated.  It appears the update would not change file formatting." \
	    >&2

clean: \
  clean-figures \
  clean-tests
	@$(MAKE) \
	  --directory case_prov/shapes \
	  clean
	@rm -f \
	  .git_submodule_init.done.log \
	  dependencies/casework.github.io/.git_submodule_init.done.log

clean-figures:
	@$(MAKE) \
	  --directory figures \
	  clean

clean-tests:
	@$(MAKE) \
	  --directory tests \
	  clean

# This recipe guarantees a timestamp update order, and is otherwise a nop.
dependencies/casework.github.io/.gitmodules: \
  .git_submodule_init.done.log
	test -r $@
	touch $@

distclean: \
  clean
	@rm -rf \
	  build \
	  dist
	@rm -f \
	  *.egg-info
