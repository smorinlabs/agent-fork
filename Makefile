# Environment dependency checks only — build/test tasks live in the justfile.

TOOLS := git uv just flox

.PHONY: check
check:
	@fail=0; \
	for t in $(TOOLS); do \
		if command -v $$t >/dev/null 2>&1; then \
			printf '  ok   %-6s %s\n' "$$t" "$$(command -v $$t)"; \
		else \
			printf '  MISS %-6s (required)\n' "$$t"; fail=1; \
		fi; \
	done; \
	exit $$fail
