.PHONY: install dev test lint fmt demo sample build docker clean

install:        ## install the CLI
	pip install .

dev:            ## editable install with test and lint tools
	pip install -e ".[dev,aws]"

test:           ## run the test suite
	pytest --cov=agentposture --cov-report=term-missing

lint:           ## static checks
	ruff check src tests

fmt:
	ruff check --fix src tests

demo:           ## open the dashboard with sample data
	agentposture demo

sample:         ## regenerate the committed sample dashboard and reports
	agentposture demo --out examples/sample-dashboard

build:          ## build wheel and sdist into dist/
	python -m build

docker:
	docker build -t agentposture:latest .

clean:
	rm -rf build dist .pytest_cache .ruff_cache .coverage htmlcov src/*.egg-info
