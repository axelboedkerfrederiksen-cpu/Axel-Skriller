from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from price_monitor.services.artifacts import (
    ArtifactConflictError,
    ArtifactIntegrityError,
    LocalArtifactStore,
    UnsafeArtifactPathError,
)


def test_local_artifact_store_round_trips_gzip_and_hashes(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    reference = store.store_html(
        site_key="demo_store",
        artifact_id="result-123",
        html="<html><p>£12.50</p></html>",
    )

    stored = tmp_path / reference.relative_path
    assert stored.read_bytes().startswith(b"\x1f\x8b")
    assert gzip.decompress(stored.read_bytes()).decode() == "<html><p>£12.50</p></html>"
    assert store.read_html(reference) == "<html><p>£12.50</p></html>"
    assert len(reference.content_sha256) == 64
    assert len(reference.compressed_sha256) == 64


def test_local_artifacts_are_immutable_and_idempotent(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    first = store.store_html(site_key="demo", artifact_id="one", html="same")

    assert store.store_html(site_key="demo", artifact_id="one", html="same") == first
    with pytest.raises(ArtifactConflictError):
        store.store_html(site_key="demo", artifact_id="one", html="different")


@pytest.mark.parametrize("unsafe", ["../escape", "a/b", ".", "", ".."])
def test_local_artifact_store_rejects_unsafe_identifiers(tmp_path: Path, unsafe: str) -> None:
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(UnsafeArtifactPathError):
        store.store_html(site_key=unsafe, artifact_id="one", html="data")


def test_local_artifact_store_detects_tampering(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    reference = store.store_html(site_key="demo", artifact_id="one", html="original")
    (tmp_path / reference.relative_path).write_bytes(gzip.compress(b"tampered", mtime=0))

    with pytest.raises(ArtifactIntegrityError):
        store.read_html(reference)
