.PHONY: run test docker docker-down install

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

run:
	python app.py

docker:
	docker-compose up --build

docker-down:
	docker-compose down
