.PHONY: help install install-voice run cli voice clean reset test lint check-ollama pull-model

PYTHON := python3
PIP := pip3

help: ## Показать это сообщение
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Установить базовые зависимости
	$(PIP) install -r requirements.txt

install-voice: install ## Установить голосовые зависимости
	$(PIP) install faster-whisper piper-tts openwakeword

check-ollama: ## Проверить статус Ollama
	@curl -s http://localhost:11434/api/tags > /dev/null && echo "Ollama: OK" || echo "Ollama: НЕ ЗАПУЩЕН — запусти 'ollama serve'"

pull-model: ## Загрузить phi3 модель в Ollama
	ollama pull phi3:3.8b-mini-4k-instruct-q4_K_M
	ollama pull nomic-embed-text

run: check-ollama ## Запустить Vista в CLI режиме
	$(PYTHON) main.py

cli: run ## Алиас для CLI режима

voice: check-ollama ## Запустить Vista в голосовом режиме
	$(PYTHON) main.py -m voice

daemon: check-ollama ## Запустить Vista в фоновом режиме
	$(PYTHON) main.py -m daemon

once: check-ollama ## Один запрос в CLI
	$(PYTHON) main.py -m once

test: check-ollama ## Прогнать быстрый тест всех систем
	@echo "=== Memory ==="
	$(PYTHON) -c "\
import asyncio; from brain.memory import Memory; \
m = Memory(); m.clear_history(); \
m.add_conversation_turn('user', 'test'); \
m.add_conversation_turn('assistant', 'ok'); \
print(f'  Count: {m.count()}, History: OK'); m.clear_history(); m.close()"
	@echo "=== Skills ==="
	$(PYTHON) -c "\
from skills.registry import SkillRegistry; \
r = SkillRegistry(); r.auto_discover(['skills.system','skills.dev','skills.productivity']); \
print(f'  Loaded: {list(r.list_skills().keys())}')"
	@echo "=== LLM ==="
	@curl -s http://localhost:11434/api/tags | $(PYTHON) -c "import sys,json; \
data=json.load(sys.stdin); models=[m['name'] for m in data.get('models',[])]; \
print(f'  Models: {models}')"
	@echo "=== STT ==="
	@$(PYTHON) -c "import importlib; print('  faster-whisper:', 'OK' if importlib.util.find_spec('faster_whisper') else 'not installed')" 2>/dev/null || echo "  faster-whisper: not installed"
	@echo "=== TTS ==="
	@say -v Milena "тест" 2>/dev/null && echo "  macOS say: OK" || echo "  macOS say: FAIL"
	@echo "\n=== All tests passed ==="

clean: ## Очистить кеш и временные файлы
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .pytest_cache 2>/dev/null || true

reset: ## Полный сброс — очистить память и кеш моделей
	rm -rf data/

lint: ## Проверить код (ruff)
	@ruff check . 2>/dev/null || echo "ruff не установлен — pip install ruff"
	@ruff format --check . 2>/dev/null || true

format: ## Форматировать код (ruff)
	@ruff format . 2>/dev/null || echo "ruff не установлен — pip install ruff"
	@ruff check --fix . 2>/dev/null || true
