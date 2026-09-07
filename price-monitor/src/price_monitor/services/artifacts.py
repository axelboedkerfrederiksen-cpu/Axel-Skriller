from __future__ import annotations

import gzip
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ArtifactStoreError(RuntimeError):
    """Base error for local artifact persistence."""


class UnsafeArtifactPathError(ArtifactStoreError, ValueError):
    """Raised when an artifact path could escape its configured root."""


class ArtifactConflictError(ArtifactStoreError):
    """Raised when an immutable artifact name is reused with different content."""


class ArtifactIntegrityError(ArtifactStoreError):
    """Raised when an artifact no longer matches its recorded digest."""


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """Portable metadata for an immutable, gzip-compressed HTML artifact."""

    relative_path: str
    content_sha256: str
    compressed_sha256: str
    uncompressed_bytes: int
    compressed_bytes: int


class LocalArtifactStore:
    """Stores bounded diagnostic HTML under a single local root.

    Callers provide opaque identifiers rather than paths. Artifacts are immutable:
    repeating an identical write is idempotent, while reusing a name for different
    content fails. This implementation is suitable for the beta's local storage;
    the returned relative paths can later be backed by an object-store adapter.
    """

    def __init__(self, root: Path, *, maximum_html_bytes: int = 20_000_000) -> None:
        if maximum_html_bytes < 1:
            raise ValueError("maximum_html_bytes must be positive")
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve()
        self._maximum_html_bytes = maximum_html_bytes

    @property
    def root(self) -> Path:
        return self._root

    def store_html(
        self,
        *,
        site_key: str,
        artifact_id: str,
        html: str,
    ) -> ArtifactReference:
        site_key = self._validate_segment(site_key, "site_key")
        artifact_id = self._validate_segment(artifact_id, "artifact_id")
        raw = html.encode("utf-8")
        if len(raw) > self._maximum_html_bytes:
            raise ArtifactStoreError(
                f"HTML artifact is {len(raw)} bytes; limit is {self._maximum_html_bytes}"
            )

        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        reference = ArtifactReference(
            relative_path=f"html/{site_key}/{artifact_id}.html.gz",
            content_sha256=hashlib.sha256(raw).hexdigest(),
            compressed_sha256=hashlib.sha256(compressed).hexdigest(),
            uncompressed_bytes=len(raw),
            compressed_bytes=len(compressed),
        )
        destination = self._safe_destination(reference.relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._assert_beneath_root(destination.parent.resolve())
        self._write_immutable(destination, compressed)
        return reference

    def read_html(
        self,
        reference_or_path: ArtifactReference | str,
        *,
        expected_content_sha256: str | None = None,
    ) -> str:
        if isinstance(reference_or_path, ArtifactReference):
            relative_path = reference_or_path.relative_path
            expected_content_sha256 = expected_content_sha256 or reference_or_path.content_sha256
            expected_compressed_sha256 = reference_or_path.compressed_sha256
        else:
            relative_path = reference_or_path
            expected_compressed_sha256 = None

        source = self._safe_existing_path(relative_path)
        compressed = source.read_bytes()
        if expected_compressed_sha256 is not None:
            actual_compressed_hash = hashlib.sha256(compressed).hexdigest()
            if actual_compressed_hash != expected_compressed_sha256:
                raise ArtifactIntegrityError("compressed artifact digest mismatch")

        try:
            with gzip.open(source, "rb") as stream:
                raw = stream.read(self._maximum_html_bytes + 1)
        except (OSError, EOFError) as exc:
            raise ArtifactIntegrityError("artifact is not valid gzip data") from exc
        if len(raw) > self._maximum_html_bytes:
            raise ArtifactIntegrityError("decompressed artifact exceeds configured limit")
        actual_content_hash = hashlib.sha256(raw).hexdigest()
        if expected_content_sha256 is not None and actual_content_hash != expected_content_sha256:
            raise ArtifactIntegrityError("HTML content digest mismatch")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ArtifactIntegrityError("HTML artifact is not UTF-8") from exc

    def _safe_destination(self, relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise UnsafeArtifactPathError("artifact path must remain relative to its root")
        candidate = self._root.joinpath(path)
        self._assert_beneath_root(candidate.parent.resolve())
        return candidate

    def _safe_existing_path(self, relative_path: str) -> Path:
        candidate = self._safe_destination(relative_path)
        resolved = candidate.resolve(strict=True)
        self._assert_beneath_root(resolved)
        if not resolved.is_file() or resolved.suffixes[-2:] != [".html", ".gz"]:
            raise UnsafeArtifactPathError("artifact must be a gzip-compressed HTML file")
        return resolved

    def _assert_beneath_root(self, path: Path) -> None:
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise UnsafeArtifactPathError("artifact path escapes configured root") from exc

    @staticmethod
    def _validate_segment(value: str, field_name: str) -> str:
        if not _SAFE_SEGMENT.fullmatch(value):
            raise UnsafeArtifactPathError(f"unsafe {field_name}")
        return value

    @staticmethod
    def _write_immutable(destination: Path, content: bytes) -> None:
        if destination.exists():
            if destination.is_file() and destination.read_bytes() == content:
                return
            raise ArtifactConflictError(f"artifact already exists: {destination.name}")

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if destination.is_file() and destination.read_bytes() == content:
                    return
                raise ArtifactConflictError(
                    f"artifact already exists: {destination.name}"
                ) from None
        finally:
            temporary.unlink(missing_ok=True)
