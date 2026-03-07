"""Comprehensive data integrity verification tests.

This module tests:
- Foreign key integrity (no orphaned records)
- Unique constraint validation
- Data range validation (CHECK constraints)
- Schema/model alignment
- Repository query correctness
"""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Artist, Track, TrackArtist
from app.models.dj import DjLibraryItem, DjPlaylist, DjPlaylistItem
from app.models.features import TrackAudioFeaturesComputed
from app.models.runs import FeatureExtractionRun
from app.models.sections import TrackSection
from app.models.sets import DjSet, DjSetItem, DjSetVersion
from app.models.transitions import Transition, TransitionCandidate


class TestForeignKeyIntegrity:
    """Test that all foreign key relationships are valid (no orphaned records)."""

    async def test_track_artists_fk_integrity(self, session: AsyncSession):
        """Verify track_artists references valid tracks and artists."""
        # Check track_id references
        stmt = text("""
            SELECT COUNT(*) FROM track_artists 
            WHERE track_id NOT IN (SELECT track_id FROM tracks)
        """)
        result = await session.execute(stmt)
        orphaned_tracks = result.scalar()
        assert orphaned_tracks == 0, f"Found {orphaned_tracks} orphaned track_artists.track_id"

        # Check artist_id references
        stmt = text("""
            SELECT COUNT(*) FROM track_artists 
            WHERE artist_id NOT IN (SELECT artist_id FROM artists)
        """)
        result = await session.execute(stmt)
        orphaned_artists = result.scalar()
        assert (
            orphaned_artists == 0
        ), f"Found {orphaned_artists} orphaned track_artists.artist_id"

    async def test_audio_features_fk_integrity(self, session: AsyncSession):
        """Verify audio features reference valid tracks and runs."""
        # Check track_id
        stmt = text("""
            SELECT COUNT(*) FROM track_audio_features_computed 
            WHERE track_id NOT IN (SELECT track_id FROM tracks)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned features.track_id"

        # Check run_id
        stmt = text("""
            SELECT COUNT(*) FROM track_audio_features_computed 
            WHERE run_id NOT IN (SELECT run_id FROM feature_extraction_runs)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned features.run_id"

    async def test_sections_fk_integrity(self, session: AsyncSession):
        """Verify sections reference valid tracks and runs."""
        stmt = text("""
            SELECT COUNT(*) FROM track_sections 
            WHERE track_id NOT IN (SELECT track_id FROM tracks)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned sections.track_id"

        stmt = text("""
            SELECT COUNT(*) FROM track_sections 
            WHERE run_id NOT IN (SELECT run_id FROM feature_extraction_runs)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned sections.run_id"

    async def test_dj_library_items_fk_integrity(self, session: AsyncSession):
        """Verify DJ library items reference valid tracks."""
        stmt = text("""
            SELECT COUNT(*) FROM dj_library_items 
            WHERE track_id NOT IN (SELECT track_id FROM tracks)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned dj_library_items.track_id"

    async def test_playlist_items_fk_integrity(self, session: AsyncSession):
        """Verify playlist items reference valid playlists and tracks."""
        stmt = text("""
            SELECT COUNT(*) FROM dj_playlist_items 
            WHERE playlist_id NOT IN (SELECT playlist_id FROM dj_playlists)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned playlist_items.playlist_id"

        stmt = text("""
            SELECT COUNT(*) FROM dj_playlist_items 
            WHERE track_id NOT IN (SELECT track_id FROM tracks)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned playlist_items.track_id"

    async def test_set_items_fk_integrity(self, session: AsyncSession):
        """Verify set items reference valid versions, tracks, and transitions."""
        # Check set_version_id
        stmt = text("""
            SELECT COUNT(*) FROM dj_set_items 
            WHERE set_version_id NOT IN (SELECT set_version_id FROM dj_set_versions)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned set_items.set_version_id"

        # Check track_id
        stmt = text("""
            SELECT COUNT(*) FROM dj_set_items 
            WHERE track_id NOT IN (SELECT track_id FROM tracks)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned set_items.track_id"

        # Check transition_id (nullable)
        stmt = text("""
            SELECT COUNT(*) FROM dj_set_items 
            WHERE transition_id IS NOT NULL 
            AND transition_id NOT IN (SELECT transition_id FROM transitions)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned set_items.transition_id"

    async def test_set_versions_fk_integrity(self, session: AsyncSession):
        """Verify set versions reference valid sets."""
        stmt = text("""
            SELECT COUNT(*) FROM dj_set_versions 
            WHERE set_id NOT IN (SELECT set_id FROM dj_sets)
        """)
        result = await session.execute(stmt)
        orphans = result.scalar()
        assert orphans == 0, f"Found {orphans} orphaned set_versions.set_id"


class TestDataRangeValidation:
    """Test that all data values are within valid ranges per CHECK constraints."""

    async def test_bpm_range_valid(self, session: AsyncSession):
        """Verify BPM values are in valid range (20-300)."""
        stmt = text("""
            SELECT COUNT(*) FROM track_audio_features_computed 
            WHERE bpm < 20 OR bpm > 300
        """)
        result = await session.execute(stmt)
        invalid = result.scalar()
        assert invalid == 0, f"Found {invalid} BPM values outside valid range (20-300)"

    async def test_energy_values_normalized(self, session: AsyncSession):
        """Verify energy values are normalized (0-1)."""
        stmt = text("""
            SELECT COUNT(*) FROM track_audio_features_computed 
            WHERE energy_mean < 0 OR energy_mean > 1
        """)
        result = await session.execute(stmt)
        invalid = result.scalar()
        assert invalid == 0, f"Found {invalid} invalid energy_mean values (must be 0-1)"

        stmt = text("""
            SELECT COUNT(*) FROM track_audio_features_computed 
            WHERE energy_max < 0 OR energy_max > 1
        """)
        result = await session.execute(stmt)
        invalid = result.scalar()
        assert invalid == 0, f"Found {invalid} invalid energy_max values (must be 0-1)"

    async def test_key_code_valid_range(self, session: AsyncSession):
        """Verify key codes are in valid range (0-23)."""
        stmt = text("""
            SELECT COUNT(*) FROM track_audio_features_computed 
            WHERE key_code < 0 OR key_code > 23
        """)
        result = await session.execute(stmt)
        invalid = result.scalar()
        assert invalid == 0, f"Found {invalid} invalid key_code values (must be 0-23)"

    async def test_track_duration_positive(self, session: AsyncSession):
        """Verify all track durations are positive."""
        stmt = text("SELECT COUNT(*) FROM tracks WHERE duration_ms <= 0")
        result = await session.execute(stmt)
        invalid = result.scalar()
        assert invalid == 0, f"Found {invalid} tracks with non-positive duration"

    async def test_section_duration_consistency(self, session: AsyncSession):
        """Verify section durations match their time ranges."""
        stmt = text("""
            SELECT COUNT(*) FROM track_sections 
            WHERE section_duration_ms != (end_ms - start_ms)
        """)
        result = await session.execute(stmt)
        invalid = result.scalar()
        assert (
            invalid == 0
        ), f"Found {invalid} sections with inconsistent duration calculation"

    async def test_sections_within_track_bounds(self, session: AsyncSession):
        """Verify all sections stay within their track's duration."""
        stmt = text("""
            SELECT COUNT(*) 
            FROM track_sections s
            JOIN tracks t ON s.track_id = t.track_id
            WHERE s.end_ms > t.duration_ms
        """)
        result = await session.execute(stmt)
        invalid = result.scalar()
        assert invalid == 0, f"Found {invalid} sections extending beyond track duration"

    async def test_band_energy_values_normalized(self, session: AsyncSession):
        """Verify all band energy values are normalized (0-1)."""
        for band in ["sub", "low", "lowmid", "mid", "highmid", "high"]:
            stmt = text(f"""
                SELECT COUNT(*) FROM track_audio_features_computed 
                WHERE {band}_energy IS NOT NULL 
                AND ({band}_energy < 0 OR {band}_energy > 1)
            """)
            result = await session.execute(stmt)
            invalid = result.scalar()
            assert invalid == 0, f"Found {invalid} invalid {band}_energy values (must be 0-1)"

    async def test_confidence_values_normalized(self, session: AsyncSession):
        """Verify all confidence values are normalized (0-1)."""
        for field in ["tempo_confidence", "key_confidence", "bpm_stability"]:
            stmt = text(f"""
                SELECT COUNT(*) FROM track_audio_features_computed 
                WHERE {field} < 0 OR {field} > 1
            """)
            result = await session.execute(stmt)
            invalid = result.scalar()
            assert invalid == 0, f"Found {invalid} invalid {field} values (must be 0-1)"

    async def test_track_status_valid(self, session: AsyncSession):
        """Verify all track status values are valid (0=active, 1=archived)."""
        stmt = text("SELECT COUNT(*) FROM tracks WHERE status NOT IN (0, 1)")
        result = await session.execute(stmt)
        invalid = result.scalar()
        assert invalid == 0, f"Found {invalid} tracks with invalid status (must be 0 or 1)"


class TestSchemaAlignment:
    """Verify ORM models match database schema."""

    async def test_track_model_alignment(self, session: AsyncSession):
        """Verify Track model has all DB columns."""
        result = await session.execute(text("PRAGMA table_info(tracks)"))
        db_columns = {row[1] for row in result.fetchall()}

        model_columns = {col.name for col in Track.__table__.columns}

        assert db_columns == model_columns, (
            f"Schema mismatch for tracks table. "
            f"Missing in model: {db_columns - model_columns}. "
            f"Missing in DB: {model_columns - db_columns}"
        )

    async def test_features_model_alignment(self, session: AsyncSession):
        """Verify TrackAudioFeaturesComputed model has all DB columns."""
        result = await session.execute(text("PRAGMA table_info(track_audio_features_computed)"))
        db_columns = {row[1] for row in result.fetchall()}

        model_columns = {col.name for col in TrackAudioFeaturesComputed.__table__.columns}

        assert db_columns == model_columns, (
            f"Schema mismatch for track_audio_features_computed table. "
            f"Missing in model: {db_columns - model_columns}. "
            f"Missing in DB: {model_columns - db_columns}"
        )

    async def test_sections_model_alignment(self, session: AsyncSession):
        """Verify TrackSection model has all DB columns."""
        result = await session.execute(text("PRAGMA table_info(track_sections)"))
        db_columns = {row[1] for row in result.fetchall()}

        model_columns = {col.name for col in TrackSection.__table__.columns}

        assert db_columns == model_columns, (
            f"Schema mismatch for track_sections table. "
            f"Missing in model: {db_columns - model_columns}. "
            f"Missing in DB: {model_columns - db_columns}"
        )

    async def test_set_items_model_alignment(self, session: AsyncSession):
        """Verify DjSetItem model has all DB columns."""
        result = await session.execute(text("PRAGMA table_info(dj_set_items)"))
        db_columns = {row[1] for row in result.fetchall()}

        model_columns = {col.name for col in DjSetItem.__table__.columns}

        assert db_columns == model_columns, (
            f"Schema mismatch for dj_set_items table. "
            f"Missing in model: {db_columns - model_columns}. "
            f"Missing in DB: {model_columns - db_columns}"
        )


class TestRepositoryQueries:
    """Test repository query correctness."""

    async def test_audio_features_list_all_excludes_orphans(self, session: AsyncSession):
        """Verify list_all() only returns features for existing tracks."""
        from app.repositories.audio_features import AudioFeaturesRepository

        repo = AudioFeaturesRepository(session)

        # Get all features via repository
        features = await repo.list_all()

        # Verify all referenced tracks exist
        track_ids = {f.track_id for f in features}
        stmt = select(func.count()).select_from(Track).where(Track.track_id.in_(track_ids))
        result = await session.execute(stmt)
        existing_count = result.scalar()

        assert existing_count == len(track_ids), (
            f"list_all() returned features for non-existent tracks. "
            f"Expected {len(track_ids)} tracks, found {existing_count}"
        )

    async def test_audio_features_filter_excludes_orphans(self, session: AsyncSession):
        """Verify filter_by_criteria() only returns features for existing tracks."""
        from app.repositories.audio_features import AudioFeaturesRepository

        repo = AudioFeaturesRepository(session)

        # Filter by BPM range
        features, total = await repo.filter_by_criteria(bpm_min=120.0, bpm_max=140.0)

        # Verify all referenced tracks exist
        if features:
            track_ids = {f.track_id for f in features}
            stmt = select(func.count()).select_from(Track).where(Track.track_id.in_(track_ids))
            result = await session.execute(stmt)
            existing_count = result.scalar()

            assert existing_count == len(track_ids), (
                "filter_by_criteria() returned features for non-existent tracks"
            )

    async def test_sections_get_latest_batches_correctly(self, session: AsyncSession):
        """Verify get_latest_by_track_ids() groups sections by track correctly."""
        from app.repositories.sections import SectionsRepository

        repo = SectionsRepository(session)

        # Get first 5 tracks with sections
        stmt = (
            select(TrackSection.track_id)
            .distinct()
            .limit(5)
        )
        result = await session.execute(stmt)
        track_ids = [row[0] for row in result.fetchall()]

        if not track_ids:
            # No sections in DB, test passes
            return

        sections_map = await repo.get_latest_by_track_ids(track_ids)

        # Verify all sections belong to requested tracks
        for track_id, sections in sections_map.items():
            assert track_id in track_ids, f"Unexpected track_id {track_id} in results"
            for section in sections:
                assert section.track_id == track_id, (
                    f"Section {section.section_id} has wrong track_id "
                    f"(expected {track_id}, got {section.track_id})"
                )

            # Verify sections are ordered by start_ms
            start_times = [s.start_ms for s in sections]
            assert start_times == sorted(start_times), (
                f"Sections for track {track_id} are not ordered by start_ms"
            )

    async def test_set_repository_stats_batch_correctness(self, session: AsyncSession):
        """Verify get_stats_batch() returns correct counts."""
        from app.repositories.sets import DjSetRepository

        repo = DjSetRepository(session)

        # Get first 5 sets
        stmt = select(DjSet.set_id).limit(5)
        result = await session.execute(stmt)
        set_ids = [row[0] for row in result.fetchall()]

        if not set_ids:
            # No sets in DB, test passes
            return

        stats = await repo.get_stats_batch(set_ids)

        # Verify stats for each set
        for set_id in set_ids:
            version_count, track_count = stats[set_id]

            # Manual count of versions
            stmt = select(func.count()).select_from(DjSetVersion).where(
                DjSetVersion.set_id == set_id
            )
            result = await session.execute(stmt)
            expected_versions = result.scalar()

            assert version_count == expected_versions, (
                f"Set {set_id}: version count mismatch "
                f"(expected {expected_versions}, got {version_count})"
            )

            # Manual count of tracks in latest version
            stmt = (
                select(DjSetVersion.set_version_id)
                .where(DjSetVersion.set_id == set_id)
                .order_by(DjSetVersion.set_version_id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            latest_vid = result.scalar()

            if latest_vid:
                stmt = select(func.count()).select_from(DjSetItem).where(
                    DjSetItem.set_version_id == latest_vid
                )
                result = await session.execute(stmt)
                expected_tracks = result.scalar()

                assert track_count == expected_tracks, (
                    f"Set {set_id}: track count mismatch "
                    f"(expected {expected_tracks}, got {track_count})"
                )


class TestDuplicateValidation:
    """Test for duplicate records that should not exist."""

    async def test_no_duplicate_tracks(self, session: AsyncSession):
        """Check for duplicate tracks (same title + duration)."""
        stmt = text("""
            SELECT title, duration_ms, COUNT(*) as cnt 
            FROM tracks 
            GROUP BY title, duration_ms 
            HAVING COUNT(*) > 1
        """)
        result = await session.execute(stmt)
        dupes = result.fetchall()

        # Note: Some duplicates may be intentional (same song, different sources)
        # This test just flags them for review
        if dupes:
            dupe_list = "\n".join(
                f'  - "{title[:50]}" ({dur}ms): {cnt} copies'
                for title, dur, cnt in dupes[:5]
            )
            # This is a warning, not a failure - duplicates may be valid
            print(
                f"\n⚠️  Found {len(dupes)} potential duplicate track groups:\n{dupe_list}"
            )

    async def test_no_duplicate_artists(self, session: AsyncSession):
        """Check for duplicate artist names."""
        stmt = text("""
            SELECT name, COUNT(*) as cnt 
            FROM artists 
            GROUP BY name 
            HAVING COUNT(*) > 1
        """)
        result = await session.execute(stmt)
        dupes = result.fetchall()

        # Artist name duplicates are usually errors
        assert len(dupes) == 0, (
            f"Found {len(dupes)} duplicate artist names: "
            f"{[(name, cnt) for name, cnt in dupes[:5]]}"
        )
