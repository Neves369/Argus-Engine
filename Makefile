.PHONY: test test-backend test-frontend

test: test-backend test-frontend

test-backend:
	cd backend && { \
	  if [ -x .venv/bin/pytest ]; then .venv/bin/pytest; else python -m pytest; fi; \
	}

test-frontend:
	cd frontend && npm test