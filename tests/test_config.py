def test_yandex_settings_have_defaults():
    from app.config import Settings

    s = Settings(database_url="sqlite+aiosqlite:///test.db", _env_file=None)
    assert s.yandex_music_token == ""
    assert s.yandex_music_user_id == ""
