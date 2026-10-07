.PHONY: help install test run

help:
	@echo "make install  install dependencies"
	@echo "make test     run the tests"
	@echo "make run      start the dev server on :5000"

install:
	python3 -m pip install -r requirements.txt

test:
	python3 -m pytest -q

run:
	flask --app notes:create_app run --debug
