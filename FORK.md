# Hermes — Bifrost Edition (форк temga/hermes-agent)

Этот репозиторий — форк [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent),
адаптированный под коммерческое использование внутри Wink и Ростелекома. Ядро агента остаётся
upstream-ным; форк добавляет «один ключ на всё» через Bifrost Gateway, собственные установщики и
каналы обновлений, а также отключает отправку телеметрии в Nous.

Принцип: **ядро не переписываем**. Вся функциональность Bifrost живёт в плагинах
(`plugins/<category>/bifrost/`), в `hermes_cli/bifrost_edition.py`, в скриптах установки и CI.
Правки ядра — точечные, только там, где без них нельзя, и каждая отмечена комментарием
`Bifrost edition` / `BIFROST-EDITION`.

## Правила для разработчиков и AI-агентов

- **Ядро — только по согласованию.** Прежде чем править что-то вне Bifrost-плагинов,
  `hermes_cli/bifrost_edition.py`, скриптов установки и CI (например `hermes_cli/`, `agent/`,
  `gateway/`, `apps/desktop/src/`), объясните, зачем нужна правка ядра и нет ли пути без неё.
  Каждую правку ядра помечайте комментарием `Bifrost edition`.
- **Каждая задача — своя ветка** `feat/…` / `fix/…` / `docs/…`, вливается в `bifrost-next`.
  Напрямую в `main` / `main-bifrost` не разрабатываем.
- **Без явного «да» не пушить** в `main`, в `bifrost-edition`, не ставить и не пушить теги и не
  запускать сборку установщиков вручную: у Bifrost Edition живые клиенты, push в `main` сразу
  показывает им «доступно обновление», а тег публикует новые установщики. Перед вопросом —
  короткий список того, что получат клиенты.
- **Плагины Bifrost правятся только в этом дереве**, отдельный репозиторий плагинов
  синхронизируется отсюда (см. ниже).
- Общие правила Hermes (`AGENTS.md` в корне и в каталогах) действуют и здесь.

## Версия и база upstream

| | |
|---|---|
| Текущий релиз форка | `v0.22.5-bifrost.8` (коммит `d13a83e42d`, 2026-11-01) |
| База upstream | релиз **v0.22.5** + `NousResearch/main` до `9bba78efa5` (2026-10-31) |
| Последний релиз upstream | `v0.22.5` (2026-10-22) |
| Отставание от `upstream/main` | 43 коммита (на 2026-11-01) |
| Коммитов форка поверх базы | 118 (без merge-коммитов) |

Таблица обновляется при каждой синхронизации с upstream. Проверить состояние на сейчас:

```bash
git fetch upstream --tags
```

```bash
git describe --tags --abbrev=0 --exclude='*canary*' --exclude='*bifrost*' $(git merge-base HEAD upstream/main)
```

```bash
git rev-list --left-right --count upstream/main...HEAD
```

Версия, которую видит пользователь (`hermes --version`, «О программе» в Desktop), имеет вид
`0.22.5-bifrost.8[+N]`: база upstream плюс номер релиза форка (`hermes_cli/version_info.py`).
`base_version` при этом остаётся upstream-ной, поэтому проверки совместимости не меняются.

## Основные отличия от оригинального Hermes

### 1. Bifrost Gateway — один ключ `sk-bf-*` на все сервисы

Пять встроенных плагинов направляют все сервисы на шлюз `https://router.rove-ai.ru/v1`:

| Плагин | Что даёт |
|---|---|
| `plugins/model-providers/bifrost` | LLM-провайдер `bifrost` (по умолчанию модель `auto` — маршрутизацию выбирает шлюз) |
| `plugins/image_gen/bifrost` | генерация изображений |
| `plugins/web/bifrost` | веб-поиск и чтение страниц |
| `plugins/transcription/bifrost` | распознавание речи (STT) |
| `plugins/tts/bifrost` | синтез речи (TTS) |

- Ключ: `BIFROST_API_KEY`, адрес шлюза: `BIFROST_BASE_URL` (в `.env`). Ключ берётся из профиля,
  который обслуживает запрос, а не из окружения процесса.
- `hermes_cli/bifrost_edition.py` один раз на профиль настраивает все сервисы на Bifrost и удаляет
  старые копии плагинов из `$HERMES_HOME/plugins/` (они перекрывали встроенные). Запускается
  установщиком (стадия `bifrost-plugins`), первым запуском Desktop и после `hermes update`.
