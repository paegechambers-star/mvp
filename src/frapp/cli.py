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
    uvicorn.run("frapp.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
