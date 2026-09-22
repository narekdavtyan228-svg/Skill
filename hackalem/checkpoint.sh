#!/usr/bin/env bash
# checkpoint.sh — часовая (или любая) отчётность по ходу хакатона.
#
# Кладётся в корень репозитория (владелец — роль A), chmod +x.
#
#   ./checkpoint.sh start           зафиксировать T+0 (делается один раз, когда объявили старт)
#   ./checkpoint.sh                 сделать срез прямо сейчас: печать + docs/status/T+NNN.md
#   ./checkpoint.sh --quick         без запуска тестов (за 3 секунды, для промежуточных взглядов)
#   ./checkpoint.sh --loop 60       автоматически каждые 60 минут, пока не остановите (Ctrl-C)
#   ./checkpoint.sh --commit        дополнительно закоммитить и запушить отчёт
#
# Что показывает: сколько прошло и осталось, в какой фазе таймлайна вы должны быть,
# кто что закоммитил за последний час, состояние трёх ворот приёмки, размер датасета,
# открытые запросы между ролями и список того, что ещё не закрыто по критериям жюри.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

T0_FILE="$REPO/.hack-t0"
STATUS_DIR="$REPO/docs/status"
TOTAL_MIN=300          # длительность хакатона
WINDOW="1 hour ago"    # окно для git-активности

QUICK=0; COMMIT=0; LOOP=0
case "${1:-}" in
  start)
    date +%s > "$T0_FILE"
    echo "T+0 зафиксирован: $(date '+%H:%M'). Финиш в $(date -d "+${TOTAL_MIN} minutes" '+%H:%M' 2>/dev/null || date -v+${TOTAL_MIN}M '+%H:%M')"
    echo "Добавьте .hack-t0 в .gitignore или закоммитьте — как удобнее."
    exit 0 ;;
esac
while [ $# -gt 0 ]; do
  case "$1" in
    --quick)  QUICK=1 ;;
    --commit) COMMIT=1 ;;
    --loop)   LOOP="${2:-60}"; shift ;;
    *) echo "неизвестный аргумент: $1"; exit 1 ;;
  esac
  shift
done

c_red()  { printf '\033[31m%s\033[0m' "$1"; }
c_grn()  { printf '\033[32m%s\033[0m' "$1"; }
c_yel()  { printf '\033[33m%s\033[0m' "$1"; }

phase_for() {  # минута -> ожидаемая фаза
  local m=$1
  if   [ "$m" -lt 15  ]; then echo "T+0…15 · разбор формулировки, AGENTS.md, запуск трёх сессий"
  elif [ "$m" -lt 45  ]; then echo "T+15…45 · каркас на заглушках; ЦЕЛЬ ЧЕКПОИНТА 1: make smoke зелёный"
  elif [ "$m" -lt 90  ]; then echo "T+45…90 · контракт ЗАМОРОЖЕН; извлечение и правила по существу"
  elif [ "$m" -lt 120 ]; then echo "T+90…120 · ЧЕКПОИНТ 2 пройден: извлечение работает на реальном комплекте"
  elif [ "$m" -lt 150 ]; then echo "T+120…150 · первый честный eval; ЦЕЛЬ: recall >= 0.8, ложных approve 0"
  elif [ "$m" -lt 210 ]; then echo "T+150…210 · полировка демо, replay-режим, ловушечный комплект"
  elif [ "$m" -lt 240 ]; then echo "T+210…240 · слайды, схема, резервное видео. ВПЕРЕДИ CODE FREEZE"
  elif [ "$m" -lt 270 ]; then echo "T+240…270 · CODE FREEZE. Только репетиции питча"
  else                        echo "T+270…300 · буфер и сдача"
  fi
}

gate() {  # имя, команда -> строка статуса
  local name="$1"; shift
  if timeout 300 bash -c "$*" >/tmp/gate.$$ 2>&1; then
    echo "  [$(c_grn OK)]   $name"
  else
    echo "  [$(c_red FAIL)] $name"
    sed -n '1,6p' /tmp/gate.$$ | sed 's/^/         /'
  fi
  rm -f /tmp/gate.$$
}

