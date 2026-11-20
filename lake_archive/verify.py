"""Read-only reconciliation of a live archive against its original import.

The operator uploads the logger CSV that was first imported into the archive.
From that original reading we

1. compare frame numbers, sampling instants and base references with the live
   archive (a restored backup may have lost or altered frames);
2. replay the correction ledger (``revision`` rows) in correction-id order on
   top of the original readings, checking for every row its base reference,
   the restored temperature before/after, and the stored representation
   before/after;

   A stored value is a difference, so it is checked against the base frame's
   *reconstructed* temperature **at the time of that correction**, not against
   the base's current or original temperature.  A base frame corrected earlier
   therefore changes the expected difference of a later correction of a frame
   that refers to it;

3. when every ledger row matches, compare the reconstructed temperatures with
   the live archive and list frames that differ.

The whole read (archive header, frames, revisions, and the last revision id)
happens inside one read transaction, so the report describes a single committed
state even while operators keep submitting corrections.  Nothing is written.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import archive as store
from . import csvio


@dataclass(frozen=True)
class SnapshotFrame:
    seq: int
    sampled_at: str
    restored_mc: int
    base_seq: int | None


@dataclass(frozen=True)
class SnapshotRevision:
    id: int
    seq: int
    old_restored_mc: int
    old_base_seq: int | None
    old_stored_kind: str
    old_stored_mc: int
    new_restored_mc: int
    new_base_seq: int | None
    new_stored_kind: str
    new_stored_mc: int


@dataclass(frozen=True)
class ArchiveSnapshot:
    archive_id: int
    name: str
    source_filename: str
    frames: tuple[SnapshotFrame, ...]
    revisions: tuple[SnapshotRevision, ...]
    last_revision_id: int | None
    revision_count: int


@dataclass(frozen=True)
class FrameIssue:
    seq: int
    field: str          # missing_in_current | unexpected_in_current |
                        # sampled_at | base_seq
    original: object
    current: object


@dataclass(frozen=True)
class RevisionIssue:
    field: str          # base_seq | new_base_seq | old_restored_mc |
                        # old_stored | new_stored | missing_frame | missing_base
    expected: object
    recorded: object


@dataclass(frozen=True)
class RevisionCheck:
    revision_id: int
    seq: int
    base_seq: int | None
    # reconstructed base frame temperature at the instant of this correction
    base_restored_mc: int | None
    old_restored_mc: int
    new_restored_mc: int
    old_stored_kind: str
    old_stored_mc: int
    new_stored_kind: str
    new_stored_mc: int
    expected_old_stored: tuple[str, int] | None
    expected_new_stored: tuple[str, int] | None
    issues: tuple[RevisionIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class RestoredIssue:
    seq: int
    reconstructed_mc: int
    current_mc: int


@dataclass(frozen=True)
class VerifyReport:
    archive_id: int
    archive_name: str
    source_filename: str
    original_filename: str | None
    last_revision_id: int | None
    revision_count: int
    original_frame_count: int
    current_frame_count: int
    frame_issues: tuple[FrameIssue, ...]
    revision_checks: tuple[RevisionCheck, ...]
    first_mismatch: RevisionCheck | None
    restored_checked: bool
    restored_issues: tuple[RestoredIssue, ...]

    @property
    def structure_ok(self) -> bool:
        return not self.frame_issues

    @property
    def revisions_ok(self) -> bool:
        return all(check.ok for check in self.revision_checks)

    @property
    def passed(self) -> bool:
        return (self.structure_ok and self.revisions_ok
                and self.restored_checked and not self.restored_issues)


def load_snapshot(db_path: str, archive_id: int) -> ArchiveSnapshot:
    """Read the archive header, frames and revisions from one committed state.

    A deferred read transaction is opened and never upgraded to a write, so in
    WAL mode a correction committed by another connection during this read is
    not visible here (and is not blocked by us).
    """
    conn = store.connect(db_path)
    try:
        conn.execute("BEGIN")
        try:
            arow = conn.execute(
                "SELECT id, name, source_filename FROM archive WHERE id = ?",
                (archive_id,),
            ).fetchone()
            if arow is None:
                raise store.ArchiveError("archive not found", status=404)
            frame_rows = conn.execute(
                "SELECT seq, sampled_at, restored_mc, base_seq FROM frame"
                " WHERE archive_id = ? ORDER BY seq",
                (archive_id,),
            ).fetchall()
            rev_rows = conn.execute(
                "SELECT id, seq, old_restored_mc, old_base_seq, old_stored_kind,"
                " old_stored_mc, new_restored_mc, new_base_seq, new_stored_kind,"
                " new_stored_mc FROM revision WHERE archive_id = ? ORDER BY id",
                (archive_id,),
            ).fetchall()
        finally:
            conn.execute("COMMIT")
    finally:
        conn.close()

    revisions = tuple(
        SnapshotRevision(
            id=r["id"], seq=r["seq"],
            old_restored_mc=r["old_restored_mc"], old_base_seq=r["old_base_seq"],
            old_stored_kind=r["old_stored_kind"], old_stored_mc=r["old_stored_mc"],
            new_restored_mc=r["new_restored_mc"], new_base_seq=r["new_base_seq"],
            new_stored_kind=r["new_stored_kind"], new_stored_mc=r["new_stored_mc"],
        )
        for r in rev_rows
    )
    return ArchiveSnapshot(
        archive_id=arow["id"],
        name=arow["name"],
        source_filename=arow["source_filename"],
        frames=tuple(
            SnapshotFrame(seq=r["seq"], sampled_at=r["sampled_at"],
                          restored_mc=r["restored_mc"], base_seq=r["base_seq"])
            for r in frame_rows
        ),
        revisions=revisions,
        last_revision_id=revisions[-1].id if revisions else None,
        revision_count=len(revisions),
    )


def _stored(restored_mc: int, base_restored_mc: int | None) -> tuple[str, int]:
    if base_restored_mc is None:
        return "absolute", restored_mc
    return "delta", restored_mc - base_restored_mc


def _compare_frames(original_rows: list[csvio.FrameRow],
                    snapshot: ArchiveSnapshot) -> list[FrameIssue]:
    original = {fr.seq: fr for fr in original_rows}
    current = {fr.seq: fr for fr in snapshot.frames}
    issues: list[FrameIssue] = []
    for seq in sorted(set(original) | set(current)):
        orig = original.get(seq)
        cur = current.get(seq)
        if cur is None:
            issues.append(FrameIssue(seq, "missing_in_current",
                                     orig.sampled_at, None))
            continue
        if orig is None:
            issues.append(FrameIssue(seq, "unexpected_in_current", None, cur.sampled_at))
            continue
        if orig.sampled_at != cur.sampled_at:
            issues.append(FrameIssue(seq, "sampled_at", orig.sampled_at, cur.sampled_at))
        if orig.base_seq != cur.base_seq:
            issues.append(FrameIssue(seq, "base_seq", orig.base_seq, cur.base_seq))
    return issues


def _replay(original_rows: list[csvio.FrameRow], snapshot: ArchiveSnapshot):
    """Replay the ledger from the original readings.

    Returns ``(checks, reconstructed, first_mismatch)`` where ``reconstructed``
    maps seq to the temperature after all replayed corrections.
    """
    restored: dict[int, int] = {}
    base_of: dict[int, int | None] = {}
    for fr in sorted(original_rows, key=lambda f: f.seq):
        base_of[fr.seq] = fr.base_seq
        if fr.base_seq is None:
            restored[fr.seq] = fr.stored_mc
        else:
            restored[fr.seq] = fr.stored_mc + restored[fr.base_seq]

    checks: list[RevisionCheck] = []
    for rev in snapshot.revisions:
        seq = rev.seq
        if seq not in restored:
            checks.append(RevisionCheck(
                revision_id=rev.id, seq=seq, base_seq=None, base_restored_mc=None,
                old_restored_mc=rev.old_restored_mc,
                new_restored_mc=rev.new_restored_mc,
                old_stored_kind=rev.old_stored_kind,
                old_stored_mc=rev.old_stored_mc,
                new_stored_kind=rev.new_stored_kind,
                new_stored_mc=rev.new_stored_mc,
                expected_old_stored=None, expected_new_stored=None,
                issues=(RevisionIssue("missing_frame", None, seq),),
            ))
            continue

        issues: list[RevisionIssue] = []
        base_seq = base_of[seq]

        # The base reference is immutable in this archive model: every ledger
        # row must carry the original one, before and after the correction.
        if rev.old_base_seq != base_seq:
            issues.append(RevisionIssue("base_seq", base_seq, rev.old_base_seq))
        if rev.new_base_seq != rev.old_base_seq:
            issues.append(RevisionIssue("new_base_seq", rev.old_base_seq,
                                        rev.new_base_seq))

        base_restored: int | None = None
        abnormal_base = base_seq is not None and base_seq not in restored
        if base_seq is not None:
            base_restored = restored.get(base_seq)
            if base_restored is None:
                issues.append(RevisionIssue("missing_base", base_seq, None))

        expected_old: tuple[str, int] | None = None
        expected_new: tuple[str, int] | None = None
        if not abnormal_base:
            expected_old = _stored(rev.old_restored_mc, base_restored)
            expected_new = _stored(rev.new_restored_mc, base_restored)
            if (rev.old_stored_kind, rev.old_stored_mc) != expected_old:
                issues.append(RevisionIssue(
                    "old_stored", expected_old,
                    (rev.old_stored_kind, rev.old_stored_mc)))
            if (rev.new_stored_kind, rev.new_stored_mc) != expected_new:
                issues.append(RevisionIssue(
                    "new_stored", expected_new,
                    (rev.new_stored_kind, rev.new_stored_mc)))

        reconstructed_before = restored[seq]
        if rev.old_restored_mc != reconstructed_before:
            issues.append(RevisionIssue("old_restored_mc", reconstructed_before,
                                        rev.old_restored_mc))

        checks.append(RevisionCheck(
            revision_id=rev.id, seq=seq, base_seq=base_seq,
            base_restored_mc=base_restored,
            old_restored_mc=rev.old_restored_mc,
            new_restored_mc=rev.new_restored_mc,
            old_stored_kind=rev.old_stored_kind,
            old_stored_mc=rev.old_stored_mc,
            new_stored_kind=rev.new_stored_kind,
            new_stored_mc=rev.new_stored_mc,
            expected_old_stored=expected_old,
            expected_new_stored=expected_new,
            issues=tuple(issues),
        ))

        # Follow the ledger's claimed "after" value even when a row does not
        # check out.  This lets the final reading comparison show whether the
        # live archive still agrees with what the ledger says it did.
        restored[seq] = rev.new_restored_mc

    return checks, restored


def analyze(snapshot: ArchiveSnapshot, original_rows: list[csvio.FrameRow],
            original_filename: str | None = None) -> VerifyReport:
    frame_issues = _compare_frames(original_rows, snapshot)
    checks, reconstructed = _replay(original_rows, snapshot)
    revisions_ok = all(check.ok for check in checks)

    restored_issues: list[RestoredIssue] = []
    restored_checked = not frame_issues and revisions_ok
    if revisions_ok:
        current = {fr.seq: fr.restored_mc for fr in snapshot.frames}
        for seq in sorted(reconstructed):
            if seq in current and current[seq] != reconstructed[seq]:
                restored_issues.append(
                    RestoredIssue(seq, reconstructed[seq], current[seq]))

    first_mismatch = next((c for c in checks if not c.ok), None)
    return VerifyReport(
        archive_id=snapshot.archive_id,
        archive_name=snapshot.name,
        source_filename=snapshot.source_filename,
        original_filename=original_filename,
        last_revision_id=snapshot.last_revision_id,
        revision_count=snapshot.revision_count,
        original_frame_count=len(original_rows),
        current_frame_count=len(snapshot.frames),
        frame_issues=tuple(frame_issues),
        revision_checks=tuple(checks),
        first_mismatch=first_mismatch,
        restored_checked=restored_checked,
        restored_issues=tuple(restored_issues),
    )


def verify_archive(db_path: str, archive_id: int, payload: bytes,
                   original_filename: str | None = None) -> VerifyReport:
    """Parse the original CSV and reconcile it with a single archive snapshot."""
    original_rows, _layout = csvio.parse_csv(payload)
    snapshot = load_snapshot(db_path, archive_id)
    return analyze(snapshot, original_rows, original_filename)
