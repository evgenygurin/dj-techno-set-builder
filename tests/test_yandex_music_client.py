from unittest.mock import AsyncMock, patch

from app.services.yandex_music_client import YandexMusicClient, parse_ym_track


async def test_search_tracks():
    client = YandexMusicClient(token="test", user_id="123")

    mock_response = {
        "result": {
            "tracks": {
                "results": [
                    {
                        "id": 103119407,
                        "title": "Octopus Neuroplasticity",
                        "artists": [
                            {"id": 3976138, "name": "Jouska", "various": False}
                        ],
                        "albums": [
                            {
                                "id": 36081872,
                                "title": "Techgnosis, Vol. 6",
                                "genre": "techno",
                                "labels": ["Techgnosis"],
                                "year": 2022,
                                "releaseDate": "2022-03-21T00:00:00+03:00",
                            }
                        ],
                        "durationMs": 347150,
                    }
                ]
            }
        }
    }

    with patch.object(client, "_get_json", return_value=mock_response):
        tracks = await client.search_tracks("Jouska Octopus Neuroplasticity")
        assert len(tracks) == 1
        assert tracks[0]["id"] == 103119407


def test_parse_track_metadata():
    """Defensive parsing: handles empty labels, missing fields."""
    track = {
        "id": 123,
        "title": "Test",
        "artists": [{"id": 1, "name": "DJ", "various": False}],
        "albums": [
            {"id": 10, "title": "EP", "genre": "techno", "labels": [], "year": 2024}
        ],
        "durationMs": 300000,
    }
    parsed = parse_ym_track(track)
    assert parsed.label_name is None
    assert parsed.album_genre == "techno"
    assert parsed.artists == "DJ"


def test_parse_track_no_albums():
    """Track with no albums doesn't crash."""
    track = {
        "id": 456,
        "title": "Orphan",
        "artists": [],
        "albums": [],
        "durationMs": 200000,
    }
    parsed = parse_ym_track(track)
    assert parsed.album_genre is None
    assert parsed.label_name is None
    assert parsed.artists == ""
    assert parsed.yandex_album_id is None


def test_parse_track_label_as_dict():
    """Labels can be dicts with name key."""
    track = {
        "id": 789,
        "title": "X",
        "artists": [{"id": 1, "name": "A", "various": False}],
        "albums": [
            {
                "id": 20,
                "title": "Album",
                "genre": "house",
                "labels": [{"id": 1, "name": "Cool Label"}],
                "year": 2023,
            }
        ],
        "durationMs": 250000,
    }
    parsed = parse_ym_track(track)
    assert parsed.label_name == "Cool Label"


def test_parse_track_filters_various_artists():
    """Various artists are filtered out."""
    track = {
        "id": 100,
        "title": "Track",
        "artists": [
            {"id": 1, "name": "Real DJ", "various": False},
            {"id": 2, "name": "Various Artists", "various": True},
        ],
        "albums": [],
        "durationMs": 300000,
    }
    parsed = parse_ym_track(track)
    assert parsed.artists == "Real DJ"
    assert parsed.artist_names == ["Real DJ"]
