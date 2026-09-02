"""An archive that restores, and a prune that only ever deletes locally.

The gate for this item is not "an archive appears". It is "extract it into an
empty tree and diff": a backup nobody has restored is a hypothesis.

Two things are deliberate and neither is obvious:

* **`data/raw/field/` is in the set and the spec did not put it there.** The spec
  says field EO samples are covered because they live in
  data/live/field_eo_log.parquet. The *log* does; the sampled *squads* do not —
  `save_field_sample` writes data/raw/field/<season>/gw<N>.json, and a past
  gameweek's top-10k picks cannot be fetched again from anywhere. Everything else
  in this archive is replaceable by a command; those are not.
* **the prune deletes only in the local directory.** `--rsync` copies to a remote
  path, and a retention rule that reached across it would be this tool deleting
  files on a machine it does not own, over a protocol with no undo.
"""

from __future__ import annotations

import tarfile

import pytest

from gaffer import backup


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    """A miniature of the real layout, with one file in every archived root."""
    monkeypatch.chdir(tmp_path)
    for rel, text in (
            ("data/live/player_gw.parquet", "live"),
            ("data/live/field_eo_log.parquet", "eo"),
            ("data/raw/field/2026-27/gw2.json", "squads"),
            ("data/raw/tier_eo/2026-27.json", "tier"),
            ("reports/decision_ledger.json", "ledger"),
            ("models/minutes.joblib", "model"),
            # Not in the set: big, and re-fetchable.
            ("data/history/player_gw.parquet", "history"),
            ("data/raw/news/page.html", "news"),
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_the_archive_extracts_to_a_tree_that_matches(tree, tmp_path):
    """The gate, as a test."""
    archive = backup.run_backup(to=tree / "backups")
    out = tmp_path / "restored"
    out.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(out)
    for rel in ("data/live/player_gw.parquet", "data/raw/field/2026-27/gw2.json",
                "reports/decision_ledger.json", "models/minutes.joblib"):
        assert (out / rel).read_text() == (tree / rel).read_text()


def test_the_sampled_squads_are_in_it(tree):
    """The spec's omission, pinned. These are the only files in the tree that
    no command can rebuild."""
    archive = backup.run_backup(to=tree / "backups")
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert "data/raw/field/2026-27/gw2.json" in names
    assert "data/raw/tier_eo/2026-27.json" in names


def test_the_replaceable_bulk_is_not(tree):
    """67 MB of scraped pages and 3 MB of history that `gaffer build-history`
    rebuilds. Excluded on purpose, and the README says which command rebuilds
    which."""
    archive = backup.run_backup(to=tree / "backups")
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert not [n for n in names if n.startswith("data/history")]
    assert not [n for n in names if n.startswith("data/raw/news")]


def test_the_name_carries_the_minute(tree):
    archive = backup.run_backup(to=tree / "backups")
    assert archive.name.startswith("gaffer-")
    assert archive.name.endswith(".tar.gz")
    stamp = archive.stem.removeprefix("gaffer-").removesuffix(".tar")
    assert len(stamp) == 13 and stamp[8] == "-"       # YYYYMMDD-HHMM


def test_a_missing_root_is_skipped_rather_than_fatal(tmp_path, monkeypatch):
    """A clone that has never trained has no models/. Backing up four of five
    roots beats backing up none."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "x.json").write_text("{}")
    archive = backup.run_backup(to=tmp_path / "backups")
    with tarfile.open(archive) as tar:
        # `tar.add` of a directory writes the directory entry as well as its
        # contents, which is what makes an extract restore the mode bits. The
        # claim is the exhaustive list: nothing from models/ or data/ is in
        # here, because neither exists.
        assert tar.getnames() == ["reports", "reports/x.json"]


def test_a_tree_with_nothing_to_archive_says_so_and_writes_no_file(tmp_path,
                                                                   monkeypatch):
    """An empty tar is worse than none: it looks like a successful backup and
    restores to nothing."""
    monkeypatch.chdir(tmp_path)
    assert backup.run_backup(to=tmp_path / "backups") is None
    assert not list((tmp_path / "backups").glob("*.tar.gz"))


def test_the_prune_keeps_the_newest_n(tree):
    dest = tree / "backups"
    dest.mkdir()
    for i in range(6):
        (dest / f"gaffer-2026090{i}-1200.tar.gz").write_text("x")
    backup.prune(dest, keep=3)
    assert sorted(p.name for p in dest.glob("*.tar.gz")) == [
        "gaffer-20260903-1200.tar.gz", "gaffer-20260904-1200.tar.gz",
        "gaffer-20260905-1200.tar.gz"]


def test_the_prune_ignores_files_it_did_not_write(tree):
    """A user's own directory. Deleting by pattern and not by "everything in
    here" is the difference between a retention rule and a data loss."""
    dest = tree / "backups"
    dest.mkdir()
    (dest / "gaffer-20260901-1200.tar.gz").write_text("x")
    (dest / "gaffer-20260902-1200.tar.gz").write_text("x")
    (dest / "important-notes.txt").write_text("mine")
    (dest / "gaffer-notes.md").write_text("also mine")
    backup.prune(dest, keep=1)
    assert (dest / "important-notes.txt").exists()
    assert (dest / "gaffer-notes.md").exists()
    assert len(list(dest.glob("gaffer-*.tar.gz"))) == 1


def test_keep_zero_is_treated_as_keep_everything(tree):
    """A misread config key must not empty the backup directory. There is no
    legitimate reason to ask this command to keep nothing."""
    dest = tree / "backups"
    dest.mkdir()
    (dest / "gaffer-20260901-1200.tar.gz").write_text("x")
    backup.prune(dest, keep=0)
    assert len(list(dest.glob("gaffer-*.tar.gz"))) == 1


def test_the_rsync_target_is_copied_to_and_never_pruned(tree, monkeypatch):
    """The remote half. This tool does not delete on a machine it does not
    own, over a protocol with no undo."""
    calls = []
    monkeypatch.setattr(backup.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or
                        type("R", (), {"returncode": 0, "stderr": ""})())
    backup.run_backup(to=tree / "backups", rsync="host:/vol/gaffer")
    assert calls and calls[0][:2] == ["rsync", "-a"]
    assert calls[0][-1] == "host:/vol/gaffer"


def test_a_failing_rsync_does_not_lose_the_local_archive(tree, monkeypatch):
    """The copy is the optional half. A local archive that exists beats an
    exception that leaves the user believing nothing was backed up."""
    monkeypatch.setattr(backup.subprocess, "run",
                        lambda cmd, **kw:
                        type("R", (), {"returncode": 1,
                                       "stderr": "host unreachable"})())
    archive = backup.run_backup(to=tree / "backups", rsync="host:/vol")
    assert archive is not None and archive.exists()


def test_latest_backup_reads_the_newest_and_its_size(tree):
    dest = tree / "backups"
    backup.run_backup(to=dest)
    newest = backup.latest_backup(dest)
    assert newest is not None
    assert newest["bytes"] > 0
    assert newest["modified_at"].endswith("+00:00")


def test_latest_backup_of_an_absent_directory_is_None(tmp_path):
    """The Health line's empty state: "never", not a zero and not a crash."""
    assert backup.latest_backup(tmp_path / "nope") is None
