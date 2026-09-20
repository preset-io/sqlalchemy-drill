"""Adversarial tests for the release artifact allowlist (no build/server needed)."""
import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_dist", Path(__file__).resolve().parents[1] / "tools" / "check_dist.py"
)
check_dist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_dist)
VERSION = "1.1.11"
WHEEL = f"sqlalchemy_drill-{VERSION}-py3-none-any.whl"
SDIST = f"sqlalchemy_drill-{VERSION}.tar.gz"


def make_dist(path, wheel_version=VERSION, sdist_version=VERSION,
              wheel_name="sqlalchemy_drill", sdist_name="sqlalchemy_drill",
              leak_test=False, omit=None, artifact_version=VERSION):
    metadata = f"Name: {wheel_name}\nVersion: {wheel_version}\n"
    with zipfile.ZipFile(path / f"sqlalchemy_drill-{artifact_version}-py3-none-any.whl", "w") as archive:
        archive.writestr(f"sqlalchemy_drill-{artifact_version}.dist-info/METADATA", metadata)
        archive.writestr("sqlalchemy_drill/__init__.py", "")
        if leak_test:
            archive.writestr("test/__init__.py", "")
    with tarfile.open(path / f"sqlalchemy_drill-{artifact_version}.tar.gz", "w:gz") as archive:
        for name in (*check_dist.REQUIRED_SDIST_PATHS, "PKG-INFO"):
            if name == omit:
                continue
            data = (f"Name: {sdist_name}\nVersion: {sdist_version}\n"
                    if name == "PKG-INFO" else "").encode()
            info = tarfile.TarInfo(f"sqlalchemy_drill-{artifact_version}/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def check(path, expected_version=VERSION):
    return check_dist.main([str(path), "--expected-version", expected_version])


def test_valid_pair(tmp_path):
    make_dist(tmp_path)
    assert check(tmp_path) == 0


@pytest.mark.parametrize("extra", ["unchecked-9.9.9.zip", "hidden", "extra.whl", "extra.tar.gz"])
def test_reject_extra_file(tmp_path, extra):
    make_dist(tmp_path)
    (tmp_path / extra).write_bytes(b"unchecked")
    assert check(tmp_path) == 1


@pytest.mark.parametrize("name", [WHEEL, SDIST])
def test_reject_version_prefix_collision(tmp_path, name):
    make_dist(tmp_path)
    (tmp_path / name).rename(tmp_path / name.replace(VERSION, VERSION + "0"))
    assert check(tmp_path) == 1


@pytest.mark.parametrize("name", [WHEEL, SDIST])
def test_reject_symlink(tmp_path, name):
    make_dist(tmp_path)
    original = tmp_path / name
    original.unlink()
    original.symlink_to(__file__)
    assert check(tmp_path) == 1


def test_reject_directory(tmp_path):
    make_dist(tmp_path)
    (tmp_path / "extra").mkdir()
    assert check(tmp_path) == 1


@pytest.mark.parametrize("kwargs", [
    {"wheel_version": "1.1.110"}, {"sdist_version": "1.1.110"},
    {"wheel_name": "other"}, {"sdist_name": "other"}, {"leak_test": True},
])
def test_reject_archive_metadata_and_namespace(tmp_path, kwargs):
    make_dist(tmp_path, **kwargs)
    assert check(tmp_path) == 1


@pytest.mark.parametrize("name", [WHEEL, SDIST])
def test_reject_corrupt_archive(tmp_path, name):
    make_dist(tmp_path)
    (tmp_path / name).write_bytes(b"not an archive")
    assert check(tmp_path) == 1


@pytest.mark.parametrize("missing", ["test/dbapi20.py", "test/__init__.py", "ivy.xml", "resolve.sh"])
def test_reject_missing_source_test_dependency(tmp_path, missing):
    make_dist(tmp_path, omit=missing)
    assert check(tmp_path) == 1


@pytest.mark.parametrize("separator", ["/./", "//"])
@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_reject_normalized_extraction_collisions(tmp_path, separator, kind):
    make_dist(tmp_path)
    if kind == "wheel":
        with zipfile.ZipFile(tmp_path / WHEEL, "a") as archive:
            archive.writestr("sqlalchemy_drill" + separator + "__init__.py", "overwrite")
    else:
        path = tmp_path / SDIST
        with tarfile.open(path) as archive:
            members = [(info, archive.extractfile(info).read())
                       for info in archive.getmembers()]
        with tarfile.open(path, "w:gz") as archive:
            for info, data in members:
                archive.addfile(info, io.BytesIO(data))
            alias = tarfile.TarInfo(f"sqlalchemy_drill-{VERSION}/test{separator}dbapi20.py")
            alias.size = 9
            archive.addfile(alias, io.BytesIO(b"overwrite"))
    assert check(tmp_path) == 1


@pytest.mark.parametrize("raw, normalized", [
    ("1.1.11.2+PR-7.f67cb54", "1.1.11.2+pr.7.f67cb54"),
    ("1.1.11.2+PR_7.F67CB54", "1.1.11.2+pr.7.f67cb54"),
    ("v1.0.0RC1", "1rc1"),
    ("1.0-1", "1.post1"),
    ("2!1.0.0+BUILD_007", "2!1+build.7"),
])
@pytest.mark.parametrize("reverse", [False, True])
def test_equivalent_versions(tmp_path, raw, normalized, reverse):
    expected, actual = (normalized, raw) if reverse else (raw, normalized)
    make_dist(tmp_path, artifact_version=actual,
              wheel_version=actual, sdist_version=actual)
    assert check(tmp_path, expected) == 0


@pytest.mark.parametrize("field", ["artifact_version", "wheel_version", "sdist_version"])
def test_reject_wrong_local_version(tmp_path, field):
    normalized = "1.1.11.2+pr.7.f67cb54"
    versions = dict(artifact_version=normalized, wheel_version=normalized,
                    sdist_version=normalized)
    versions[field] = "1.1.11.2+pr.8.f67cb54"
    make_dist(tmp_path, **versions)
    assert check(tmp_path, "1.1.11.2+PR-7.f67cb54") == 1


@pytest.mark.parametrize("name", [WHEEL, SDIST])
def test_reject_missing_artifact(tmp_path, name):
    make_dist(tmp_path)
    (tmp_path / name).unlink()
    assert check(tmp_path) == 1


@pytest.mark.parametrize("field", ["wheel_version", "sdist_version"])
@pytest.mark.parametrize("version", ["not-a-version", VERSION + "\nVersion: " + VERSION])
def test_reject_invalid_or_duplicate_metadata_version(tmp_path, field, version):
    make_dist(tmp_path, **{field: version})
    assert check(tmp_path) == 1
