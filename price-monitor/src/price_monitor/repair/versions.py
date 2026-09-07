from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from price_monitor.scrapers.spec import SiteSpec

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SpecVersionError(RuntimeError):
    """Base error for declarative scraper version operations."""


class UnknownSpecError(SpecVersionError, LookupError):
    pass


class StaleCandidateError(SpecVersionError):
    pass


class ImmutableVersionConflictError(SpecVersionError):
    pass


class _VersionState(TypedDict):
    active_revision: str
    active_sha256: str
    previous_revision: str | None
    previous_sha256: str | None


@dataclass(frozen=True, slots=True)
class SpecVersion:
    spec: SiteSpec
    sha256: str
    source: Literal["packaged", "staged", "versioned"]
    relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class ActivationResult:
    active: SpecVersion
    previous: SpecVersion | None


class SpecVersionStore:
    """Immutable SiteSpec versions with a small, atomically replaced active pointer.

    Packaged specs remain the fallback until the first repair is activated. Runtime
    candidates never modify package files, and every activated candidate remains in
    ``versions/`` so rollback is an active-pointer change rather than a rewrite.
    """

    def __init__(
        self,
        root: Path,
        packaged_baselines: Mapping[str, SiteSpec] | Iterable[SiteSpec] = (),
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve()
        if isinstance(packaged_baselines, Mapping):
            baselines = dict(packaged_baselines)
        else:
            baselines = {spec.key: spec for spec in packaged_baselines}
        if any(key != spec.key for key, spec in baselines.items()):
            raise ValueError("packaged baseline keys must match SiteSpec.key")
        self._packaged = baselines

    @property
    def root(self) -> Path:
        return self._root

    def get_active(self, key: str) -> SpecVersion:
        key = self._component(key, "key")
        state = self._read_state(key)
        if state is None:
            try:
                return self._packaged_version(self._packaged[key])
            except KeyError as exc:
                raise UnknownSpecError(f"no active or packaged spec for {key!r}") from exc
        active = self.get_revision(key, state["active_revision"])
        if active.sha256 != state["active_sha256"]:
            raise SpecVersionError("active spec digest does not match its state pointer")
        return active

    def get_revision(self, key: str, revision: str) -> SpecVersion:
        key = self._component(key, "key")
        revision = self._component(revision, "revision")
        version_path = self._version_path(key, revision)
        if version_path.exists():
            return self._read_version(version_path, key, revision, "versioned")
        packaged = self._packaged.get(key)
        if packaged is not None and packaged.revision == revision:
            return self._packaged_version(packaged)
        raise UnknownSpecError(f"unknown spec version {key!r}@{revision!r}")

    def stage_candidate(
        self,
        candidate: SiteSpec,
        *,
        expected_base_revision: str,
    ) -> SpecVersion:
        key = self._component(candidate.key, "key")
        self._component(candidate.revision, "revision")
        with self._lock(key):
            current = self.get_active(key)
            if current.spec.revision != expected_base_revision:
                raise StaleCandidateError(
                    f"candidate was based on {expected_base_revision!r}; "
                    f"active revision is {current.spec.revision!r}"
                )
            if candidate.revision == current.spec.revision:
                raise SpecVersionError("candidate revision must differ from active revision")
            content = self._serialize(candidate)
            path = self._staged_path(key, candidate.revision)
            self._write_immutable(path, content)
            return SpecVersion(
                spec=candidate,
                sha256=hashlib.sha256(content).hexdigest(),
                source="staged",
                relative_path=str(path.relative_to(self._root)),
            )

    def get_staged(self, key: str, revision: str) -> SpecVersion:
        key = self._component(key, "key")
        revision = self._component(revision, "revision")
        path = self._staged_path(key, revision)
        if not path.exists():
            raise UnknownSpecError(f"unknown staged candidate {key!r}@{revision!r}")
        return self._read_version(path, key, revision, "staged")

    def activate(
        self,
        key: str,
        revision: str,
        *,
        expected_active_revision: str | None = None,
    ) -> ActivationResult:
        key = self._component(key, "key")
        revision = self._component(revision, "revision")
        with self._lock(key):
            current = self.get_active(key)
            if (
                expected_active_revision is not None
                and current.spec.revision != expected_active_revision
            ):
                raise StaleCandidateError(
                    f"expected active revision {expected_active_revision!r}; "
                    f"found {current.spec.revision!r}"
                )
            if current.spec.revision == revision:
                return ActivationResult(active=current, previous=self._previous(key))

            try:
                candidate = self.get_staged(key, revision)
            except UnknownSpecError:
                candidate = self.get_revision(key, revision)

            version_path = self._version_path(key, revision)
            content = self._serialize(candidate.spec)
            self._write_immutable(version_path, content)
            active = SpecVersion(
                spec=candidate.spec,
                sha256=hashlib.sha256(content).hexdigest(),
                source="versioned",
                relative_path=str(version_path.relative_to(self._root)),
            )
            self._write_state(key, active=active, previous=current)
            return ActivationResult(active=active, previous=current)

    def rollback(
        self,
        key: str,
        *,
        expected_active_revision: str | None = None,
    ) -> ActivationResult:
        key = self._component(key, "key")
        with self._lock(key):
            current = self.get_active(key)
            if (
                expected_active_revision is not None
                and current.spec.revision != expected_active_revision
            ):
                raise StaleCandidateError(
                    f"expected active revision {expected_active_revision!r}; "
                    f"found {current.spec.revision!r}"
                )
            previous = self._previous(key)
            if previous is None:
                raise SpecVersionError(f"no previous revision is available for {key!r}")
            self._write_state(key, active=previous, previous=current)
            return ActivationResult(active=previous, previous=current)

    def _previous(self, key: str) -> SpecVersion | None:
        state = self._read_state(key)
        if state is None:
            return None
        previous_revision = state["previous_revision"]
        previous_sha256 = state["previous_sha256"]
        if previous_revision is None:
            return None
        if previous_sha256 is None:
            raise SpecVersionError("previous revision has no digest in its state pointer")
        previous = self.get_revision(key, previous_revision)
        if previous.sha256 != previous_sha256:
            raise SpecVersionError("previous spec digest does not match its state pointer")
        return previous

    def _read_state(self, key: str) -> _VersionState | None:
        path = self._state_path(key)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            active_revision = value["active_revision"]
            active_sha256 = value["active_sha256"]
            previous_revision = value.get("previous_revision")
            previous_sha256 = value.get("previous_sha256")
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise SpecVersionError(f"invalid state file for {key!r}") from exc
        for digest in (active_sha256, previous_sha256):
            if digest is not None and not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise SpecVersionError(f"invalid state digest for {key!r}")
        self._component(str(active_revision), "active_revision")
        if previous_revision is not None:
            self._component(str(previous_revision), "previous_revision")
        return _VersionState(
            active_revision=str(active_revision),
            active_sha256=str(active_sha256),
            previous_revision=(str(previous_revision) if previous_revision is not None else None),
            previous_sha256=(str(previous_sha256) if previous_sha256 is not None else None),
        )

    def _write_state(self, key: str, *, active: SpecVersion, previous: SpecVersion | None) -> None:
        value = {
            "active_revision": active.spec.revision,
            "active_sha256": active.sha256,
            "previous_revision": previous.spec.revision if previous else None,
            "previous_sha256": previous.sha256 if previous else None,
        }
        self._write_atomic(self._state_path(key), self._json_bytes(value))

    def _read_version(
        self,
        path: Path,
        expected_key: str,
        expected_revision: str,
        source: Literal["staged", "versioned"],
    ) -> SpecVersion:
        self._assert_safe_existing(path)
        content = path.read_bytes()
        try:
            spec = SiteSpec.model_validate_json(content)
        except ValueError as exc:
            raise SpecVersionError(f"invalid SiteSpec at {path.name}") from exc
        if spec.key != expected_key or spec.revision != expected_revision:
            raise SpecVersionError("version path does not match SiteSpec identity")
        return SpecVersion(
            spec=spec,
            sha256=hashlib.sha256(content).hexdigest(),
            source=source,
            relative_path=str(path.relative_to(self._root)),
        )

    def _packaged_version(self, spec: SiteSpec) -> SpecVersion:
        content = self._serialize(spec)
        return SpecVersion(
            spec=spec,
            sha256=hashlib.sha256(content).hexdigest(),
            source="packaged",
        )

    def _version_path(self, key: str, revision: str) -> Path:
        return self._safe_path("versions", key, f"{revision}.json")

    def _staged_path(self, key: str, revision: str) -> Path:
        return self._safe_path("staged", key, f"{revision}.json")

    def _state_path(self, key: str) -> Path:
        return self._safe_path("state", f"{key}.json")

    @contextmanager
    def _lock(self, key: str) -> Iterator[None]:
        path = self._safe_path("locks", f"{key}.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _safe_path(self, *parts: str) -> Path:
        if any(part in {"", ".", ".."} or "/" in part or "\\" in part for part in parts):
            raise SpecVersionError("unsafe spec version path")
        path = self._root.joinpath(*parts)
        try:
            path.parent.resolve().relative_to(self._root)
        except ValueError as exc:
            raise SpecVersionError("spec version path escapes configured root") from exc
        return path

    def _assert_safe_existing(self, path: Path) -> None:
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self._root)
        except (FileNotFoundError, ValueError) as exc:
            raise SpecVersionError("spec version path escapes configured root") from exc
        if not resolved.is_file():
            raise SpecVersionError("spec version is not a regular file")

    @staticmethod
    def _component(value: str, field_name: str) -> str:
        if not _SAFE_COMPONENT.fullmatch(value):
            raise SpecVersionError(f"unsafe {field_name}")
        return value

    @staticmethod
    def _json_bytes(value: object) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def _serialize(cls, spec: SiteSpec) -> bytes:
        return cls._json_bytes(spec.model_dump(mode="json"))

    @staticmethod
    def _write_immutable(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.is_file() and path.read_bytes() == content:
                return
            raise ImmutableVersionConflictError(f"version already exists: {path.name}")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.is_file() and path.read_bytes() == content:
                    return
                raise ImmutableVersionConflictError(
                    f"version already exists: {path.name}"
                ) from None
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            temporary.unlink(missing_ok=True)
