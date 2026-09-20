#!/usr/bin/env bash
# setup-machine.sh — подготовка одной машины к хакатону. Запускать НАКАНУНЕ, не на площадке.
# Использование:  bash setup-machine.sh [путь-к-локальной-копии-ECC]
# Если путь указан — ECC ставится из локального каталога (офлайн-резерв),
# иначе — из GitHub-маркетплейса.

set -euo pipefail
LOCAL_ECC="${1:-}"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mОШИБКА: %s\033[0m\n' "$*" >&2; exit 1; }

say "1/5 Проверка предусловий"
command -v node  >/dev/null || fail "нет Node.js (нужен >= 20)"
command -v python3 >/dev/null || fail "нет Python 3"
command -v git   >/dev/null || fail "нет git"
command -v codex >/dev/null || fail "нет Codex CLI — установите и выполните codex login"
node -v; python3 -V; git --version; codex --version

NODE_MAJOR="$(node -v | sed 's/^v\([0-9]*\).*/\1/')"
[ "$NODE_MAJOR" -ge 18 ] || fail "Node.js $NODE_MAJOR слишком старый, нужен >= 18 (лучше 20+)"

say "2/5 Проверка входа в Codex"
if [ ! -f "${CODEX_HOME:-$HOME/.codex}/auth.json" ]; then
  echo "Не вижу авторизации Codex. Выполните: codex login"
  echo "Затем перезапустите этот скрипт."
  exit 1
fi
echo "Авторизация найдена."

say "3/5 Установка ECC как нативного плагина Codex"
if [ -n "$LOCAL_ECC" ]; then
  [ -d "$LOCAL_ECC" ] || fail "каталог $LOCAL_ECC не найден"
  ECC_SRC="$(cd "$LOCAL_ECC" && pwd)"
  codex plugin marketplace add "$ECC_SRC"
else
  codex plugin marketplace add affaan-m/ECC
fi
codex plugin add ecc@ecc
codex plugin list --json || true

if [ -n "$LOCAL_ECC" ] && [ -f "$ECC_SRC/scripts/codex/check-plugin-cache.js" ]; then
  say "Проверка кэша плагина"
  (cd "$ECC_SRC" && npm install --ignore-scripts --no-audit --no-fund --loglevel=error \
     && node scripts/codex/check-plugin-cache.js) || echo "Проверка кэша не прошла — посмотрите вывод выше."
fi

say "4/5 Python-окружение"
python3 -m venv "$HOME/.venvs/hack"
# shellcheck disable=SC1091
source "$HOME/.venvs/hack/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet openai pydantic streamlit pytest python-dotenv pandas pymupdf pillow fpdf2 pyyaml
echo "Установлено. Активация: source ~/.venvs/hack/bin/activate"
echo "Для задач HaulDispatch / NPT Investigator дополнительно: pip install ortools"

say "5/5 Git"
git config --global user.name  >/dev/null 2>&1 || echo "Задайте: git config --global user.name  \"Имя Фамилия\""
git config --global user.email >/dev/null 2>&1 || echo "Задайте: git config --global user.email \"почта-от-gitlab\""
[ -f "$HOME/.ssh/id_ed25519.pub" ] || echo "SSH-ключа нет. Создайте: ssh-keygen -t ed25519 -C hackalem, затем добавьте в GitLab → Preferences → SSH Keys"

cat <<'EOF'

Готово. Осталось вручную:
  1) перезапустить Codex, зайти в /plugins — ECC должен быть enabled;
  2) один раз выполнить внутри Codex: $configure-ecc
  3) проверить вызов скилла: $tdd-workflow
  4) склонировать общий репозиторий и прогнать репетицию (45–60 минут).

Хуки ECC в Codex на хакатоне НЕ включаем: /hooks оставляем нетронутым.
Легаси-синхронизацию scripts/sync-ecc-to-codex.sh НЕ запускаем — она конфликтует с нативным плагином.
EOF
