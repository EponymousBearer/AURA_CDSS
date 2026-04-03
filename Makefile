.PHONY: install train evaluate backend frontend test docker clean

install:
	python -m pip install -r backend/requirements.txt -r training/requirements.txt
	cd frontend && npm install

train:
	cd training && python train.py

evaluate:
	cd training && python evaluate.py

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	pytest backend/tests/ -v && cd frontend && npm run lint

docker:
	docker-compose up --build

clean:
	python -c "import pathlib, shutil; root = pathlib.Path('.'); targets = ['__pycache__', '.next', 'catboost_info']; [shutil.rmtree(path, ignore_errors=True) for target in targets for path in root.rglob(target) if path.is_dir()]"