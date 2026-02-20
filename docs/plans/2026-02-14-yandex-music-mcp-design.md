# Yandex Music MCP Server Design

## Goal

Create a FastMCP server from the Yandex Music OpenAPI spec and mount it into the existing FastAPI application at `/mcp`.

## Approach

**FastMCP.from_openapi()** with the community Yandex Music OpenAPI YAML spec, filtered via RouteMap to expose only DJ-relevant endpoints as MCP tools.

## Architecture

```text
app/mcp/
├── __init__.py                    # re-export
└── yandex_music/
    ├── __init__.py                # re-export create_yandex_music_mcp
    ├── server.py                  # FastMCP.from_openapi() + RouteMap + httpx client
    └── config.py                  # route map patterns, mcp_names mapping
data/
└── yandex-music.yaml              # OpenAPI spec (downloaded from GitHub)
```

### Data flow

```text
LLM/Client → /mcp (Streamable HTTP) → FastMCP → httpx.AsyncClient → api.music.yandex.net
```

## File changes

### New files

- `app/mcp/yandex_music/__init__.py` — re-export `create_yandex_music_mcp`
- `app/mcp/yandex_music/server.py` — MCP server factory
- `app/mcp/yandex_music/config.py` — RouteMap configuration
- `data/yandex-music.yaml` — OpenAPI spec
- `tests/mcp/test_yandex_music.py` — unit tests

### Modified files

- `app/config.py` — add `yandex_music_token: str`
- `app/main.py` — mount MCP via `combine_lifespans` + `app.mount("/mcp", ...)`
- `app/mcp/__init__.py` — update re-exports

### Deleted files

- `app/clients/yandex_music.py` — replaced by MCP server
- `app/mcp/__pycache__/` — stale artifacts

## Endpoint filtering

### Included (DJ-relevant)

| Pattern | Endpoints |
|---------|-----------|
| `/tracks/` | getTracks, getDownloadInfo, getTrackSupplement, getSimilarTracks, getTrackLyrics |
| `/albums/` | getAlbumById, getAlbumsWithTracks, getAlbumsByIds |
| `/artists/` | getPopularTracks, getArtistTracks, artist direct-albums, artist brief-info |
| `/search` | search |
| `/users/.*/playlists/` | getPlayLists, getPlaylistById, createPlaylist, changePlaylistTracks, etc. |
| `/playlists/` | getPlaylistsByIds |
| `/genres` | getGenres |
| `/tags/` | getPlaylistsIdsByTag |

### Excluded

`/account/`, `/feed/`, `/landing3/`, `/rotor/`, `/queues/`, `/settings`, `/permission-alerts`, `/token`, `/play-audio`, `/non-music/`

## Tool naming

Map `operationId` to snake_case via `mcp_names`:
- `getTracks` → `get_tracks`
- `getDownloadInfo` → `get_track_download_info`
- `search` → `search_yandex_music`
- etc.

## Authentication

OAuth token from `settings.yandex_music_token` → `httpx.AsyncClient(headers={"Authorization": "OAuth {token}"})`.

## FastAPI integration

```python
# app/main.py
from fastmcp.utilities.lifespan import combine_lifespans
from app.mcp.yandex_music import create_yandex_music_mcp

def create_app() -> FastAPI:
    mcp = create_yandex_music_mcp()
    mcp_app = mcp.http_app(path="/mcp")

    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
    )
    application.mount("/mcp", mcp_app)
    apply_middleware(application)
    register_error_handlers(application)
    register_routers(application)
    return application
```

## Error handling

- httpx errors (timeout, connection) propagate as MCP tool errors
- 401/403 from Yandex API surface with clear "invalid token" message
- Invalid spec = startup failure (fail fast)

## Testing

- `tests/mcp/test_yandex_music.py`:
  - `create_yandex_music_mcp()` returns `FastMCP` instance
  - Filtered tools contain only DJ-relevant endpoints
  - Excluded endpoints (account, feed, rotor) are absent
- No real HTTP calls — configuration-only verification
