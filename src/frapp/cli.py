import os
import secrets

import typer
import uvicorn

from .settings import settings

app = typer.Typer(add_completion=False)


@app.command()
def version():
    """Print FraPP version."""
    typer.echo(settings.version)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = True):
    """Run API server."""
    # Fester Token für eingebettete Docks (SCRIPTOR), damit die URL hier ausgegeben werden kann
    token = os.environ.setdefault("FRAPP_SCRIPTOR_TOKEN", secrets.token_urlsafe(24))
    typer.echo(f"SCRIPTOR: http://127.0.0.1:{port}/scriptor/#token={token}")
    uvicorn.run("frapp.api:app", host=host, port=port, reload=reload)


def prepare_desktop() -> str:
    """
    Desktop-Modus vorbereiten (vor dem Import von frapp.api aufrufen):

    - Datenbank unter %APPDATA%\\FraPP (bzw. ~/.local/share/frapp), falls DATABASE_URL fehlt
    - ein zufälliger Zugriffsschlüssel pro Start für FraPP-API und SCRIPTOR
    - API-Key aus dem OS-Tresor auch für den G.O.D.A.I.-Chat
    Gibt den Schlüssel zurück.
    """
    from .paths import sqlite_url

    if not os.environ.get("DATABASE_URL"):
        settings.database_url = sqlite_url()
    token = os.environ.get("FRAPP_SCRIPTOR_TOKEN") or secrets.token_urlsafe(24)
    os.environ["FRAPP_SCRIPTOR_TOKEN"] = token
    settings.api_key = token
    if not settings.anthropic_api_key:
        try:
            from scriptor.settings import get_api_key

            settings.anthropic_api_key = get_api_key() or ""
        except ImportError:
            pass
    return token


@app.command("app")
def desktop(
    port: int = typer.Option(0, help="Port (0 = frei wählen)"),
    browser: bool = typer.Option(
        False, "--browser", help="Im Browser statt eigenem Fenster öffnen"
    ),
):
    """Desktop-App: Tagesplan, Kalender, SCRIPTOR, G.O.D.A.I., ContextOS in einem Fenster."""
    from scriptor.app.launcher import ensure_streams, launch

    ensure_streams()
    token = prepare_desktop()
    from .api import DOCKS
    from .api import app as api_app

    scriptor = next((d for d in DOCKS if d.name == "scriptor"), None)
    if scriptor is None:
        typer.secho("SCRIPTOR-Dock nicht geladen (FRAPP_DISABLED_DOCKS?).", fg="red", err=True)
        raise typer.Exit(1)
    launch(
        scriptor.runtime,
        port=port,
        prefer_window=not browser,
        asgi=api_app,
        token=token,
        path="/app/",
        title="FraPP",
    )


def _mount_dock_cli() -> None:
    """CLI-Befehle der Docks einhängen: frapp scriptor …"""
    from .docks import load_docks

    for dock in load_docks():
        sub = dock.cli()
        if sub is not None:
            app.add_typer(sub, name=dock.name, help=f"{dock.name} (Dock)")


def main():
    _mount_dock_cli()
    app()


if __name__ == "__main__":
    main()
