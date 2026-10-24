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


@app.command("app")
def desktop(
    port: int = typer.Option(0, help="Port (0 = frei wählen)"),
    browser: bool = typer.Option(False, "--browser", help="Im Browser statt eigenem Fenster öffnen"),
):
    """Desktop-App: FraPP + SCRIPTOR (+ G.O.D.A.I.) in einem Fenster."""
    from scriptor.app.launcher import ensure_streams, launch

    ensure_streams()
    from .api import DOCKS, app as api_app

    scriptor = next((d for d in DOCKS if d.name == "scriptor"), None)
    if scriptor is None:
        typer.secho("SCRIPTOR-Dock nicht geladen (FRAPP_DISABLED_DOCKS?).", fg="red", err=True)
        raise typer.Exit(1)
    launch(scriptor.runtime, port=port, prefer_window=not browser,
           asgi=api_app, token=scriptor.token, path="/scriptor/", title="FraPP")


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
