# MCP Observability Design

> Middleware, logging, telemetry, Sentry, lifespan и storage backends для FastMCP 3.0 сервера.

## Context

FastMCP 3.0.0rc1 сервер с двумя namespace (YM ~30 tools, DJ 12 tools) не имеет:
- Middleware на MCP-уровне
- Структурированного логирования
- Телеметрии (OpenTelemetry)
- Error tracking (Sentry)
- Кеширования ответов
- Настроенного lifespan для MCP

## Decision

**Подход A: Централизованный модуль** `app/mcp/observability.py`.

Вся конфигурация middleware, Sentry и OTEL — в одном модуле.
Gateway вызывает `apply_observability(gateway, settings)`.

Причина: один пользователь, один сервер. Гранулярность подхода C (гибридный)
не нужна — легко рефакторнуть позже.

## Architecture

### File Structure

| Файл | Назначение |
|------|-----------|
| `app/mcp/observability.py` | Sentry init, OTEL setup, middleware стек |
| `app/mcp/lifespan.py` | Lifespan для MCP: cache store init, logging |
| `app/config.py` | Новые settings: sentry, otel, cache, middleware |
| `app/mcp/gateway.py` | Вызов `apply_observability()` + lifespan |
| `app/main.py` | Sentry init до импорта FastMCP |
| `pyproject.toml` | Новые deps: sentry-sdk, opentelemetry-*, py-key-value-aio |

### Middleware Stack (order matters)

```text
Request →  ErrorHandling  →  StructuredLogging  →  DetailedTiming  →  ResponseCaching  →  Retry  →  Ping  → Tool
Response ← ErrorHandling  ←  StructuredLogging  ←  DetailedTiming  ←  ResponseCaching  ←  Retry  ←  Ping  ← Tool
```

| # | Middleware | Конфигурация | Назначение |
|---|-----------|-------------|-----------|
| 1 | `ErrorHandlingMiddleware` | `include_traceback=debug`, callback → Sentry | Ловит ошибки, отправляет в Sentry |
| 2 | `StructuredLoggingMiddleware` | JSON, `include_payload=debug` | JSON логи для парсинга |
| 3 | `DetailedTimingMiddleware` | Default | Per-operation timing |
| 4 | `ResponseCachingMiddleware` | DiskStore, TTL: tools=60s, resources=300s | Кеш ответов на диск |
| 5 | `RetryMiddleware` | `max_retries=3`, `backoff_factor=1.0` | Retry transient errors |
| 6 | `PingMiddleware` | `interval=30` | Keepalive для HTTP/SSE |

### Sentry + OpenTelemetry

```python
# app/main.py — ПЕРЕД импортом FastMCP
sentry_sdk.init(
    dsn=settings.sentry_dsn,
    traces_sample_rate=1.0,
    send_default_pii=True,
    integrations=[MCPIntegration(), FastApiIntegration()],
    environment=settings.environment,
)
```

- Sentry SDK 2.x = OpenTelemetry SDK — spans автоматически в Sentry
- FastMCP подхватывает TracerProvider и создаёт spans для tool/resource/prompt
- Для локального dev: дополнительный SpanProcessor → otel-desktop-viewer

### Lifespan

```python
@lifespan
async def observability_lifespan(server):
    cache_store = DiskStore(directory=settings.mcp_cache_dir)
    logger.info("MCP server starting", extra={"server": server.name})
    try:
        yield {"cache_store": cache_store}
    finally:
        logger.info("MCP server shutting down")
```

### Storage Backend

| Параметр | Значение | Причина |
|----------|---------|---------|
| Backend | `DiskStore` | Один пользователь, персистентность |
| Директория | `./cache/mcp/` | Gitignored |
| Миграция | `DiskStore` → `RedisStore` | Одна строка при деплое в облако |

### Settings (app/config.py)

```python
# Sentry
sentry_dsn: str = ""                    # Пустой = отключен
sentry_traces_sample_rate: float = 1.0
sentry_send_pii: bool = True
environment: str = "development"

# OpenTelemetry
otel_endpoint: str = ""                  # Пустой = нет доп. exporter
otel_service_name: str = "dj-set-builder-mcp"

# MCP Observability
mcp_cache_dir: str = "./cache/mcp"
mcp_cache_ttl_tools: int = 60
mcp_cache_ttl_resources: int = 300
mcp_retry_max: int = 3
mcp_retry_backoff: float = 1.0
mcp_ping_interval: int = 30
mcp_log_payloads: bool = False
```

Каждая фича отключается пустой строкой или 0.

## Dependencies

```toml
# pyproject.toml — новые зависимости
"sentry-sdk[fastapi]>=2.20",
"opentelemetry-api>=1.29",
"opentelemetry-sdk>=1.29",
"opentelemetry-exporter-otlp>=1.29",
# py-key-value-aio уже в fastmcp deps
```

## Key Constraints

1. `sentry_sdk.init()` MUST be called BEFORE importing FastMCP (OTEL TracerProvider order)
2. ErrorHandling middleware MUST be first (catches errors from all subsequent middleware)
3. ResponseCaching MUST be before Retry (cached responses don't trigger retries)
4. DiskStore directory MUST be gitignored
5. `include_payload` in logging MUST be False in production (PII)

## References

- [FastMCP Middleware](https://gofastmcp.com/servers/middleware)
- [FastMCP Logging](https://gofastmcp.com/servers/logging)
- [FastMCP Lifespan](https://gofastmcp.com/servers/lifespan)
- [FastMCP Storage Backends](https://gofastmcp.com/servers/storage-backends)
- [FastMCP Telemetry](https://gofastmcp.com/servers/telemetry)
- [Sentry MCP Integration](https://docs.sentry.io/platforms/python/integrations/mcp/)
