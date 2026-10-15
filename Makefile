.PHONY: help install dev dev-agent dev-frontend test e2e clean-sandboxes

help:
	@echo "make install         - install Python (uv) and frontend (npm) dependencies"
	@echo "make dev-agent       - agent service on :8000 (AG-UI + micro-app gateway)"
	@echo "make dev-frontend    - Next.js UI on :3000"
	@echo "make test            - unit tests (no cluster, no LLM)"
	@echo "make e2e             - browser journey against the running stack (needs dev servers)"
	@echo "make clean-sandboxes - delete all sandbox pods, services and ingresses"

install:
	uv sync
	cd frontend && npm install --legacy-peer-deps

dev-agent:
	uv run uvicorn sandbox_agent.api:create_app --factory --host 0.0.0.0 --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev

test:
	uv run pytest -q
	cd frontend && npx tsc --noEmit

e2e:
	cd frontend && node e2e/journey.mjs ../e2e-output

clean-sandboxes:
	kubectl -n sandbox-system get pods -o name | grep sbx- | xargs -r kubectl -n sandbox-system delete --wait=false
	kubectl -n sandbox-system delete ingress,svc -l app.kubernetes.io/managed-by=sandbox-mcp --wait=false
