.PHONY: install test lint run docker docker-down

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

lint:
	ruff check .

lint-fix:
	ruff check --fix .

run:
	python app.py

docker:
	docker-compose up --build

docker-down:
	docker-compose down
