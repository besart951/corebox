import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from croniter import croniter

from app_foundation.primitives import Clock, Conflict, ValidationError


class Job(Protocol):
    @property
    def name(self) -> str: ...
    async def run(self) -> None: ...


class DistributedLock(Protocol):
    def acquire(self, name: str) -> AbstractAsyncContextManager[bool]: ...


@dataclass(frozen=True, slots=True)
class FunctionJob:
    name: str
    action: Callable[[], Awaitable[None]]

    async def run(self) -> None:
        await self.action()


class JobRegistry:
    def __init__(self, jobs: tuple[Job, ...] = ()) -> None:
        self._jobs: dict[str, Job] = {}
        for job in jobs:
            self.register(job)

    def register(self, job: Job) -> None:
        if job.name in self._jobs:
            raise Conflict("Job name already registered")
        self._jobs[job.name] = job

    def get(self, name: str) -> Job:
        return self._jobs[name]


class MemoryLock:
    def __init__(self) -> None:
        self._held: set[str] = set()

    @asynccontextmanager
    async def acquire(self, name: str) -> AsyncIterator[bool]:
        if name in self._held:
            yield False
            return
        self._held.add(name)
        try:
            yield True
        finally:
            self._held.remove(name)


class JobRunner:
    def __init__(self, registry: JobRegistry, lock: DistributedLock) -> None:
        self._registry = registry
        self._lock = lock

    async def run(self, name: str) -> bool:
        async with self._lock.acquire(name) as acquired:
            if acquired:
                await self._registry.get(name).run()
            return acquired


class Schedule(Protocol):
    def next_after(self, instant: datetime) -> datetime: ...


@dataclass(frozen=True, slots=True)
class IntervalSchedule:
    seconds: int

    def __post_init__(self) -> None:
        if self.seconds < 1:
            raise ValidationError("Interval must be positive")

    def next_after(self, instant: datetime) -> datetime:
        return instant + timedelta(seconds=self.seconds)


@dataclass(frozen=True, slots=True)
class CronSchedule:
    expression: str
    timezone: str = "UTC"

    def __post_init__(self) -> None:
        if not croniter.is_valid(self.expression) or len(self.expression.split()) != 5:
            raise ValidationError("A five-field cron expression is required")
        ZoneInfo(self.timezone)

    def next_after(self, instant: datetime) -> datetime:
        result = croniter(self.expression, instant.astimezone(ZoneInfo(self.timezone))).get_next(
            datetime
        )
        assert isinstance(result, datetime)
        return result


class Scheduler:
    """Coalesces missed ticks, prevents local overlap, drains running jobs on stop."""

    def __init__(
        self, runner: JobRunner, schedules: tuple[tuple[str, Schedule], ...], clock: Clock
    ) -> None:
        self._runner = runner
        self._schedules = schedules
        self._clock = clock
        self._stop = asyncio.Event()
        self._running: dict[str, asyncio.Task[None]] = {}

    async def _execute(self, name: str) -> None:
        try:
            await self._runner.run(name)
        except Exception:
            # No exception repr: job failures may contain transport credentials.
            logging.getLogger(__name__).error("Job failed: %s", name)  # noqa: TRY400 - omit secrets in exception

    async def run(self) -> None:
        due = {name: schedule.next_after(self._clock.now()) for name, schedule in self._schedules}
        try:
            while not self._stop.is_set():
                now = self._clock.now()
                for name, schedule in self._schedules:
                    task = self._running.get(name)
                    if now >= due[name] and (task is None or task.done()):
                        self._running[name] = asyncio.create_task(self._execute(name))
                        due[name] = schedule.next_after(now)
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=0.5)
        finally:
            if self._running:
                await asyncio.gather(*self._running.values())

    def stop(self) -> None:
        self._stop.set()


__all__ = (
    "CronSchedule",
    "DistributedLock",
    "FunctionJob",
    "IntervalSchedule",
    "Job",
    "JobRegistry",
    "JobRunner",
    "MemoryLock",
    "Schedule",
    "Scheduler",
)
