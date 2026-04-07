.PHONY: install lint format test run docker

install:
	pip install -r requirements.txt
	pip install ruff mypy pytest pre-commit
	pre-commit install || true

lint:
	ruff check .

format:
	ruff format .

test:
	pytest -q

run:
	python main.py

docker:
	docker build -t freddy-agent:dev .
