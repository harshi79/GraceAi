"""Attachment validation and the upload state machine."""

from __future__ import annotations

import pytest

from grace import config
from grace.attachments import AttachmentManager, format_size
from grace.errors import AeroError
from grace.models import Attachment


@pytest.fixture()
def manager():
    return AttachmentManager()


def make(tmp_path, name="notes.txt", content=b"hello", size=None):
    path = tmp_path / name
    if size is None:
        path.write_bytes(content)
    else:
        path.write_bytes(b"x" * size)
    return str(path)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "name",
    ["notes.txt", "data.json", "table.csv", "main.py", "index.html",
     "config.yaml", "photo.png", "shot.jpg", "doc.pdf", "clip.mp4",
     "song.mp3", "archive.zip", "README.md"],
)
def test_supported_formats_are_accepted(manager, tmp_path, name):
    added, problems = manager.add_paths([make(tmp_path, name)])
    assert not problems
    assert added and added[0].name == name


@pytest.mark.parametrize(
    "name",
    ["program.exe", "lib.dll", "app.apk", "virus.bat", "db.sqlite",
     "disk.iso", "malware.scr", "payload.ps1"],
)
def test_executables_are_refused(manager, tmp_path, name):
    added, problems = manager.add_paths([make(tmp_path, name)])
    assert not added
    assert problems and "cannot be attached" in problems[0]


@pytest.mark.parametrize("name", ["archive.rar", "weird.xyz", "noextension"])
def test_unknown_extensions_are_refused(manager, tmp_path, name):
    added, problems = manager.add_paths([make(tmp_path, name)])
    assert not added
    assert problems


def test_missing_file_is_refused(manager):
    added, problems = manager.add_paths(["/nope/missing.txt"])
    assert not added and problems


def test_empty_file_is_refused(manager, tmp_path):
    added, problems = manager.add_paths([make(tmp_path, "empty.txt", b"")])
    assert not added and problems


def test_oversize_file_is_refused(manager, tmp_path):
    path = make(tmp_path, "big.txt", size=config.DEFAULT_ATTACHMENT_POLICY.max_bytes + 1)
    added, problems = manager.add_paths([path])
    assert not added
    assert "too large" in problems[0]


def test_duplicate_is_refused(manager, tmp_path):
    path = make(tmp_path, "a.txt")
    manager.add_paths([path])
    added, problems = manager.add_paths([path])
    assert not added and "already attached" in problems[0]


def test_quota_is_enforced(manager, tmp_path):
    policy = config.AttachmentPolicy(max_count=2)
    manager = AttachmentManager(policy=policy)
    paths = [make(tmp_path, f"f{i}.txt") for i in range(4)]
    added, problems = manager.add_paths(paths)
    assert len(added) == 2
    assert len(problems) == 2


def test_mixed_batch_reports_each_problem(manager, tmp_path):
    good = make(tmp_path, "good.txt")
    bad = make(tmp_path, "bad.exe")
    added, problems = manager.add_paths([good, bad])
    assert len(added) == 1
    assert len(problems) == 1


# --------------------------------------------------------------------------- #
# Upload lifecycle
# --------------------------------------------------------------------------- #


class FakeUploader:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, path, on_progress):
        self.calls.append(path)
        if self.fail:
            raise AeroError("boom")
        for step in (0.25, 0.5, 1.0):
            on_progress(step)
        return Attachment(
            id="att_x", path=path, name=path.rsplit("/", 1)[-1], size=3, mime="text/plain",
            state="uploaded", remote_id="f_remote", progress=1.0,
        )


def test_upload_marks_ready(manager, tmp_path):
    manager._uploader = FakeUploader()
    manager.add_paths([make(tmp_path, "a.txt")])
    manager.upload_all()
    item = manager.items[0]
    assert item.state == "uploaded"
    assert item.remote_id == "f_remote"
    assert manager.all_ready
    assert manager.ready_references() == ["f_remote"]


def test_upload_failure_and_retry(manager, tmp_path):
    uploader = FakeUploader(fail=True)
    manager._uploader = uploader
    manager.add_paths([make(tmp_path, "a.txt")])
    manager.upload_all()
    item = manager.items[0]
    assert item.state == "failed"
    assert manager.any_failed
    assert not manager.all_ready

    uploader.fail = False
    manager.retry(item.id)
    assert manager.items[0].state == "uploaded"
    assert manager.items[0].attempts == 2


def test_retry_only_applies_to_failed(manager, tmp_path):
    manager._uploader = FakeUploader()
    manager.add_paths([make(tmp_path, "a.txt")])
    manager.upload_all()
    item = manager.items[0]
    manager.retry(item.id)  # already uploaded
    assert item.attempts == 1


def test_upload_without_a_transport_fails_cleanly(manager, tmp_path):
    manager._uploader = None
    manager.add_paths([make(tmp_path, "a.txt")])
    manager.upload_all()
    assert manager.items[0].state == "failed"


def test_progress_is_reported(manager, tmp_path):
    uploader = FakeUploader()
    manager._uploader = uploader
    seen = []
    manager._on_change = lambda att: seen.append(att.progress if att else None)
    manager.add_paths([make(tmp_path, "a.txt")])
    manager.upload_all()
    assert seen and seen[-1] == 1.0


def test_remove_and_clear(manager, tmp_path):
    manager._uploader = FakeUploader()
    manager.add_paths([make(tmp_path, "a.txt"), make(tmp_path, "b.txt")])
    manager.remove(manager.items[0].id)
    assert len(manager) == 1
    manager.clear()
    assert len(manager) == 0
    assert manager.ready_references() == []


def test_error_callback_is_invoked(manager, tmp_path):
    errors = []
    manager._uploader = FakeUploader(fail=True)
    manager._on_error = lambda att, msg: errors.append(msg)
    manager.add_paths([make(tmp_path, "a.txt")])
    manager.upload_all()
    assert errors


def test_upload_all_is_idempotent(manager, tmp_path):
    uploader = FakeUploader()
    manager._uploader = uploader
    manager.add_paths([make(tmp_path, "a.txt")])
    manager.upload_all()
    manager.upload_all()
    assert len(uploader.calls) == 1


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "size,expected",
    [
        (0, "0 B"),
        (512, "512 B"),
        (2048, "2.0 KB"),
        (5 * 1024 * 1024, "5.0 MB"),
        (3 * 1024 * 1024 * 1024, "3.0 GB"),
    ],
)
def test_format_size(size, expected):
    assert format_size(size) == expected
