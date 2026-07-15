#!/usr/bin/env bash
#
# Удаляет утёкшие секретные файлы из ВСЕЙ истории git.
# Запускать ОДИН РАЗ, в чистой копии репозитория, после того как код-патч уже применён.
#
# Требуется git-filter-repo:
#   pip install git-filter-repo    (или: brew install git-filter-repo)
#
set -e

echo "==> Проверяю git-filter-repo..."
if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo не найден. Установи: pip install git-filter-repo"
  exit 1
fi

echo "==> Удаляю секретные файлы из всей истории..."
git filter-repo --force --invert-paths \
  --path env \
  --path log.json \
  --path astro_search.session \
  --path 54.txt \
  --path comit.txt \
  --path auth_router_temp.txt

echo "==> Готово локально. Теперь force-push (перезапишет историю на GitHub):"
echo "    git remote add origin https://github.com/alex753ad/astro.git   # если remote слетел"
echo "    git push origin --force --all"
echo "    git push origin --force --tags"
echo
echo "ВАЖНО: после этого все, кто клонировал репозиторий, должны сделать заново clone."
echo "И всё равно считай утёкшие ключи скомпрометированными — ротацию (шаг 1 инструкции) не пропускай."
