import uuid

import pytest
from typer.testing import CliRunner

from app.cli.main import app

runner = CliRunner()


@pytest.mark.requires_db
def test_project_create_persists_to_db():
    name = f"Test Project {uuid.uuid4().hex[:8]}"

    result = runner.invoke(app, ["project", "create", name])

    assert result.exit_code == 0, result.output
    assert "Created project" in result.output
    assert name in result.output


@pytest.mark.requires_db
def test_project_list_includes_created_project():
    name = f"Listable Project {uuid.uuid4().hex[:8]}"
    create_result = runner.invoke(app, ["project", "create", name])
    assert create_result.exit_code == 0, create_result.output

    list_result = runner.invoke(app, ["project", "list"])

    assert list_result.exit_code == 0, list_result.output
    slug = name.lower().replace(" ", "-")
    assert slug in list_result.output
