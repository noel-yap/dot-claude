# Makefile for the skill eval suites.
#
# Each skill under skills/<name>/evals has fast unit tests (no API) plus
# end-to-end "claude eval" tests (real model calls, graded by a Beta-binomial
# posterior: an assertion passes once the posterior puts most of its mass at
# or above --live-eval-target-rate, over at most --live-eval-max-trials runs).
# The two are split by the `live_eval` marker: unit targets select
# `-m "not live_eval"`, eval targets select `-m live_eval`. The per-skill
# eval dirs reuse the module names _helpers / _assertions, so they CANNOT be
# collected in one pytest session — every target runs one eval dir at a time.
#
# Run from this directory (skills/). Examples:
#   make test                 # everything: unit tests then claude evals
#   make test-unit            # fast unit tests only, no API calls
#   make eval                 # all skills' claude evals (target 2/3, <=21 runs)
#   make eval-dependency-injection
#   make eval TARGET_RATE=0.8 MAX_TRIALS=12
#   make test-unit PYTEST_ARGS="-v"

PYTEST      ?= python3 -m pytest
MAX_TRIALS  ?= 21
TARGET_RATE ?= 0.6667
PYTEST_ARGS ?=

UNIT_FLAGS := -m "not live_eval"
EVAL_FLAGS := -m live_eval --live-eval-max-trials $(MAX_TRIALS) --live-eval-target-rate $(TARGET_RATE)

# Eval dirs discovered from the tree, e.g. "dependency-injection/evals".
SKILL_DIRS := $(patsubst %/,%,$(dir $(wildcard */evals/evals.json)))
# Skill names, e.g. "dependency-injection".
SKILLS := $(patsubst %/evals,%,$(SKILL_DIRS))

.DEFAULT_GOAL := help

.PHONY: help test test-shared test-unit eval clean

help: ## Show this help
	@echo "Skill eval suite targets:"
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Per-skill claude evals: make eval-<skill>"
	@echo "Discovered skills:      $(SKILLS)"
	@echo "Vars: MAX_TRIALS=$(MAX_TRIALS) TARGET_RATE=$(TARGET_RATE) PYTEST_ARGS='$(PYTEST_ARGS)'"

test: test-unit eval ## Run everything: unit tests then claude evals (real model calls)

test-unit: test-shared ## Run shared + every skill's unit tests (excludes live_eval)
	@for d in $(SKILL_DIRS); do \
	  echo "== unit: $$d =="; \
	  $(PYTEST) "$$d" $(UNIT_FLAGS) $(PYTEST_ARGS) || exit $$?; \
	done

test-shared: ## Run the shared eval_utils package unit tests
	$(PYTEST) eval_utils/tests $(PYTEST_ARGS)

eval: ## Run every skill's claude evals (real model calls; set MAX_TRIALS/TARGET_RATE)
	@for d in $(SKILL_DIRS); do \
	  echo "== eval: $$d =="; \
	  $(PYTEST) "$$d" $(EVAL_FLAGS) $(PYTEST_ARGS) || exit $$?; \
	done

eval-%: ## Run claude evals for one skill: make eval-<skill>
	$(PYTEST) "$*/evals" $(EVAL_FLAGS) $(PYTEST_ARGS)

clean: ## Remove pytest / __pycache__ caches under skills/
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
