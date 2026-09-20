#!/usr/bin/env bash
# lane.sh — запуск одной дорожки на общей машине.
# Кладётся в ~/hack/lane.sh, chmod +x.
#
#   ~/hack/lane.sh a                 интерактивная сессия Codex дорожки A (профиль hack)
#   ~/hack/lane.sh b --safe          сессия в режиме только чтение (ревью, разбор)
#   ~/hack/lane.sh c --exec          безголовый прогон кикофф-промпта с логом
#   ~/hack/lane.sh b --exec "текст"  безголовый прогон произвольного промпта
#   ~/hack/lane.sh a --shell         просто оболочка в каталоге дорожки, без Codex
#   ~/hack/lane.sh c --account a     та же дорожка, но аккаунт Codex другой (кончилась квота)
#
# Дорожка определяет: каталог кода, аккаунт Codex, аккаунт GitLab (через remote-алиас),
# порт Streamlit и метку в приглашении оболочки.

set -euo pipefail

LANE="${1:-}"
shift || true
case "$LANE" in
  a|b|c) ;;
  *) echo "Использование: lane.sh {a|b|c} [--safe|--exec [\"промпт\"]|--shell] [--account {a|b|c}]"; exit 1 ;;
esac

HACK_DIR="$HOME/hack"
DIR="$HACK_DIR/$LANE"
ACCOUNT="$LANE"
MODE="interactive"
PROMPT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --safe)    MODE="safe" ;;
    --shell)   MODE="shell" ;;
    --exec)    MODE="exec"; if [ $# -gt 1 ] && [[ "$2" != --* ]]; then PROMPT="$2"; shift; fi ;;
    --account) ACCOUNT="$2"; shift ;;
    *) echo "неизвестный аргумент: $1"; exit 1 ;;
  esac
  shift
done

[ -d "$DIR/.git" ] || { echo "нет рабочей копии $DIR — сначала setup-solo.sh"; exit 1; }
export CODEX_HOME="$HOME/.codex-$ACCOUNT"
[ -f "$CODEX_HOME/auth.json" ] || { echo "нет авторизации в $CODEX_HOME — выполните CODEX_HOME=$CODEX_HOME codex login"; exit 1; }

case "$LANE" in
  a) PORT=8501; ROLE="Ядро и контракт   (core/ eval/)" ;;
  b) PORT=8502; ROLE="Данные и извлечение (data/ extract/)" ;;
  c) PORT=8503; ROLE="Правила и витрина  (rules/ ui/)" ;;
esac
export STREAMLIT_SERVER_PORT="$PORT"

cd "$DIR"
# shellcheck disable=SC1091
[ -f "$HOME/.venvs/hack/bin/activate" ] && source "$HOME/.venvs/hack/bin/activate"

UPPER="$(echo "$LANE" | tr '[:lower:]' '[:upper:]')"
GIT_USER="$(git config user.email || echo 'НЕ ЗАДАН')"
REMOTE="$(git remote get-url origin 2>/dev/null || echo '—')"

printf '\n\033[1;44m  ДОРОЖКА %s  \033[0m  %s\n' "$UPPER" "$ROLE"
printf '  каталог:  %s\n' "$DIR"
printf '  Codex:    CODEX_HOME=%s\n' "$CODEX_HOME"
printf '  GitLab:   %s  (автор коммитов: %s)\n' "$REMOTE" "$GIT_USER"
printf '  Streamlit порт: %s\n\n' "$PORT"

[ "$GIT_USER" = "НЕ ЗАДАН" ] && printf '\033[33m!  не задан git user.email в этой копии — коммиты уйдут не от того автора\033[0m\n\n'

case "$MODE" in
  shell)
    export PS1="\[\033[1;44m\] LANE $UPPER \[\033[0m\] \w \$ "
    exec "$SHELL" -i
    ;;
  safe)
    exec codex -p safe
    ;;
  exec)
    mkdir -p "$HACK_DIR/logs"
    if [ -z "$PROMPT" ]; then
      PFILE="$HACK_DIR/prompts/kickoff-$LANE.txt"
      [ -f "$PFILE" ] || { echo "нет файла промпта $PFILE"; exit 1; }
      PROMPT="$(cat "$PFILE")"
    fi
    LOG="$HACK_DIR/logs/$LANE-$(date +%H%M%S).log"
    echo "лог: $LOG"
    echo "остановить: Ctrl-C;  продолжить потом: CODEX_HOME=$CODEX_HOME codex exec resume --last \"...\""
    exec codex exec --full-auto "$PROMPT" 2>&1 | tee "$LOG"
    ;;
  *)
    exec codex -p hack
    ;;
esac
