"""Bounded transactional search for ordered layout proposals.

The search knows nothing about geometry.  A proposal callback owns feasibility and
may yield any number of records for one item (for example, a room and the route
that connects it).  Search paths are immutable tuples, so records from a rejected
branch cannot leak into a sibling branch or into ``initial``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from time import monotonic
from typing import Any, TypeVar


Item = TypeVar("Item")
Record = TypeVar("Record")


def interleave_trials(streams):
    """Give each proposal domain one trial before returning to the first.

    None is retained: rejected geometric work must not monopolise another
    proportion's or storey's opportunity to offer a legal batch.
    """
    active = [iter(stream) for stream in streams]
    while active:
        remaining = []
        for stream in active:
            try:
                trial = next(stream)
            except StopIteration:
                continue
            remaining.append(stream)
            yield trial
        active = remaining


class LayoutSearchTimeout(Exception):
    """Cooperative stage stop, never a geometric infeasibility verdict."""


class SearchDeadline:
    def __init__(self, seconds: float, *, clock=monotonic):
        if seconds <= 0:
            raise ValueError('search time budget must be positive')
        self.clock = clock
        self.expires = clock() + seconds

    def check(self):
        if self.clock() >= self.expires:
            raise LayoutSearchTimeout


@dataclass
class LayoutSearchResult:
    """Outcome of :func:`search_layout`.

    ``nodes`` counts candidate batches considered.  ``exhausted`` is true only
    when the search had to stop because ``max_nodes`` was reached; an empty
    proposal domain is an ordinary incomplete result.
    """

    placed: list[Any]
    complete: bool
    nodes: int
    exhausted: bool
    unplaced: list[Any]
    timed_out: bool = False


def search_layout(
    items: Iterable[Item],
    initial: Iterable[Record],
    proposals: Callable[[Item, Sequence[Record]], Iterable[Iterable[Record] | None]],
    *,
    max_nodes: int,
    checkpoint: Callable[[], None] | None = None,
    fair_roots: bool = False,
    accept: Callable[[Sequence[Record]], bool] | None = None,
) -> LayoutSearchResult:
    """Depth-first search over lazy, transactional candidate batches.

    ``proposals`` receives a read-only snapshot of the current path and yields
    candidate batches in the order they should be tried.  Each yielded batch is
    one node.  A failed branch is discarded before the next batch is requested.
    The returned partial path has maximum item depth reached, with ties keeping
    the first path encountered for deterministic results.

    With ``fair_roots``, two first-item proposals are explored cooperatively under
    the same global budget. Geometry iterators yield ``None`` after unsuccessful
    work to let the other branch advance; it never creates a node or a record.
    ``accept`` checks the complete proposed path before committing its batch.
    A rejected batch spends a node and rolls back, even at the last item.
    """
    if max_nodes < 0:
        raise ValueError("max_nodes must be non-negative")

    ordered_items = tuple(items)
    seed = tuple(initial)
    best_path = seed
    best_depth = 0
    nodes = 0
    exhausted = False

    complete = False

    def remember(index, path):
        nonlocal best_depth, best_path, complete
        if index > best_depth:
            best_depth = index
            best_path = path
        if index == len(ordered_items):
            complete = True

    def batches(index, path):
        nonlocal nodes, exhausted
        candidates = iter(proposals(ordered_items[index],path))
        while True:
            if checkpoint is not None:
                checkpoint()
            if nodes >= max_nodes:
                exhausted = True
                return
            try:
                batch = next(candidates)
            except StopIteration:
                return
            if batch is None:
                # A cooperative geometry trial performed work but found no batch.
                yield None
                continue
            nodes += 1
            new_path = path+tuple(batch)
            if accept is not None and not accept(new_path):
                yield None
                continue
            remember(index+1,new_path)
            yield new_path

    def visit(index: int, path: tuple[Record, ...]):
        nonlocal exhausted
        if complete or exhausted:
            return
        # Do not request geometry after consuming the global node budget.
        if nodes >= max_nodes:
            exhausted = True
            return
        for new_path in batches(index,path):
            yield None
            if complete or exhausted:
                return
            if new_path is not None:
                yield from visit(index+1,new_path)
            if complete or exhausted:
                return

    def interleaved():
        # Two live dominant assemblies receive equal geometric work opportunities.
        # A stalled secondary room cannot monopolise the entire planning deadline.
        roots = iter(batches(0,seed))
        active,roots_done = [],False
        while not complete and not exhausted and (active or not roots_done):
            if len(active)<2 and not roots_done:
                try:
                    path = next(roots)
                    if path is not None and not complete:
                        active.append(visit(1,path))
                except StopIteration:
                    roots_done = True
            remaining = []
            for branch in active:
                if complete or exhausted:
                    break
                try:
                    next(branch)
                    remaining.append(branch)
                except StopIteration:
                    pass
            active = remaining

    timed_out = False
    try:
        remember(0,seed)
        if not complete:
            if fair_roots:
                interleaved()
            else:
                for _ in visit(0,seed):
                    pass
    except LayoutSearchTimeout:
        complete, timed_out = False, True
    return LayoutSearchResult(
        placed=list(best_path),
        complete=complete,
        nodes=nodes,
        exhausted=exhausted and not complete,
        unplaced=list(ordered_items[best_depth:]),
        timed_out=timed_out,
    )
