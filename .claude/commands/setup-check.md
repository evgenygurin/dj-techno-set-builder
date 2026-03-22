---
description: "Проверить окружение: DB, MCP, env vars, deps"
allowed-tools: ["Bash", "Read"]
---

# Setup Check

Проверь что окружение настроено правильно для работы с проектом.

## Проверки

```bash
echo "=== 1. Environment Variables ==="
set -a; source .env 2>/dev/null; set +a
[ -n "$DJ_DB_PATH" ] && echo "✅ DJ_DB_PATH=$DJ_DB_PATH" || echo "❌ DJ_DB_PATH не установлен"
[ -f "$DJ_DB_PATH" ] && echo "✅ DB файл существует" || echo "❌ DB файл не найден: $DJ_DB_PATH"
[ -n "$YANDEX_MUSIC_TOKEN" ] && echo "✅ YANDEX_MUSIC_TOKEN установлен" || echo "⚠️ YANDEX_MUSIC_TOKEN не установлен (YM tools не будут работать)"

echo ""
echo "=== 2. Python Dependencies ==="
uv run python -c "import fastmcp; print(f'✅ fastmcp {fastmcp.__version__}')" 2>/dev/null || echo "❌ fastmcp не установлен (uv sync --all-extras)"
uv run python -c "import app; print('✅ app importable')" 2>/dev/null || echo "❌ app не импортируется"

echo ""
echo "=== 3. MCP Server ==="
curl -sf http://localhost:9100/mcp > /dev/null 2>&1 && echo "✅ MCP dev-сервер на :9100" || echo "⚠️ MCP dev-сервер не запущен (make mcp-dev)"

echo ""
echo "=== 4. Database Schema ==="
sqlite3 "$DJ_DB_PATH" "SELECT COUNT(*) FROM tracks;" 2>/dev/null && echo "✅ DB доступна" || echo "❌ DB недоступна"

echo ""
echo "=== 5. Lint & Tests ==="
uv run ruff check app/ --quiet 2>/dev/null && echo "✅ ruff check passed" || echo "⚠️ ruff check issues"
uv run pytest tests/test_health.py -q 2>/dev/null && echo "✅ health test passed" || echo "❌ health test failed"

echo ""
echo "=== 6. iCloud DB Check ==="
python3 -c "
import os, pathlib
p = pathlib.Path(os.environ.get('DJ_DB_PATH', ''))
if p.exists():
    st = p.stat()
    ratio = (st.st_blocks * 512) / st.st_size if st.st_size > 0 else 0
    status = '✅ local' if ratio >= 0.9 else '❌ iCloud stub'
    print(f'{status} (blocks ratio: {ratio:.2f})')
else:
    print('❌ DB не найдена')
" 2>/dev/null
```

Если что-то ❌ — исправь перед работой.
