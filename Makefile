# Newest Python >= 3.11 on PATH (an older system python3 may come first);
# tools/repoctl applies the same rule for hooks. Override with PYTHON=...
PYTHON ?= $(shell for p in python3.14 python3.13 python3.12 python3.11 python3 python; do command -v $$p >/dev/null 2>&1 && $$p -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null && { echo $$p; break; }; done)
REPOCTL := $(PYTHON) tools/repoctl.py
SKILL_TEST_SUITES := $(wildcard .agents/skills/*/tests)

.DEFAULT_GOAL := help

.PHONY: help python-check init inventory resources skill-digest check doctor readiness test test-future verify validate incident issue labels review-packet \
	start next ui-review done new handover map where risk garden capabilities sync github-sync similar eval trial

# Export user-supplied values so recipes pass them as data, not as shell source.
export Q AGENT MODEL TASKS DESC GROUP COVERS ACCESS TIER FORCE NAME KIND OWNER BUDGET TITLE SUMMARY BODY TYPE PRIORITY AREA TOPIC STATUS SURFACE GATE PUBLIC_REVIEWED REVIEW_EVIDENCE ISSUE_FILE PUBLIC_SAFE

help:
	@printf '%s\n' \
	  'EVERY SESSION (this is all most tasks need)' \
	  '  make start                       Brief: branch, handover, next step, what needs attention' \
	  '  make next                        The single next step toward a complete product' \
	  '  make where Q="login form"        Find files, functions, owning docs, past failures' \
	  '  make ui-review                   Screenshot the UI (phone/desktop, light/dark) and judge it' \
	  '  make done                        Before saying "done": heal derived files, gates, all tests' \
	  '' \
	  'EXTEND THE SYSTEM (searches for overlap first, wires everything in)' \
	  '  make new KIND=skill NAME=x DESC="what; when to use"     Reusable procedure' \
	  '  make new KIND=agent NAME=x DESC="job; when" [ACCESS=read-only TIER=fast]   Subagent role' \
	  '  make new KIND=doc NAME=x DESC="owns; read when" [GROUP=design COVERS="src/x/**"]' \
	  '  make similar Q="release notes"   Does a similar skill or role already exist?' \
	  '  make capabilities                Tools, agent hosts, and MCP routes available here' \
	  '' \
	  'WHEN NEEDED' \
	  '  make risk                        How much ceremony this change needs' \
	  '  make handover                    Write HANDOVER.md before pausing (git facts pre-filled)' \
	  '  make map                         One-screen repository map' \
	  '  make garden                      Full rot report' \
	  '  make sync                        Regenerate derived files after editing their sources' \
	  '  make issue BODY=path TITLE="..." TYPE=... PRIORITY=... AREA=... TOPIC=...   File an issue' \
	  '  make review-packet ISSUE_FILE=path   Brief for a fresh critic' \
	  '  make incident TITLE="..." SUMMARY="..."   Private incident draft' \
	  '' \
	  'PROJECT SETUP AND MAINTENANCE' \
	  '  make init NAME=my-project KIND=web   Turn the template into your project' \
	  '  make check | verify | doctor | readiness | inventory | resources | labels | github-sync' \
	  '  make eval AGENT=claude [MODEL=haiku]   Fresh-agent navigation benchmark (cheap model by default)' \
	  '  make trial NAME=<request> [MODEL=sonnet] [BUDGET=25]   Build trial: an agent builds a product; friction report' \
	  '  make validate BODY=path | skill-digest SKILL_PATH=.agents/skills/name'

python-check:
	@test -n "$(PYTHON)" && $(PYTHON) -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null || { echo "Needs Python 3.11+ (found: '$(PYTHON)'); install python3.11 or newer, or run: make PYTHON=/path/to/python3.11 ..." >&2; exit 1; }

init: python-check
	$(REPOCTL) init --name "$${NAME}" --kind "$${KIND}" $(if $(OWNER),--owner "$${OWNER}",)

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

# The same suite 800 days ahead: fails when a fixture or check rots with the calendar (#10).
test-future: python-check
	PYTHONPATH="$(CURDIR)/tools/tests/clockshift" SHIFT_DAYS=800 $(MAKE) test

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

# The one completion command: heal derived files, run the change gate, then
# everything CI runs. Prints the risk tier so the right review follows.
done: python-check
	@$(REPOCTL) sync
	@$(REPOCTL) finish
	@$(MAKE) --no-print-directory verify
	@echo "All gates passed. Get the review your risk tier requires, then hand over or open the PR."

new: python-check
	$(if $(KIND),,$(error Choose what to create: make new KIND=skill|agent|doc NAME=my-name DESC="what it does; when to use it"))
	$(if $(NAME),,$(error Name it: NAME=kebab-case-name))
	$(if $(DESC),,$(error Describe it: DESC="what it does; when to use it"))
	@$(REPOCTL) new --kind "$${KIND}" --name "$${NAME}" \
	  --description "$${DESC}" \
	  --group "$${GROUP:-operate}" --covers "$${COVERS:-}" --access "$${ACCESS:-read-only}" \
	  --tier "$${TIER:-balanced}" $(if $(filter 1 yes true,$(FORCE)),--force,)

handover: python-check
	@$(REPOCTL) handover

map: python-check
	@$(REPOCTL) map

next: python-check
	@$(REPOCTL) next

ui-review: python-check
	$(REPOCTL) ui-review

where: python-check
	$(if $(Q),,$(error Add what to look for: make where Q="login form"))
	@$(REPOCTL) where "$${Q}"

risk: python-check
	@$(REPOCTL) risk

garden: python-check
	$(REPOCTL) garden

capabilities: python-check
	@$(REPOCTL) capabilities

sync: python-check
	$(REPOCTL) sync

github-sync: python-check
	$(REPOCTL) github-sync

similar: python-check
	$(if $(Q),,$(error Describe the capability: make similar Q="draft release notes"))
	@$(REPOCTL) similar "$${Q}"

eval: python-check
	$(REPOCTL) eval --host "$${AGENT:-claude}" $(if $(TASKS),--tasks "$${TASKS}",) $(if $(MODEL),--model "$${MODEL}",)

trial: python-check
	$(if $(NAME),,$(error Name a request in .agents/trials/: make trial NAME=waypoint))
	$(REPOCTL) trial "$${NAME}" $(if $(MODEL),--model "$${MODEL}",) $(if $(BUDGET),--budget "$${BUDGET}",)
