from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_database_is_private_and_dev_prod_are_isolated():
    dev = yaml.safe_load((ROOT / "compose.dev.yml").read_text())
    prod = yaml.safe_load((ROOT / "compose.prod.yml").read_text())
    assert dev["name"] != prod["name"]
    for config in (dev, prod):
        assert not config["services"]["db"].get("ports")
        assert "pgdata:/var/lib/postgresql/data" in config["services"]["db"]["volumes"]
        assert config["services"]["web"]["ports"][0].startswith("127.0.0.1:")
    assert prod["networks"]["private"]["internal"] is True
    assert prod["services"]["tunnel"]["networks"] == ["edge"]
    assert prod["services"]["tunnel"]["profiles"] == ["tunnel"]
    assert (
        prod["services"]["backup"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    )
    for name in ("db", "api", "web", "backup", "tunnel"):
        assert prod["services"][name]["restart"] == "unless-stopped"
    assert prod["services"]["api"]["environment"]["SECURE_COOKIES"] == "true"
    assert (
        prod["services"]["db"]["environment"]["POSTGRES_USER"]
        != prod["services"]["api"]["environment"]["POSTGRES_USER"]
    )
