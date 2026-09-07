from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from price_monitor.domain.types import (
    ExtractedProduct,
    FetchedPage,
    ScrapeTarget,
    ValidationOutcome,
)
from price_monitor.scrapers.spec import SiteSpec


class RunnerConfigurationError(RuntimeError):
    pass


class SpecRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    product: ExtractedProduct | None = None
    validation: ValidationOutcome | None = None
    error_type: str | None = None
    error_message: str | None = None
    timed_out: bool = False
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def result_is_consistent(self) -> SpecRunResult:
        has_success = self.product is not None and self.validation is not None
        has_failure = self.error_type is not None
        if has_success == has_failure:
            raise ValueError("runner result must contain exactly one success or failure")
        if self.timed_out and self.error_type != "TimeoutExpired":
            raise ValueError("timed_out results must use TimeoutExpired")
        return self

    @property
    def accepted(self) -> bool:
        return self.validation is not None and self.validation.accepted


@runtime_checkable
class SpecRunner(Protocol):
    def run(self, *, spec: SiteSpec, page: FetchedPage, target: ScrapeTarget) -> SpecRunResult: ...


class DevelopmentSubprocessSpecRunner:
    """Best-effort process isolation for development and CI only.

    ``-I``, a temporary working directory, a timeout, and a stripped environment
    reduce accidental coupling. They are not a security boundary for hostile code.
    Production must use an external sandbox such as ``DockerSpecRunner``. Only a
    declarative SiteSpec is supplied to this runner; Python patches are unsupported.
    """

    _DEVELOPMENT_ENVIRONMENTS = frozenset({"dev", "development", "test", "testing", "ci"})

    def __init__(
        self,
        *,
        environment: str,
        timeout_seconds: float = 5.0,
        python_executable: Path | None = None,
        package_root: Path | None = None,
    ) -> None:
        if environment.casefold() not in self._DEVELOPMENT_ENVIRONMENTS:
            raise RunnerConfigurationError(
                "the subprocess spec runner is development-only; use DockerSpecRunner"
            )
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds
        # Preserve a virtualenv launcher path: resolving its symlink would make
        # Python lose the virtualenv's site-packages under isolated mode.
        self._python = (python_executable or Path(sys.executable)).absolute()
        self._package_root = (package_root or Path(__file__).resolve().parents[2]).resolve()
        if not self._python.is_file() or not self._package_root.is_dir():
            raise RunnerConfigurationError("invalid trusted runner executable or package root")

    def run(self, *, spec: SiteSpec, page: FetchedPage, target: ScrapeTarget) -> SpecRunResult:
        bootstrap = (
            "import sys;"
            f"sys.path.insert(0,{str(self._package_root)!r});"
            "from price_monitor.repair._spec_worker import main;main()"
        )
        command = (str(self._python), "-I", "-c", bootstrap)
        return _run_command(
            command,
            spec=spec,
            page=page,
            target=target,
            timeout_seconds=self._timeout_seconds,
            environment=_stripped_environment(),
        )


class DockerRunnerCommand(BaseModel):
    """Produces a locked-down, shell-free Docker invocation for production."""

    model_config = ConfigDict(frozen=True)

    image: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9./:@_-]{0,254}$")
    docker_executable: str = Field(default="docker", pattern=r"^[A-Za-z0-9_./-]+$")
    memory: str = Field(default="256m", pattern=r"^[1-9][0-9]*[kKmMgG]$")
    cpus: str = Field(default="0.5", pattern=r"^[0-9]+(?:\.[0-9]+)?$")
    pids_limit: int = Field(default=64, ge=8, le=1_024)
    user: str = Field(default="65532:65532", pattern=r"^[0-9]+:[0-9]+$")

    def build(self) -> tuple[str, ...]:
        return (
            self.docker_executable,
            "run",
            "--rm",
            "--interactive",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--memory={self.memory}",
            f"--cpus={self.cpus}",
            f"--pids-limit={self.pids_limit}",
            f"--user={self.user}",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
            self.image,
            "python",
            "-I",
            "-m",
            "price_monitor.repair._spec_worker",
        )


class DockerSpecRunner:
    """Runs the trusted worker from a pinned production sandbox image."""

    def __init__(
        self,
        command: DockerRunnerCommand,
        *,
        timeout_seconds: float = 15.0,
        host_environment: Mapping[str, str] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._command = command
        self._timeout_seconds = timeout_seconds
        # Docker normally needs no inherited variables for its local Unix socket.
        # Remote deployments may explicitly allowlist DOCKER_HOST/TLS variables.
        self._host_environment = dict(host_environment or {})

    def run(self, *, spec: SiteSpec, page: FetchedPage, target: ScrapeTarget) -> SpecRunResult:
        return _run_command(
            self._command.build(),
            spec=spec,
            page=page,
            target=target,
            timeout_seconds=self._timeout_seconds,
            environment=self._host_environment,
        )


def _stripped_environment() -> dict[str, str]:
    # Deliberately do not inherit API keys, database URLs, PYTHONPATH, or proxies.
    environment = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if os.name == "nt" and "SYSTEMROOT" in os.environ:
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return environment


def _run_command(
    command: Sequence[str],
    *,
    spec: SiteSpec,
    page: FetchedPage,
    target: ScrapeTarget,
    timeout_seconds: float,
    environment: Mapping[str, str],
) -> SpecRunResult:
    payload = json.dumps(
        {
            "spec": spec.model_dump(mode="json"),
            "page": page.model_dump(mode="json"),
            "target": target.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="price-monitor-spec-run-") as directory:
            completed = subprocess.run(
                tuple(command),
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=directory,
                env=dict(environment),
                check=False,
                close_fds=True,
            )
    except subprocess.TimeoutExpired:
        return SpecRunResult(
            error_type="TimeoutExpired",
            error_message=f"spec runner exceeded {timeout_seconds:g} seconds",
            timed_out=True,
            duration_ms=_elapsed_ms(started),
        )
    except OSError as exc:
        return SpecRunResult(
            error_type=type(exc).__name__,
            error_message=str(exc)[:2_000],
            duration_ms=_elapsed_ms(started),
        )

    if completed.returncode != 0:
        message = completed.stderr.strip()[-2_000:] or "sandbox worker exited unsuccessfully"
        return SpecRunResult(
            error_type="WorkerProcessError",
            error_message=message,
            duration_ms=_elapsed_ms(started),
        )
    try:
        output = json.loads(completed.stdout)
        if output.get("ok") is True:
            return SpecRunResult(
                product=ExtractedProduct.model_validate(output["product"]),
                validation=ValidationOutcome.model_validate(output["validation"]),
                duration_ms=_elapsed_ms(started),
            )
        error_type = str(output.get("error_type") or "WorkerError")[:200]
        error_message = str(output.get("error_message") or "unknown worker error")[:2_000]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        error_type = "InvalidWorkerOutput"
        error_message = str(exc)[:2_000]
    return SpecRunResult(
        error_type=error_type,
        error_message=error_message,
        duration_ms=_elapsed_ms(started),
    )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1_000))
