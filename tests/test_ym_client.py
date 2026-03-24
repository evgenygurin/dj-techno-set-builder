from unittest.mock import AsyncMock

from app.clients.yandex_music import YandexMusicClient


async def test_search_tracks() -> None:
    mock_http = AsyncMock()
    mock_http.get.return_value = {
        "result": {
            "tracks": {
                "results": [
                    {
                        "id": 103119407,
                        "title": "Octopus Neuroplasticity",
                        "artists": [{"id": 3976138, "name": "Jouska", "various": False}],
                        "albums": [
                            {
                                "id": 36081872,
                                "title": "Techgnosis, Vol. 6",
                                "genre": "techno",
                                "labels": ["Techgnosis"],
                            }
                        ],
                    }
                ]
            }
        }
    }

    client = YandexMusicClient(mock_http)
    results = await client.search_tracks("Jouska Octopus Neuroplasticity")

    assert len(results) == 1
    assert results[0]["id"] == 103119407


async def test_fetch_tracks() -> None:
    mock_http = AsyncMock()
    mock_http.post_form.return_value = {
        "result": [
            {
                "id": 103119407,
                "title": "Octopus Neuroplasticity",
                "artists": [{"id": 3976138, "name": "Jouska"}],
                "albums": [{"genre": "techno", "labels": []}],
            }
        ]
    }

    client = YandexMusicClient(mock_http)
    data = await client.fetch_tracks(["103119407"])
    assert "103119407" in data
    assert data["103119407"]["title"] == "Octopus Neuroplasticity"
