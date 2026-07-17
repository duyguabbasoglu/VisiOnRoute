"""VISiOnRoute CLI (Typer).

Subcommand groups are registered per milestone:
  keys    — development JWT key generation
  admin   — one-time platform admin bootstrap (M2)
  worker  — outbox/job consumer (M4+)
  demo    — synthetic demo data, clearly marked (M5+)
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from visionroute.cli.admin import app as admin_app
from visionroute.cli.simulate import app as simulate_app
from visionroute.observability.logging import configure_logging

app = typer.Typer(name="visionroute", no_args_is_help=True, add_completion=False)
keys_app = typer.Typer(no_args_is_help=True, help="JWT anahtar yönetimi (yalnızca geliştirme).")
app.add_typer(keys_app, name="keys")
app.add_typer(admin_app, name="admin")
app.add_typer(simulate_app, name="simulate")


@app.callback()
def _init() -> None:
    configure_logging(json_output=False, level=logging.INFO)


@keys_app.command("generate")
def keys_generate(
    out: Path = typer.Option(Path(".dev/keys"), help="Anahtar dosyalarının yazılacağı dizin."),
) -> None:
    """RS256 geliştirme anahtar çifti üretir. Üretimde Secrets Manager kullanın."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    out.mkdir(parents=True, exist_ok=True)
    private_path = out / "jwt-private.pem"
    public_path = out / "jwt-public.pem"
    if private_path.exists():
        typer.echo(f"{private_path} zaten var; üzerine yazılmadı.")
        raise typer.Exit(1)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_path.chmod(0o600)
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    typer.echo(f"Anahtarlar üretildi: {private_path}, {public_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