- Плагины правятся **только в этом дереве**. Отдельный репозиторий
  [temga/hermes-plugin-bifrost-gateway](https://github.com/temga/hermes-plugin-bifrost-gateway)
  (для обычного Hermes) синхронизируется отсюда: `scripts/bifrost/sync_plugin_pack.py`.

### 2. Онбординг и Desktop

- В первом запуске и в «Настройки → Провайдеры» есть выделенная строка Bifrost: ввод ключа,
  проверка через `/v1/models`, обращение к сотрудникам Ростелекома и Wink.
- Nous Portal показан обычной строкой провайдера, без пометки «рекомендуется»; на форме ключа
  выбранного провайдера его нет.
- Шаг выбора языка; рекомендуемая модель по умолчанию — та, что реально доступна ключу.
- Первый запуск гида включается из `config.yaml` и стартует, как только подключён провайдер.
- Ссылка на заметки о релизе в «О программе» ведёт в репозиторий форка.
- Переводы новых строк для всех языков Desktop.

### 3. Телеметрия отключена

`SHARED_METRICS_DISABLED = True` в `hermes_cli/observability/shared_metrics_send_config.py`:
ничего не собирается и не отправляется в Nous, что бы ни было в `config.yaml`, и ни CLI, ни Desktop,
ни дашборд не предлагают согласиться на сбор. В тестах флаг выключается (`tests/conftest.py`),
чтобы upstream-тесты конвейера метрик продолжали работать после каждой синхронизации.

### 4. Работа из России: зеркало Skills Hub

`skills.hub_url` в `config.yaml` указывает на зеркало Skills Hub, когда
`hermes-agent.nousresearch.com` недоступен (геоблокировка CDN). Используется и поиском навыков
в CLI, и каталогом в Desktop. Документировано в `website/docs/user-guide/configuration.md`.

### 5. Обновления идут из форка

- `updates.branch` (по умолчанию `main`) — ветка, с которой `hermes update` и все проверки
  обновлений сравнивают установку. Форк выпускается из своей `main`.
- `scripts/install.sh` / `scripts/install.ps1` по умолчанию клонируют `temga/hermes-agent`.
- `--channel stable` на форке запрещён: стабильный канал разрешает релизы upstream и поставил бы
  версию без изменений Bifrost.
- Старые установки следят за веткой `bifrost-edition` — это автоматическое зеркало `main`
  (`.github/workflows/bifrost-edition-mirror.yml`), вручную её не трогаем.

### 6. Установщики и CI

- **Hermes Setup — Bifrost Edition**: лёгкий установщик на Tauri (`apps/bootstrap-installer`),
  macOS DMG (universal, подписан Developer ID и нотаризован) и Windows EXE. Собирается
  `.github/workflows/desktop-setup-tauri-bifrost.yml` на self-hosted раннерах по тегу
  `v<upstream>-bifrost.<N>`. Описание для релиза: `.github/release-notes/bifrost-setup.md`.
- Стадия установки `bifrost-plugins` (между `products` и `setup`) в обоих скриптах установки.
- Windows: совместимость `install.ps1` с PowerShell 5.1, пути с не-ASCII символами сворачиваются
  в короткую форму 8.3.
- После каждого push в `main` теги релизов upstream зеркалируются в форк, чтобы версия
  определялась правильно.
- Наследие RU Edition (август 2026): `desktop-setup-tauri-ru.yml` (теги `v*-ru-setup.*`),
  сабмодуль `apps/desktop/resources/ru-plugins`, `ru-plugins-bootstrap.ts`. Больше не
  используется — его заменил Bifrost Edition.

### 7. Изменённые файлы ядра

Если при синхронизации с upstream возник конфликт, он почти наверняка в одном из этих мест:

- `hermes_cli/version_info.py` — номер релиза форка в версии;
- `hermes_cli/config_defaults.py`, `hermes_cli/config.py` — `updates.branch`, `skills.hub_url`;
- `hermes_cli/observability/shared_metrics_*.py` — отключение телеметрии;
- `hermes_cli/web_routers/models.py`, `config_env.py`, `oauth.py` — рекомендуемая модель,
  ключ Bifrost в онбординге;
- `hermes_cli/main.py`, `update_cmd_maint.py`, `source_check.py`, `banner.py` — ветка обновлений,
  очистка старых копий плагинов;
- `tools/skills_hub_search.py`, `tui_gateway/methods_config.py` — зеркало Skills Hub;
- `scripts/install.sh`, `scripts/install.ps1`, `scripts/build/electron-runtime.mjs`;
- `apps/desktop/src/components/onboarding/*`, `apps/desktop/src/store/onboarding*.ts`,
  `apps/desktop/src/app/settings/providers-settings.tsx`, `apps/desktop/electron/main.ts`;
- `README.md`, `AGENTS.md`, `plugins/AGENTS.md` — ссылки на этот файл. Корневой `AGENTS.md`
  упирается в лимит цепочки 30k символов (`scripts/ci/check_agents_md_size.py`): если upstream
  его вырастит, ссылку оставить, а длинный текст держать здесь. Сейчас ради лимита из последней
  строки корневого `AGENTS.md` убрано упоминание навыка `hermes-agent-dev` (в форк он не входит).

Полный список: `git diff --stat $(git merge-base HEAD upstream/main) HEAD`.

## Ветки и релизы

| Ветка | Назначение |
|---|---|
| `main` (локально `main-bifrost`) | релизная ветка форка; push в неё видят все клиенты как «доступно обновление» |
| `bifrost-next` | невыпущенные изменения; вливается в `main` только при подготовке релиза |
| `feat/…`, `fix/…` | отдельная ветка на каждую задачу, вливается в `bifrost-next` |
| `sync/upstream-<дата>` | синхронизация с upstream; после проверки `bifrost-next` перематывается на неё |
| `bifrost-edition` | авто-зеркало `main` для старых установщиков, вручную не трогать |

Релиз: влить `bifrost-next` в `main`, поставить аннотированный тег `v<upstream>-bifrost.<N>`
(N продолжает счёт при смене базы: `bifrost.6` на 0.21.5, `bifrost.7`–`bifrost.8` на 0.22.5) и
отправить тег — это запускает сборку установщиков. После синхронизации отправить в форк теги
релизов upstream (`v0.22.x`; теги `+canary.*` не отправлять).

## Синхронизация с upstream

1. `git fetch upstream --tags`, создать `sync/upstream-<дата>` от `bifrost-next`.
2. `git merge upstream/main`, разрешить конфликты (см. «Изменённые файлы ядра»).
3. Прогнать `python scripts/check` и `scripts/run_tests.sh`; часть тестов падает и на чистом
   upstream в этом окружении — сравнивать с базой upstream, прежде чем считать что-то регрессией.
4. Перемотать `bifrost-next` на `sync/upstream-<дата>` (fast-forward) и обновить таблицу «Версия и база upstream» выше.
