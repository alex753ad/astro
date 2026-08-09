#!/usr/bin/env bash
#
# Удаляет утёкшие секреты из ВСЕЙ истории git.
# Запускать ОДИН РАЗ, в свежем зеркальном клоне, после того как код-патч применён.
#
# Требуется git-filter-repo:
#   pip install git-filter-repo    (или: brew install git-filter-repo)
#
# ── Что изменилось со времени первого запуска ────────────────────────────────
# Первый прогон вычистил env, log.json, astro_search.session и др. Но
# .env.example тронут не был, а в нём коммитились НАСТОЯЩИЕ значения:
#   9690bab (initial commit)  OPENAI_API_KEY=sk-proj-… — рабочий ключ
#   c086efa ("security: … JWT rotation")  JWT_SECRET=ZKT87rW7BXK5…
# Оба коммита — предки origin/main, то есть лежат на GitHub и читаются
# через git log -p, GitHub API и любой форк.
#
# .env.example удалять из истории целиком нельзя — это полезный файл, который
# нужен в текущем дереве. Поэтому здесь --replace-text: значения заменяются на
# заглушку, а файл остаётся.
#
set -euo pipefail

REPLACEMENTS_FILE="$(mktemp)"
trap 'rm -f "$REPLACEMENTS_FILE"' EXIT

echo "==> Проверяю git-filter-repo..."
if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo не найден. Установи: pip install git-filter-repo"
  exit 1
fi

echo "==> Проверяю, что это зеркальный клон, а не рабочая копия..."
# filter-repo отказывается работать в репозитории с несохранёнными изменениями,
# но лучше сказать об этом внятно заранее.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "В рабочем дереве есть изменения. Закоммить или спрячь их, потом запускай."
  exit 1
fi

# ---------------------------------------------------------------------------
# Список утёкших значений. Регулярки вида regex:… ловят ключи целиком, чтобы не
# перечислять каждый вручную; литералы — то, что уже точно известно.
#
# ВАЖНО: этот файл сам содержит утёкшие значения, поэтому он создаётся во
# временном каталоге и удаляется по выходу. Не коммить его.
# ---------------------------------------------------------------------------
cat > "$REPLACEMENTS_FILE" <<'EOF'
regex:sk-proj-[A-Za-z0-9_\-]{20,}==><REDACTED-OPENAI-KEY>
regex:sk-[A-Za-z0-9]{32,}==><REDACTED-API-KEY>
regex:sk_live_[A-Za-z0-9]{16,}==><REDACTED-STRIPE-KEY>
regex:whsec_[A-Za-z0-9]{16,}==><REDACTED-STRIPE-WEBHOOK>
regex:re_[A-Za-z0-9_]{16,}==><REDACTED-RESEND-KEY>
regex:[0-9]{8,10}:AA[A-Za-z0-9_\-]{30,}==><REDACTED-TELEGRAM-TOKEN>
regex:GOCSPX-[A-Za-z0-9_\-]{20,}==><REDACTED-GOOGLE-SECRET>
ZKT87rW7BXK5AxBBZkb18sxS7Kfl25FbVS8W1l82z5B887UnxiPllffPL9n8pMP0ac7b7o0V738QY0lQvwMQsQ==><REDACTED-JWT-SECRET>
EOF

echo "==> Удаляю секретные файлы из всей истории..."
git filter-repo --force --invert-paths \
  --path env \
  --path log.json \
  --path astro_search.session \
  --path 54.txt \
  --path comit.txt \
  --path auth_router_temp.txt

echo "==> Затираю утёкшие значения (в т.ч. в .env.example)..."
git filter-repo --force --replace-text "$REPLACEMENTS_FILE"

echo "==> Проверяю, что в истории ничего не осталось..."
if git grep -qI "ZKT87rW7BXK5AxBBZkb18sxS7Kfl" $(git rev-list --all) -- 2>/dev/null; then
  echo "!! JWT_SECRET всё ещё встречается в истории — разбирайся прежде, чем пушить."
  exit 1
fi
echo "   чисто"

cat <<'EOF'

==> Готово локально. Дальше — force-push (перезапишет историю на GitHub):
      git push origin --force --all
      git push origin --force --tags

ВАЖНО, по убыванию значимости:

1. Ротация ключей — обязательна и НЕ отменяется этой чисткой. Всё, что здесь
   перечислено, считается скомпрометированным с момента публикации:
   OpenAI, Anthropic, DeepSeek, Resend, Robokassa Password1/Password2,
   Google OAuth secret, Telegram bot token, JWT_SECRET, пароль Postgres.

2. GitHub хранит «висячие» объекты в форках и в кэше веб-интерфейса даже после
   force-push: старый коммит остаётся доступен по прямой ссылке на SHA.
   Открыть тикет в GitHub Support с просьбой удалить unreachable-объекты,
   либо (надёжнее) удалить репозиторий и создать заново из чистого состояния.

3. Все, кто клонировал репозиторий, должны сделать clone заново — обычный
   git pull после переписанной истории даёт конфликт на каждом коммите.

4. Локальные worktree в .claude/worktrees/ содержат СВОИ копии .env.example со
   старым секретом. Их надо удалить или пересоздать: иначе мердж такой ветки
   вернёт значение обратно в main.

5. Включить в настройках репозитория: Secret Scanning + Push Protection
   (Settings → Code security). В CI это уже закрыто джобой gitleaks.
EOF
