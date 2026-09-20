#!/usr/bin/env bash
# setup-solo.sh — подготовка ОДНОЙ машины с тремя аккаунтами Codex и тремя аккаунтами GitLab.
# Запускать НАКАНУНЕ хакатона.
#
#   bash setup-solo.sh <ssh-url-репозитория> [путь-к-локальной-копии-ECC]
#
# Пример:
#   bash setup-solo.sh git@gitlab.com:myteam/hackalem-permitguard.git
#   bash setup-solo.sh git@gitlab.com:myteam/hackalem-permitguard.git ~/tools/ECC
#
# Скрипт идемпотентен: существующие ключи, дома и клоны не перезаписываются.

set -euo pipefail

REPO_URL="${1:-}"
LOCAL_ECC="${2:-}"
LANES=(a b c)
HACK_DIR="$HOME/hack"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!  %s\033[0m\n' "$*"; }
fail() { printf '\033[31mОШИБКА: %s\033[0m\n' "$*" >&2; exit 1; }

[ -n "$REPO_URL" ] || fail "укажите SSH-URL репозитория, например git@gitlab.com:team/repo.git"
[[ "$REPO_URL" == git@* ]] || fail "нужен SSH-URL (git@...), а не https"

# Из git@gitlab.com:team/repo.git достаём путь team/repo.git
REPO_PATH="${REPO_URL#*:}"

say "1/6 Проверка предусловий"
for c in node python3 git codex ssh; do command -v "$c" >/dev/null || fail "нет $c"; done
NODE_MAJOR="$(node -v | sed 's/^v\([0-9]*\).*/\1/')"
[ "$NODE_MAJOR" -ge 18 ] || fail "Node.js $NODE_MAJOR слишком старый, нужен >= 18"
command -v tmux >/dev/null || warn "tmux не найден — три дорожки удобнее в панелях tmux"
node -v; python3 -V; git --version; codex --version

say "2/6 Три окружения Codex"
for L in "${LANES[@]}"; do
  H="$HOME/.codex-$L"
  mkdir -p "$H"
  if [ -f "$H/auth.json" ]; then
    echo "  дом $H — авторизация уже есть"
  else
    warn "дом $H без авторизации. Выполните в отдельном терминале:  CODEX_HOME=$H codex login"
    warn "(для каждого дома — СВОЙ аккаунт Codex; второй и третий вход делайте в приватном окне браузера)"
  fi
done

say "3/6 Установка ECC в каждый дом"
if [ -n "$LOCAL_ECC" ]; then
  [ -d "$LOCAL_ECC" ] || fail "каталог $LOCAL_ECC не найден"
  ECC_SRC="$(cd "$LOCAL_ECC" && pwd)"
  (cd "$ECC_SRC" && npm install --ignore-scripts --no-audit --no-fund --loglevel=error)
  MARKET="$ECC_SRC"
else
  MARKET="affaan-m/ECC"
fi
for L in "${LANES[@]}"; do
  H="$HOME/.codex-$L"
  [ -f "$H/auth.json" ] || { warn "пропускаю $H — сначала codex login"; continue; }
  echo "  -> $H"
  CODEX_HOME="$H" codex plugin marketplace add "$MARKET" || warn "marketplace add не прошёл для $H"
  CODEX_HOME="$H" codex plugin add ecc@ecc            || warn "plugin add не прошёл для $H"
done
if [ -n "${ECC_SRC:-}" ] && [ -f "$ECC_SRC/scripts/codex/check-plugin-cache.js" ]; then
  (cd "$ECC_SRC" && node scripts/codex/check-plugin-cache.js) || warn "проверка кэша плагина не прошла"
fi

say "4/6 Три SSH-ключа и хост-алиасы GitLab"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/config" && chmod 600 "$HOME/.ssh/config"
for L in "${LANES[@]}"; do
  KEY="$HOME/.ssh/gl_$L"
  [ -f "$KEY" ] || ssh-keygen -t ed25519 -N "" -f "$KEY" -C "hackalem-$L"
  if grep -q "^Host gitlab-$L$" "$HOME/.ssh/config"; then
    echo "  алиас gitlab-$L уже настроен"
  else
    cat >> "$HOME/.ssh/config" <<EOF

Host gitlab-$L
    HostName gitlab.com
    User git
    IdentityFile $KEY
    IdentitiesOnly yes
EOF
    echo "  добавлен алиас gitlab-$L"
  fi
done
echo
echo "Добавьте КАЖДЫЙ ключ в СВОЙ аккаунт GitLab (Preferences -> SSH Keys):"
for L in "${LANES[@]}"; do echo; echo "--- аккаунт $L ---"; cat "$HOME/.ssh/gl_$L.pub"; done
echo
echo "После добавления проверьте:  ssh -T gitlab-a ; ssh -T gitlab-b ; ssh -T gitlab-c"

say "5/6 Три рабочих копии репозитория"
mkdir -p "$HACK_DIR" "$HACK_DIR/logs" "$HACK_DIR/prompts"
for L in "${LANES[@]}"; do
  DIR="$HACK_DIR/$L"
  if [ -d "$DIR/.git" ]; then
    echo "  $DIR уже существует"
  else
    git clone "git@gitlab-$L:$REPO_PATH" "$DIR" || { warn "клон дорожки $L не удался (добавлен ли ключ в GitLab?)"; continue; }
  fi
  git -C "$DIR" remote set-url origin "git@gitlab-$L:$REPO_PATH"
  echo "  задайте идентичность дорожки $L:"
  echo "    git -C $DIR config user.name \"Имя $L\" && git -C $DIR config user.email \"почта-$L\""
done

say "6/6 Python-окружение"
if [ -d "$HOME/.venvs/hack" ]; then
  echo "  ~/.venvs/hack уже есть"
else
  python3 -m venv "$HOME/.venvs/hack"
fi
# shellcheck disable=SC1091
source "$HOME/.venvs/hack/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet openai pydantic streamlit pytest python-dotenv pandas pymupdf pillow fpdf2 pyyaml
echo "  готово. Для HaulDispatch / NPT Investigator дополнительно: pip install ortools"

cat <<EOF

Осталось вручную:
  1) codex login в тех домах, где его не было (см. предупреждения выше);
  2) добавить три публичных ключа в три аккаунта GitLab и проверить ssh -T gitlab-{a,b,c};
  3) задать git user.name / user.email в каждой копии (команды напечатаны выше);
  4) в каждом доме один раз: CODEX_HOME=~/.codex-X codex  ->  /plugins (ECC enabled)  ->  \$configure-ecc
  5) положить lane.sh в $HACK_DIR и chmod +x;
  6) сохранить кикофф-промпты в $HACK_DIR/prompts/kickoff-{a,b,c}.txt;
  7) прогнать репетицию на 45 минут во всех трёх дорожках одновременно.

Хуки ECC в Codex не включаем. scripts/sync-ecc-to-codex.sh не запускаем.
EOF
