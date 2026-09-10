"""Deterministic provisional identities for sources without contributor IDs."""

from hashlib import sha256
import unicodedata


def normalized_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).casefold()
    return " ".join(
        "".join(
            c if c.isalnum() else " " for c in text if not unicodedata.combining(c)
        ).split()
    )


def provisional_id(source_key: str, name: str) -> str:
    # Scope unknown people to a publication: homonyms must not be merged by hash.
    digest = sha256(f"{source_key}\0{normalized_name(name)}".encode()).hexdigest()[:24]
    return f"provisional:{digest}"
