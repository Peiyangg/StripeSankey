import marimo

__generated_with = "0.11.8"
app = marimo.App(width="medium")


@app.cell
def _():
    from .widget import StripeSankeyInline
    return (StripeSankeyInline,)


@app.cell
def _():
    __version__ = "0.1.0"
    __all__ = ["StripeSankeyInline"]
    return __all__, __version__


if __name__ == "__main__":
    app.run()
