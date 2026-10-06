PYTHON ?= python3
REPOCTL := $(PYTHON) tools/repoctl.py
SKILL_TEST_SUITES := $(wildcard .agents/skills/*/tests)

.DEFAULT_GOAL := help

.PHONY: help python-check init inventory resources skill-digest check doctor readiness test verify validate incident issue labels review-packet \
	start finish map where risk garden capabilities adapters skill-overlap eval

# Export user-supplied values so recipes pass them as data, not as shell source.
export Q TEXT AGENT TASKS NAME KIND TITLE SUMMARY BODY TYPE PRIORITY AREA TOPIC STATUS SURFACE GATE PUBLIC_REVIEWED REVIEW_EVIDENCE ISSUE_FILE PUBLIC_SAFE

help:
	@printf '%s\n' \
	  'make start                                Print the session brief (hosts without hooks)' \
	  'make where Q="..."                        Find paths, symbols, owning docs, and past failures' \
	  'make map                                  One-screen repository map' \
	  'make risk                                 Ceremony tier for this branch'"'"'s changes' \
	  'make finish                               Completion gate: owed docs, drift, markers' \
	  'make garden                               Full rot report (docs, deprecations, budgets, surfaces)' \
	  'make adapters                             Regenerate host adapter files from .agents/' \
	  'make capabilities                         Tools, agent hosts, and MCP routes available here' \
	  'make skill-overlap TEXT="..."             Compare a proposed capability with existing ones' \
	  'make eval AGENT=claude [TASKS=a,b]        Fresh-agent navigation benchmark' \
	  'make inventory                            Show detected and declared surfaces' \
	  'make resources                            Show validated read-only resource routes' \
	  'make skill-digest SKILL_PATH=.agents/skills/name  Hash a reviewed skill tree' \
	  'make init NAME=my-project KIND=web       Set identity, reset vision intake, and update README' \
	  'make check                                Validate structure, docs, links, and hygiene' \
	  'make doctor                               Check initialization and launch readiness' \
	  'make readiness                            Enforce public-launch evidence gates' \
	  'make validate BODY=path STATUS=triage      Validate an issue body without filing it' \
	  'make verify                               Run tests, structure checks, and declared surface checks' \
	  'make incident TITLE="..." SUMMARY="..."    Create a private incident draft (PUBLIC_SAFE=1 + review evidence promotes)' \
	  'make issue BODY=path TITLE="..."                  File a profile-aware public-safe issue' \
	  'make labels                               Synchronize canonical GitHub issue labels' \
	  'make review-packet ISSUE_FILE=path         Print a fresh-agent critic prompt'

python-check:
	@$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 11), "repoctl requires Python 3.11+"'

init: python-check
	$(REPOCTL) init --name "$${NAME}" --kind "$${KIND}"

inventory:
	$(REPOCTL) inventory

resources: python-check
	$(REPOCTL) resources

skill-digest:
	$(REPOCTL) skill-digest "$${SKILL_PATH}"

check: python-check
	$(REPOCTL) check

doctor: python-check
	$(REPOCTL) doctor

readiness: python-check
	$(REPOCTL) readiness

test: python-check
	$(PYTHON) -m unittest discover -s tools/tests -p 'test_*.py'
	@for suite in $(SKILL_TEST_SUITES); do \
	  echo "-- $$suite"; \
	  $(PYTHON) -m unittest discover -s "$$suite" -p 'test_*.py' || exit 1; \
	done

verify: python-check
	$(MAKE) test
	$(REPOCTL) verify
	$(REPOCTL) doctor

validate: python-check
	$(REPOCTL) validate-issue --body-file "$${BODY}" --status "$${STATUS}"

incident:
	$(REPOCTL) incident --title "$${TITLE}" --summary "$${SUMMARY}" $(if $(filter 1 yes true,$(PUBLIC_SAFE)),--public-safe --review-evidence "$${REVIEW_EVIDENCE}",)

issue:
	$(REPOCTL) issue \
	  --title "$${TITLE}" \
	  --body-file "$${BODY}" \
	  --type "$${TYPE}" \
	  --priority "$${PRIORITY}" \
	  --area "$${AREA}" \
	  --topic "$${TOPIC}" \
	  --status "$${STATUS}" \
	  --surface "$${SURFACE}" \
	  --gate "$${GATE}" \
	  $(if $(filter 1 yes true,$(PUBLIC_REVIEWED)),--public-reviewed,) \
	  --review-evidence "$${REVIEW_EVIDENCE}"

labels:
	$(REPOCTL) labels --sync

review-packet:
	$(REPOCTL) review-packet --issue-file "$${ISSUE_FILE}"

start: python-check
	@$(REPOCTL) start

finish: python-check
	$(REPOCTL) finish

map: python-check
	@$(REPOCTL) map

where: python-check
	@$(REPOCTL) where "$${Q:?set Q=\"search terms\"}"

risk: python-check
	@$(REPOCTL) risk

garden: python-check
	$(REPOCTL) garden

capabilities: python-check
	@$(REPOCTL) capabilities

adapters: python-check
	$(REPOCTL) adapters

skill-overlap: python-check
	@$(REPOCTL) skill-overlap "$${TEXT:?set TEXT=\"capability description\"}"

eval: python-check
	$(REPOCTL) eval --host "$${AGENT:-claude}" $(if $(TASKS),--tasks "$${TASKS}",)
