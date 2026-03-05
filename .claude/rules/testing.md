---
paths:
  - "tests/**"
---

# Testing Conventions

## Framework

- **pytest** + **pytest-asyncio** with `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed on async tests
- **httpx** `AsyncClient` with `ASGITransport` for API integration tests
- **In-memory SQLite** for all tests — fast, isolated, no cleanup needed

## Fixtures (`tests/conftest.py`)

3 core async fixtures:

- **`engine`** — in-memory SQLite with `create_all`/`drop_all` lifecycle
- **`session`** — async session with `expire_on_commit=False` (objects stay valid after commit)
- **`client`** — httpx `AsyncClient` with `dependency_overrides[get_session]` for API tests

```python
@pytest.fixture
async def client(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session():
        async with factory() as sess:
            yield sess

    application = create_app()
    application.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

## Critical import

**`from app.models import Base`** (not `from app.models.base`) — this import triggers all model registrations so `create_all()` sees every table. Without it, SQLite test DB will be empty.

## Test organization

```text
tests/
├── conftest.py                    # Shared fixtures (engine, session, client)
├── test_tracks.py                 # Track CRUD API tests
├── test_artists.py                # Artist CRUD API tests
├── test_playlists.py              # Playlist API tests
├── test_sets.py                   # DJ set API tests
├── test_transitions.py            # Transition API tests
├── test_transition_scoring.py     # TransitionScoringService unit tests
├── test_track_analysis.py         # TrackAnalysisService tests
├── test_sections_api.py           # Sections API tests
├── integration/
│   └── test_yandex_enrich_flow.py # Integration with YM client
├── utils/
│   ├── conftest.py                # Synthetic audio fixtures (WAV generation)
│   ├── test_bpm.py                # BPM detection tests
│   ├── test_beats.py              # Beat detection tests
│   ├── test_energy.py             # Energy analysis tests
│   ├── test_groove.py             # Groove analysis tests
│   ├── test_key_detect.py         # Key detection tests
│   ├── test_loudness.py           # Loudness measurement tests
│   └── test_spectral.py           # Spectral analysis tests
└── mcp/
    ├── conftest.py                # MCP fixtures (workflow_mcp, gateway_mcp, ym_mcp, workflow_mcp_with_db)
    ├── test_client_integration.py # In-memory Client tests (ping, call_tool, errors)
    ├── test_workflow_analysis.py   # Analysis tool registration tests
    ├── test_workflow_delivery.py   # deliver_set tool tests (unit + integration)
    ├── test_workflow_discovery.py
    ├── test_workflow_export.py
    ├── test_workflow_import.py
    ├── test_workflow_setbuilder.py
    ├── test_dependencies.py       # DI providers + Pydantic types importability
    ├── test_gateway.py            # Gateway composition tests
    ├── test_prompts.py            # Prompt registration + rendering
    ├── test_resources.py          # Resource + template listing
    ├── test_visibility.py         # Visibility control + transforms
    └── test_yandex_music.py       # YM MCP server tests
```

## Audio utils tests

`tests/utils/conftest.py` provides synthetic audio fixtures:
- Generates WAV files with sine waves at known frequencies
- Used for deterministic testing of BPM, key, energy modules
- No real audio files needed in repo

## MCP tests

Two testing layers, both using fixtures from `tests/mcp/conftest.py`.

### Layer 1: Metadata tests — verify tool registration, tags, annotations, namespacing

```python
async def test_tools_registered(workflow_mcp: FastMCP):
    tools = await workflow_mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "build_set" in tool_names
```

### Layer 2: Client integration tests — in-memory `Client(server)` invocations

```python
async def test_import_tracks_stub(workflow_mcp: FastMCP):
    async with Client(workflow_mcp) as client:
        result = await client.call_tool("import_tracks", {"track_ids": [1, 2, 3]})
        assert not result.is_error
        assert result.data.skipped_count == 3
```

### MCP fixtures (`tests/mcp/conftest.py`)

| Fixture | DB | Use for |
|---------|-----|---------|
| `workflow_mcp` | No | Metadata tests + stub tool invocation |
| `gateway_mcp` | No | Namespace tests (`dj_*`, `ym_*` prefix) |
| `ym_mcp` | No | YM tool tests |
| `workflow_mcp_with_db` | Yes (in-memory SQLite) | DB-dependent tool invocation |
| `engine` | — | Schema + seeding (share with mcp_with_db) |

### DB-dependent MCP tool tests (CRITICAL PATTERN)

`workflow_mcp_with_db` patches **`app.mcp.dependencies.session_factory`** to point to the test in-memory DB.

**⚠️ Seeding must use the SAME `engine` fixture, NOT `app.database.session_factory`:**

```python
async def test_deliver_set_empty_version(workflow_mcp_with_db: FastMCP, engine, tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.sets import DjSet, DjSetVersion

    # ✅ CORRECT — use async_sessionmaker(engine) to seed
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        dj_set = DjSet(name="Test Set")
        session.add(dj_set)
        await session.flush()
        version = DjSetVersion(set_id=dj_set.set_id)
        session.add(version)
        await session.flush()
        set_id = dj_set.set_id
        version_id = version.set_version_id  # PK is set_version_id, not version_id!
        await session.commit()

    # ❌ WRONG — this seeds into the real DB, not the test DB
    # async with session_factory() as session: ...
```

### `structured_content` shape (CRITICAL GOTCHA)

FastMCP puts Pydantic return model fields **directly** at the top level of `structured_content`, NOT wrapped in `{"result": ...}`:

```python
# ✅ CORRECT
sc = raw.structured_content
assert sc["set_id"] == set_id
assert sc["status"] == "ok"

# ❌ WRONG
assert sc["result"]["set_id"] == set_id   # KeyError!
assert raw.data["set_id"] == set_id       # wrong attribute
```

### Key testing rules

- **Server in fixture, Client in test body** (don't open Client in fixtures)
- **`result.data`** for structured output on simple tool calls, **`raw.structured_content`** for Pydantic returns
- **`result.is_error`** for error state, **`pytest.raises(ToolError)`** for expected tool errors
- **No database fixtures needed** for metadata + stub tool tests
- **Patch filesystem** in delivery tests: `with patch("app.mcp.tools.delivery._output_dir", return_value=tmp_path):`

## Test commands

```bash
uv run pytest -v                         # All tests
uv run pytest tests/test_tracks.py -v    # Single file
uv run pytest tests/test_tracks.py::test_create_track -v  # Single test
uv run pytest -k "transition" -v         # Match pattern
uv run pytest tests/mcp/ -v             # All MCP tests
make test-k MATCH=delivery              # Makefile shortcut
make coverage                            # With coverage report
```

## Writing new tests

- Use `client` fixture for API endpoint tests (full HTTP round-trip)
- Use `session` fixture for repository/service unit tests (direct DB)
- Use `MagicMock(spec=ModelClass)` for mock features in unit tests
- Use `workflow_mcp_with_db` + `engine` for MCP tools that need DB
- API tests: check status code + response body, use `response.json()["field"]`
- Service tests: inject real repositories with test session
- MCP delivery tests: always patch `_output_dir` to `tmp_path` to avoid real filesystem writes
