"""Structural tests for the dependency-free static frontend."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def test_every_page_references_existing_local_assets() -> None:
    """Every dashboard HTML page loads the shared stylesheet and its page module."""
    pages = {
        "index.html": "dashboard.js",
        "forecast.html": "forecast.js",
        "eta.html": "eta.js",
        "models.html": "models.js",
        "data.html": "data.js",
        "history.html": "history.js",
        "status.html": "status.js",
    }
    for page_name, module_name in pages.items():
        contents = (FRONTEND_ROOT / page_name).read_text(encoding="utf-8")
        assert 'rel="stylesheet" href="css/style.css"' in contents
        assert f'src="js/{module_name}"' in contents
        assert (FRONTEND_ROOT / "js" / module_name).is_file()


def test_api_client_declares_required_backend_endpoints() -> None:
    """The shared HTTP layer retains a single implementation for each API contract."""
    contents = (FRONTEND_ROOT / "js" / "api.js").read_text(encoding="utf-8")
    for endpoint in ("/health", "/forecast", "/eta", "/models", "/prediction-history", "/system-status", "/orders"):
        assert endpoint in contents


def test_frontend_uses_no_framework_build_dependencies() -> None:
    """Static pages remain independent of framework runtimes and Node build tooling."""
    forbidden_imports = ("react", "vue", "angular", "tailwind", "bootstrap")
    files = [*FRONTEND_ROOT.glob("*.html"), *(FRONTEND_ROOT / "js").glob("*.js")]
    contents = "\n".join(path.read_text(encoding="utf-8").lower() for path in files)
    assert all(f'from "{package}"' not in contents for package in forbidden_imports)
    assert "webpack" not in contents
    assert not (PROJECT_ROOT / "package.json").exists()
