# Vista

**Локальный AI-ассистент, аналог Джарвиса.**  
Работает полностью на локальных нейросетях — без интернета, без облаков, без слежки.

## Возможности

- **Четыре режима:** CLI (текст), voice (голос), daemon (фон + wake word), once (один запрос)
- **Голосовое управление:** wake word («Виста», «Джарвис»), распознавание речи (faster-whisper), синтез речи (Piper/macOS say)
- **Навыки (skills):** система, разработка (Git), продуктивность (календарь), дом
- **Память:** долговременная (ChromaDB) + контекст диалога с авто-сжатием
- **Быстрые команды:** время, дата, калькулятор, запуск приложений (без LLM)
- **Анти-галлюцинации:** фильтрация утечек системного промпта

## Быстрый старт

```bash
# 1. Установка зависимостей
pip install -r requirements.txt

# 2. Голосовые зависимости (опционально)
pip install faster-whisper piper-tts openwakeword

# 3. Запуск Ollama
ollama serve

# 4. Загрузка моделей
make pull-model

# 5. Запуск
make run        # CLI
make voice      # голосовой
make daemon     # фоновый (wake word)
```

## Использование

```bash
python main.py                    # CLI по умолчанию
python main.py -m voice           # голосовой режим
python main.py -m daemon          # фоновый (ждёт wake word)
python main.py -m once -q "..."   # один запрос
python main.py -c config.yaml     # свой конфиг
```

### Команды CLI

| Команда | Действие |
|---------|----------|
| `/help` | справка |
| `/clear` | очистить историю |
| `/skills` | список навыков |
| `/history` | история диалога |
| `/model` | текущая модель |
| `/voice` | переключиться в голос |
| `/quit` | выход |

## Архитектура

```
Vista/
├── core/           # оркестратор, конфиг, event bus
├── brain/          # LLM, память, промпты
├── voice/          # STT, TTS, wake word
├── skills/         # система, dev, продуктивность, дом
├── perception/     # зрение (скриншоты)
├── ui/             # интерфейсы
├── data/           # chroma, модели piper
├── config.yaml     # конфигурация
└── main.py         # точка входа
```

## Конфигурация

`config.yaml` — всё в одном файле:

- **models.llm** — модель Ollama, температура, контекст
- **models.stt** — faster-whisper (base, int8)
- **models.tts** — Piper или macOS say
- **memory** — ChromaDB, лимиты контекста
- **skills** — авто-подключаемые модули
- **daemon** — таймаут активного диалога

## Требования

- Python ≥ 3.11
- [Ollama](https://ollama.ai) с моделями `phi3:3.8b-mini-4k-instruct-q4_K_M` и `nomic-embed-text`
- Для голоса: faster-whisper, piper-tts, openwakeword

## Лицензия

MIT
