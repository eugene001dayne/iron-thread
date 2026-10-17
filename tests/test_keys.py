from attestation import generate_keypair, key_id
from attest_keys import load_or_create_private_key, public_from_private, trusted_public_keys


def test_creates_key_file_once_and_reuses_it(tmp_path, monkeypatch):
    monkeypatch.delenv("ATTEST_PRIVATE_KEY", raising=False)
    p = tmp_path / "k.key"
    first = load_or_create_private_key(p)
    second = load_or_create_private_key(p)
    assert first == second
    assert p.read_text().strip() == first


def test_never_overwrites_existing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ATTEST_PRIVATE_KEY", raising=False)
    priv, _ = generate_keypair()
    p = tmp_path / "k.key"
    p.write_text(priv + "\n")
    assert load_or_create_private_key(p) == priv
    assert p.read_text().strip() == priv


def test_env_var_wins_over_file(tmp_path, monkeypatch):
    priv, _ = generate_keypair()
    monkeypatch.setenv("ATTEST_PRIVATE_KEY", priv)
    p = tmp_path / "k.key"
    assert load_or_create_private_key(p) == priv
    assert not p.exists()


def test_public_key_matches_and_retired_keys_are_trusted(monkeypatch):
    priv, pub = generate_keypair()
    old_priv, old_pub = generate_keypair()
    monkeypatch.setenv("ATTEST_RETIRED_PUBLIC_KEYS", old_pub)
    keys = trusted_public_keys(priv)
    assert public_from_private(priv) == pub
    assert keys == {key_id(pub): pub, key_id(old_pub): old_pub}
