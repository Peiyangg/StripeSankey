"""
Sphinx configuration for the StripeSankey documentation site.

Build it locally from the repository root::

    uv run --extra docs sphinx-build -b html docs docs/_build/html

or, without uv, ``pip install ".[docs]"`` and then the same ``sphinx-build``
command.

GitLab CI builds the same thing into ``public/`` and publishes it with GitLab
Pages -- see ``.gitlab-ci.yml``.
"""

import os
import sys

# Document the source tree, not whichever stripesankey happens to be installed.
sys.path.insert(0, os.path.abspath("../src"))

import stripesankey  # noqa: E402

project = "StripeSankey"
author = "Peiyang Huo"
copyright = "2025, Peiyang Huo"
release = stripesankey.__version__
version = release

extensions = [
    "myst_parser",               # pages are Markdown, like the README
    "sphinx.ext.autodoc",        # the API reference is read from the docstrings
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",       # the docstrings mix Google- and NumPy-style
    "sphinx.ext.viewcode",       # [source] links next to every function
]

source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
exclude_patterns = ["_build", "**/.DS_Store"]

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

autodoc_member_order = "bysource"
autosummary_generate = False

# -- HTML: the Read the Docs theme -- navigation left, content right ---------
html_theme = "sphinx_rtd_theme"
html_title = "StripeSankey"
html_logo = "StripeSankey_logo.png"
html_theme_options = {
    "logo_only": True,
    # the logo is dark text on a transparent background
    "style_nav_header_background": "#ffffff",
    # The sidebar lists the pages; only the current page shows its sections.
    "navigation_depth": 2,
    "collapse_navigation": True,
    # GitLab's file URLs are /-/blob/<branch>/<path>.
    "vcs_pageview_mode": "-/blob",
}
html_static_path = [
    "_static",
    # The interactive figures of the 1000 Genomes example, linked from
    # examples/human_genomics.md. Listed one by one so the rest of viz/ is not
    # copied into the site.
    "../example/population/viz/stripesankey_K2-8.html",
    "../example/population/viz/metasankey_K2-8.html",
]
html_css_files = ["custom.css"]
html_show_sourcelink = False

# "Edit on GitLab" in the top-right corner of every page.
html_context = {
    "display_gitlab": True,
    "gitlab_host": "gitlab.kuleuven.be",
    "gitlab_user": "aida-lab/public",
    "gitlab_repo": "StripeSankey",
    "gitlab_version": "main",
    "conf_py_path": "/docs/",
}


# These classes are returned by functions, never built by hand, and their
# inherited signatures (anywidget's ``*args, **kwargs``; every field of a
# dataclass) say nothing a reader can use.
_NO_SIGNATURE = {
    "stripesankey.StripeSankeyInline",
    "stripesankey.ClusterDendrogram",
    "stripesankey.ModeAnalysis",
}


def _drop_signature(app, what, name, obj, options, signature, return_annotation):
    if name in _NO_SIGNATURE:
        return "", None
    return None


def setup(app):
    app.connect("autodoc-process-signature", _drop_signature)