report() {
  local now elapsed remain stamp
  now=$(date +%s)
  if [ -f "$T0_FILE" ]; then
    elapsed=$(( (now - $(cat "$T0_FILE")) / 60 ))
  else
    elapsed=-1
  fi
  remain=$(( TOTAL_MIN - elapsed ))
  stamp=$(date '+%H:%M')

  echo
  echo "================= ЧЕКПОИНТ $stamp ================="
  if [ "$elapsed" -ge 0 ]; then
    printf 'Прошло: T+%s мин   Осталось: ' "$elapsed"
    if [ "$remain" -lt 45 ]; then c_red "$remain мин"; elif [ "$remain" -lt 90 ]; then c_yel "$remain мин"; else c_grn "$remain мин"; fi
    echo
    echo "Должны быть здесь: $(phase_for "$elapsed")"
  else
    echo "T+0 не зафиксирован. Запустите: ./checkpoint.sh start"
  fi

  echo
  echo "--- Активность за последний час -------------------"
  git fetch -q origin 2>/dev/null || echo "  (не удалось получить origin — работаем по локальной истории)"
  local ref; ref=$(git rev-parse --verify -q origin/main >/dev/null && echo origin/main || echo HEAD)
  local n; n=$(git log "$ref" --since="$WINDOW" --oneline 2>/dev/null | wc -l | tr -d ' ')
  echo "  Коммитов: $n"
  if [ "$n" -gt 0 ]; then
    git log "$ref" --since="$WINDOW" --pretty='    %an: %s' | head -20
    echo "  Затронутые области:"
    git log "$ref" --since="$WINDOW" --name-only --pretty=format: \
      | grep -v '^$' | cut -d/ -f1 | sort | uniq -c | sort -rn | head -8 | sed 's/^/    /'
  else
    echo "  $(c_yel 'Ни одного коммита за час — либо агенты буксуют, либо кто-то не пушит.')"
  fi
  echo "  Последние коммиты по авторам:"
  git log "$ref" --pretty='%an|%ar|%s' | awk -F'|' '!seen[$1]++ {printf "    %-22s %-14s %s\n", $1, $2, $3}' | head -5

  echo
  echo "--- Ворота приёмки --------------------------------"
  if [ "$QUICK" = 1 ]; then
    echo "  (пропущено: --quick)"
  else
    [ -f Makefile ] && grep -q '^smoke:' Makefile && gate "make smoke   (сквозной прогон)" "make smoke" || echo "  [$(c_yel 'н/д')]  цели smoke в Makefile ещё нет"
    [ -f eval/run.py ] && gate "python -m eval.run (метрики)" "python -m eval.run" || echo "  [$(c_yel 'н/д')]  eval/run.py ещё нет"
    [ -d tests ] || ls test_*.py >/dev/null 2>&1 && gate "pytest -q" "pytest -q" || echo "  [$(c_yel 'н/д')]  тестов ещё нет"
    [ -f ui/visual_qa.py ] && gate "make ui-qa (браузерная проверка)" "make ui-qa" || echo "  [$(c_yel 'н/д')]  браузерной проверки UI ещё нет"
  fi
  if [ "$QUICK" != 1 ] && [ -f eval/run.py ]; then
    echo "  Последние метрики:"
    timeout 300 python -m eval.run 2>/dev/null | tail -6 | sed 's/^/    /'
  fi

  echo
  echo "--- Датасет ---------------------------------------"
  local fx=0
  [ -d data/fixtures ] && fx=$(find data/fixtures -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ')
  printf '  Комплектов: %s из 60' "$fx"
  [ "$fx" -lt 20 ] && printf '  %s' "$(c_yel '(мало для честного eval)')"
  echo
  if [ -f data/ground_truth.json ]; then
    python3 - <<'PY' 2>/dev/null || echo "  ground_truth.json есть, но не читается как JSON"
import json
d=json.load(open("data/ground_truth.json"))
n=len(d) if isinstance(d,(list,dict)) else 0
print(f"  Эталонных записей в ground_truth.json: {n}")
PY
  else
    echo "  $(c_yel 'ground_truth.json отсутствует — eval не на чем считать')"
  fi

  echo
  echo "--- Запросы между ролями --------------------------"
  if compgen -G "docs/requests/*.md" >/dev/null; then
    grep -HnE ':?\[' docs/requests/*.md 2>/dev/null | grep -E '^\S+:[0-9]+:\[' | tail -12 | sed 's/^/  /' || echo "  нет открытых запросов"
  else
    echo "  пусто"
  fi

  echo
  echo "--- Критерии жюри (проверить глазами) -------------"
  local checks=(
    "prooflinks: у каждого finding есть source_id + location + quote"
    "статусы unknown / insufficient_evidence реально встречаются в выводе"
    "минимум один вызов mock-API за прогон"
    "вся арифметика сроков — в коде, не в промпте"
    "HITL: нет ветки, где система сама разрешает работы"
    "fail-closed: неполные данные дают block_and_escalate"
    "replay-режим: демо в один клик"
    "резервное видео демо записано"
  )
  for c in "${checks[@]}"; do echo "  [ ] $c"; done

  echo
  echo "--- Что сказать вслух на чекпоинте ----------------"
  echo "  Каждый за 40 секунд: зелёный/красный · что делает агент сейчас · чего ждёт от других."
  echo "==================================================="
  echo
}

save() {
  mkdir -p "$STATUS_DIR"
  local elapsed=0
  [ -f "$T0_FILE" ] && elapsed=$(( ($(date +%s) - $(cat "$T0_FILE")) / 60 ))
  local out="$STATUS_DIR/T+$(printf '%03d' "$elapsed").md"
  { echo '```'; report | sed 's/\x1b\[[0-9;]*m//g'; echo '```'; } > "$out"
  echo "Отчёт сохранён: $out"
  if [ "$COMMIT" = 1 ]; then
    git add "$out" >/dev/null 2>&1
    git commit -qm "[A] status: чекпоинт T+$elapsed" >/dev/null 2>&1 && \
    git pull -q --rebase origin main && git push -q origin main && echo "Отчёт запушен." || echo "Пуш отчёта не прошёл — не страшно, продолжайте."
  fi
}

if [ "$LOOP" != 0 ]; then
  echo "Автоотчёт каждые $LOOP минут. Остановить: Ctrl-C."
  while true; do report; save; sleep $(( LOOP * 60 )); done
else
  report
  save
fi
