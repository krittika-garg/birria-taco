# common make vars and targets:
export LINTER = flake8
export PYLINTFLAGS = --exclude=__main__.py

export CLOUD_MONGO = 0

PYTHONFILES = $(shell ls *.py)
PYTESTFLAGS = -vv --verbose --cov-branch --cov-report term-missing --tb=short -W ignore::FutureWarning

MAIL_METHOD = api

FORCE:

# Minimum coverage percent; empty means no minimum. CI sets it per package.
COV_MIN ?=

tests: lint pytests

lint: $(patsubst %.py,%.pylint,$(PYTHONFILES)) lint_tests

%.pylint:
	$(LINTER) $(PYLINTFLAGS) $*.py

# Test code gets linted too.
lint_tests: FORCE
	@if [ -d tests ]; then echo "$(LINTER) $(PYLINTFLAGS) tests"; \
		$(LINTER) $(PYLINTFLAGS) tests; fi

pytests: FORCE
	pytest $(PYTESTFLAGS) --cov=$(PKG) $(if $(COV_MIN),--cov-fail-under=$(COV_MIN))

# test a python file:
%.py: FORCE
	$(LINTER) $(PYLINTFLAGS) $@
	pytest $(PYTESTFLAGS) tests/test_$*.py

nocrud:
	-rm *~
	-rm *.log
	-rm *.out
	-rm .*swp
	-rm $(TESTDIR)/*~
