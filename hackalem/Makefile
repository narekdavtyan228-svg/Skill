.PHONY: help verify smoke eval test ui ui-qa data status install install-dev

help:
	@echo "make install  — поставить зависимости в активный venv"
	@echo "make verify   — запустить все ворота приёмки, включая браузерный UI QA"
	@echo "make smoke    — сквозной прогон на одном комплекте (главные ворота приёмки)"
	@echo "make eval     — метрики по всему датасету"
	@echo "make test     — pytest"
	@echo "make data     — сгенерировать синтетические комплекты"
	@echo "make ui       — поднять витрину на порту 8501 (демо для жюри)"
	@echo "make ui-qa    — проверить UI на 375/768/1024/1440 px"
	@echo "make status   — срез прогресса прямо сейчас"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

verify:
	python verify.py

# Владелец целей smoke/eval/test — роль A. Цели обязаны работать с самого начала,
# пусть даже на заглушках: без зелёного smoke цикл не считается закрытым.
smoke:
	python -m core.orchestrator --permit data/fixtures/permit_0001 --print

eval:
	python -m eval.run

test:
	pytest -q

data:
	python -m data.generator --output data --seed 20260920

ui:
	streamlit run ui/app.py --server.port $${STREAMLIT_SERVER_PORT:-8501}

ui-qa:
	python -m ui.visual_qa

status:
	./checkpoint.sh --quick
