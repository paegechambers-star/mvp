import pytest

from scriptor.project import BookProject, ProjectError, slugify


def test_slugify():
    assert slugify("Die Stimmen der Stadt!") == "die-stimmen-der-stadt"
    assert slugify("Größe & Maß") == "grosse-mass"


def test_create_and_duplicate(workspace, project):
    assert project.slug == "die-stimmen-der-stadt"
    assert BookProject.list_slugs(workspace) == ["die-stimmen-der-stadt"]
    with pytest.raises(ProjectError):
        BookProject.create(workspace, "Die Stimmen der Stadt", "young_adult", "x")


def test_ssot_commit_requires_reason_and_registers(project):
    with pytest.raises(ProjectError):
        project.commit_ssot("bible", {"premise": "x"}, reason="  ")
    rid = project.commit_ssot("bible", {"premise": "x"}, reason="test")
    assert project.bible["premise"] == "x"
    assert project.bible["meta"]["genre"] == "young_adult"  # PATCH merged
    reg = project.register()
    assert reg[-1]["id"] == rid and reg[-1]["kind"] == "PATCH"
    assert [e["id"] for e in reg] == sorted({e["id"] for e in reg})  # eindeutig, fortlaufend
    project.commit_ssot("outline", {"chapters": []}, reason="neu", kind="SUPERSEDE")
    with pytest.raises(ProjectError):
        project.commit_ssot("evil", {}, reason="x")


def test_chapter_versions_never_overwrite(project):
    v1, _ = project.write_chapter(1, "eins", "draft")
    v2, _ = project.write_chapter(1, "zwei", "rev")
    assert (v1, v2) == (1, 2)
    assert project.latest_chapter(1) == (2, "zwei")
    assert (project.root / "work/chapters/kap-01.v1.md").read_text() == "eins"


def test_export_requires_all_chapters(project):
    project.commit_ssot("outline", {"chapters": [{"nr": 1, "title": "A"}, {"nr": 2, "title": "B"}]},
                        reason="t", kind="SUPERSEDE")
    project.write_chapter(1, "Text eins", "d")
    with pytest.raises(ProjectError, match=r"\[2\]"):
        project.export_markdown()
    project.write_chapter(2, "Text zwei", "d")
    out = project.export_markdown()
    text = out.read_text()
    assert "## 1. A" in text and "Text zwei" in text and "Chambi" in text
