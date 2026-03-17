We're so happy you're interested in contributing to Ink/Stitch!  There's a lot that we need help with for people with all skill levels and backgrounds.

Before you contribute, **please have a look at our [code of conduct](CODE_OF_CONDUCT.md)**.  Thanks!

**There's never any time commitment, we're all here to have fun.**  If you want to contribute, let us know and we'll add you as a collaborator.

Feel free to find something that interests you.  If you're looking for ideas, consider this list:

* coding (Python, Javascript)
  * **please read our [coding style guide](CODING_STYLE.md)**
* build / CI system (GitHub actions)
* translations ([how to translate](https://github.com/inkstitch/inkstitch/blob/main/LOCALIZATION.md))
* issue upkeep and management
* artwork
* documentation (see [gh-pages branch](https://github.com/inkstitch/inkstitch/tree/gh-pages))


Development environment setup
=============================

Ink/Stitch's native contributor/build workflow assumes:

- Python 3.11
- Inkscape installed with the `inkscape` CLI available on `PATH`
- a normal virtual environment where the active interpreter is named `python`

The CI build uses Python 3.11.x on all platforms, so that is the safest local version to use too.

Quick start
-----------

1. Install the required system packages for your platform.
2. Run:

  ```sh
  make setup-python-env
  source .venv/bin/activate
  ```

3. Build INX files:

  ```sh
  make inx
  ```

4. Run tests or packaging tasks as needed:

  ```sh
  pytest
  make dist
  ```

The helper target creates `.venv`, installs the Python dependencies used by local builds, and keeps the workflow native to the project: activate the virtualenv first, then run `make` so `python` resolves to the environment interpreter.

macOS prerequisites
-------------------

The macOS build workflow installs these packages with Homebrew:

```sh
brew install gtk+3 pkg-config gobject-introspection geos libffi gettext jq gnu-getopt
```

`make setup-python-env` will install these Homebrew packages automatically on macOS if they are missing.

If you are on Apple Silicon and your Python 3.11 interpreter is not the default one on `PATH`, run the setup with `PYTHON_BIN` set explicitly, for example:

```sh
PYTHON_BIN=/opt/homebrew/bin/python3.11 make setup-python-env
```

Linux prerequisites
-------------------

The Linux CI environment installs these system packages before Python dependencies:

```sh
sudo apt-get update
sudo apt-get install gettext libnotify4 glib-networking libsdl2-dev libsdl2-2.0-0
sudo apt-get install libgirepository1.0-dev libcairo2-dev
sudo apt-get install build-essential libgtk-3-dev cmake
sudo apt-get install gfortran libopenblas-dev liblapack-dev pkg-config
```

Windows notes
-------------

The Windows CI workflow also uses Python 3.11 and installs dependencies into a normal Python environment before running `make dist`.  For contributor work, the simplest approach is to create a Python 3.11 virtualenv manually, install `requirements-build.txt`, then run the same `make` targets from an activated shell.

Important notes
---------------

- `make inx` intentionally runs `python bin/generate-inx-files`, so the virtualenv must be activated first.
- `make inx` also assumes the `inkscape` executable is on `PATH` so the project can locate the bundled `inkex` module.
- The helper bootstrap script is for the supported native flow.  It does not use `uv`.


No AI-written Pull Requests
===========================

Please don't create pull requests written entirely or in large part by LLM-based tools such as Claude, Cursor, etc.  We don't accept contributions of this sort and they will be closed without review.
