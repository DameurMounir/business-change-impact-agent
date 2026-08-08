.PHONY: test format lint typecheck release-gate demo ui clean

test:
	python -m pytest

format:
	python -m ruff format .

lint:
	python -m ruff check .

typecheck:
	python -m mypy src scripts

release-gate:
	python scripts/release_gate.py

demo:
	python -m business_change_impact_agent demo --workspace artifacts/demo

ui:
	streamlit run streamlit_app.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov dist build *.egg-info artifacts/demo
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
