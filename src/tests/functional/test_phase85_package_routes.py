"""Functional tests for Phase 8.5 package routes."""
import json
import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestPackageExport:
    """Tests for /api/rpg/package/export endpoint."""

    def test_export_package_returns_ok(self, client):
        payload = {
            "setup_payload": {
                "world": "test_world",
                "metadata": {
                    "simulation_state": {
                        "players": ["hero"],
                    }
                }
            }
        }
        response = client.post(
            "/api/rpg/package/export",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data["ok"] is True
        assert "package" in data
        assert data["package"]["package_type"] == "rpg_save_package"

    def test_export_package_with_empty_payload(self, client):
        payload = {"setup_payload": {}}
        response = client.post(
            "/api/rpg/package/export",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data["ok"] is True

    def test_export_package_with_no_payload(self, client):
        payload = {}
        response = client.post(
            "/api/rpg/package/export",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data["ok"] is True


class TestPackageValidate:
    """Tests for /api/rpg/package/validate endpoint."""

    def test_validate_valid_package(self, client):
        valid_package = {
            "package_type": "rpg_save_package",
            "schema_version": 3,
            "adventure": {
                "setup_payload": {"world": "test"},
                "metadata": {},
            },
            "state": {
                "simulation_state": {"world": "test"},
            },
        }
        payload = {"package": valid_package}
        response = client.post(
            "/api/rpg/package/validate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data["ok"] is True
        assert data["errors"] == []

    def test_validate_invalid_package_type(self, client):
        invalid_package = {
            "package_type": "wrong_type",
            "adventure": {"setup_payload": {}},
            "state": {"simulation_state": {}},
        }
        payload = {"package": invalid_package}
        response = client.post(
            "/api/rpg/package/validate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data["ok"] is False
        assert len(data["errors"]) > 0

    def test_validate_migrates_old_package(self, client):
        v1_package = {
            "schema_version": 1,
            "state": {
                "simulation_state": {
                    "world": "test",
                }
            },
        }
        # Need to add package_type for it to be valid after migration
        v1_package["package_type"] = "rpg_save_package"
        # Add minimal adventure structure
        v1_package["adventure"] = {"setup_payload": {}}
        payload = {"package": v1_package}
        response = client.post(
            "/api/rpg/package/validate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data["package"]["schema_version"] == 3


class TestPackageImport:
    """Tests for /api/rpg/package/import endpoint."""

    def test_import_valid_package(self, client):
        valid_package = {
            "package_type": "rpg_save_package",
            "schema_version": 3,
            "adventure": {
                "setup_payload": {"world": "test_world"},
                "metadata": {
                    "simulation_state": {"players": ["hero"]}
                },
            },
            "state": {
                "simulation_state": {"players": ["hero"]},
            },
        }
        payload = {"package": valid_package}
        response = client.post(
            "/api/rpg/package/import",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data["ok"] is True
        assert "setup_payload" in data

    def test_import_fails_on_invalid_package(self, client):
        invalid_package = {
            "package_type": "wrong",
            "adventure": {"setup_payload": {}},
            "state": {"simulation_state": {}},
        }
        payload = {"package": invalid_package}
        response = client.post(
            "/api/rpg/package/import",
            data=json.dumps(payload),
            content_type="application/json",
        )
        # Should fail because package_type is wrong (400 Bad Request for invalid client data)
        assert response.status_code == 400
