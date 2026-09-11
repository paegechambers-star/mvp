import json
from pathlib import Path

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


@app.command()
def listen(
    file: Path,
    model: str = typer.Option("base", help="Whisper-Modellgröße: tiny|base|small|medium|large-v3"),
    language: str | None = typer.Option(None, help="Sprache erzwingen, z.B. 'de' (sonst Auto-Erkennung)"),
    timestamps: bool = typer.Option(False, help="Segmente mit Zeitstempeln statt Fließtext ausgeben"),
    output: Path | None = typer.Option(None, help="Transkript zusätzlich in Datei schreiben"),  # noqa: B008
    output_json: bool = typer.Option(False, "--json", help="Ausgabe als JSON (Text + Segmente + Metadaten)"),
):
    """Transkribiert eine MP3/Audiodatei lokal, damit Claude den Inhalt lesen ('hören') kann."""
    from . import audio

    if not file.exists():
        typer.secho(f"Datei nicht gefunden: {file}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        meta = audio.get_metadata(file)
        result = audio.transcribe_mp3(file, model_size=model, language=language)
    except audio.AudioToolError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if output_json:
        payload = {
            "file": str(file),
            "metadata": meta,
            "language": result.language,
            "language_probability": result.language_probability,
            "duration": result.duration,
            "text": result.text,
            "segments": [s.__dict__ for s in result.segments],
        }
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        typer.echo(rendered)
        if output:
            output.write_text(rendered, encoding="utf-8")
        return

    if meta:
        typer.echo(f"# Metadaten: {meta}")
    typer.echo(f"# Sprache: {result.language} (p={result.language_probability}) | Dauer: {result.duration}s")
    typer.echo("")

    if timestamps:
        rendered = "\n".join(f"[{s.start:>7.2f} - {s.end:>7.2f}] {s.text}" for s in result.segments)
    else:
        rendered = result.text

    typer.echo(rendered)
    if output:
        output.write_text(rendered, encoding="utf-8")
        typer.echo(f"\n# Transkript geschrieben nach: {output}", err=True)


if __name__ == "__main__":
    app()
