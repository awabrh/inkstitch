# Ink/Stitch Extension System and Runtime

This document explains how Ink/Stitch runs inside Inkscape, how its `.inx` files are generated, and how the codebase routes one generic process entrypoint to many different extension implementations.

It is written for readers who are new both to Inkscape extensions and to the Ink/Stitch codebase.

## The big picture

Ink/Stitch is **not one extension**. It is a **suite of many Inkscape extensions**:

- effect extensions, such as parameter editors, tools, and commands in the Extensions menu
- input extensions, which let Inkscape open embroidery formats as SVG-based Ink/Stitch documents
- output extensions, which let Inkscape save an Ink/Stitch SVG as a machine embroidery file

Most of those extensions share the same executable entrypoint: [inkstitch.py](../inkstitch.py). That file is a **dispatcher**. It does startup work, reads a hidden `--extension` argument, looks up the corresponding extension class in [lib/extensions/__init__.py](../lib/extensions/__init__.py), instantiates it, and runs it.

The connection between Inkscape and that dispatcher is a generated `.inx` manifest file in [inx/](../inx/). The `.inx` file is **not the implementation**. It is registration and runtime metadata that tells Inkscape:

- what the extension is called
- where it appears in the UI
- whether it is an effect, input, or output extension
- what parameters it exposes
- what executable command to launch
- what hidden arguments to pass to that command

If you keep those roles separate, the rest of the system becomes much easier to understand:

1. templates in [templates/](../templates/) describe extension manifests
2. generators in [lib/inx/](../lib/inx/) render those templates into concrete `.inx` files in [inx/](../inx/)
3. Inkscape reads the generated `.inx` files and launches Ink/Stitch
4. [inkstitch.py](../inkstitch.py) dispatches to a class in [lib/extensions/](../lib/extensions/)
5. that class performs the actual work

## 1. What an Inkscape extension is in practical terms

In practical terms, an Inkscape extension is an **external program** that Inkscape knows how to launch.

Inkscape does not learn about that program by scanning Python classes. Instead, it learns about it from an `.inx` XML file. That XML manifest describes both the user-facing part of the extension and the runtime contract for invoking it.

Depending on the extension type, Inkscape expects different inputs and outputs:

| Extension type | Triggered from | Main input | Main output |
| --- | --- | --- | --- |
| Effect | Extensions menu | current SVG document | updated SVG document |
| Input | File open/import flow | foreign file path | SVG document |
| Output | Save/export flow | current SVG document | non-SVG output bytes |

That last row is important: for an output extension, writing embroidery bytes to standard output is the correct behavior. It is not an accident.

## 2. What `.inx` manifests are and why they exist

A `.inx` file is an **Inkscape extension manifest**. Inkscape consumes it; Ink/Stitch generates it.

An `.inx` file usually contains several kinds of information:

- a stable extension ID
- the human-readable name shown in the UI
- whether the extension is an `effect`, `input`, or `output`
- menu placement, menu tips, and icons for effect extensions
- visible and hidden parameters
- the command that Inkscape should execute

### A concrete effect example: `templates/params.xml`

[templates/params.xml](../templates/params.xml) is a representative effect manifest template. It defines:

- `<name>Params</name>`: the UI label
- `<id>org.{{ id_inkstitch }}.params</id>`: a globally unique ID
- `<param name="extension" ...>params</param>`: a hidden parameter telling the dispatcher which class to run
- an `<effect>` section describing menu placement, object applicability, icon, and tooltip
- a `<script>` section telling Inkscape what command to launch

The critical point is that the manifest does **not** contain the implementation of the parameter editor. It only tells Inkscape how to invoke it.

### Input manifests

[templates/input.xml](../templates/input.xml) shows the structure for input extensions. It contains an `<input>` block instead of `<effect>`, including:

- the file extension, such as `.dst`
- the MIME type
- the user-facing file type name and tooltip
- a hidden `extension=input` parameter
- the script command to run

This tells Inkscape that when the user opens a supported embroidery file, Ink/Stitch should be launched as an **input converter**.

### Output manifests

[templates/output.xml](../templates/output.xml) is the output counterpart. It contains an `<output>` block and hidden parameters including:

- `extension=output`
- `format=<file format>`

That second hidden parameter is how one generic `Output` class can serve many output formats.

The template also includes an optional file such as `output_params_gcode.xml` through Jinja's `{% include %}` mechanism. This allows specific output formats to add extra options without duplicating the whole manifest template.

## 3. How Ink/Stitch generates manifests

Ink/Stitch does **not** hand-maintain every `.inx` file. Instead, it generates them from templates.

This generation layer exists because Ink/Stitch has many extensions and many supported file formats. Hand-editing all resulting manifests would be repetitive and error-prone. Generation solves several problems at once:

- keeps extension IDs and naming conventions consistent
- keeps menu names and command tags consistent
- keeps supported input and output formats synchronized with `pystitch`
- allows source builds and packaged builds to emit different command paths
- allows alternate extension namespaces for side-by-side installations
- reduces duplicated XML across many related manifests

### The generator entrypoint: `lib/inx/generate.py`

[lib/inx/generate.py](../lib/inx/generate.py) is the top-level orchestrator. Its `generate_inx_files()` function computes two important values:

- `id_inkstitch`
- `menu_inkstitch`

Normally those are `inkstitch` and `Ink/Stitch`. When the optional `alter` argument is supplied, they become values like `k-inkstitch` and `Ink/Stitch-k`. This supports running multiple Ink/Stitch installations side by side in one Inkscape instance.

It then calls three specialized generators:

- [lib/inx/inputs.py](../lib/inx/inputs.py)
- [lib/inx/outputs.py](../lib/inx/outputs.py)
- [lib/inx/extensions.py](../lib/inx/extensions.py)

### Input manifest generation: `lib/inx/inputs.py`

[lib/inx/inputs.py](../lib/inx/inputs.py) asks `pystitch` for supported formats and filters that list down to reader-capable formats in the relevant categories. For each supported format it renders [templates/input.xml](../templates/input.xml) and writes a generated manifest into [inx/](../inx/).

This means the set of importable formats is largely data-driven instead of being copied into many separate files by hand.

### Output manifest generation: `lib/inx/outputs.py`

[lib/inx/outputs.py](../lib/inx/outputs.py) does the equivalent job for writer-capable formats. It renders [templates/output.xml](../templates/output.xml) once per supported writer format and passes values such as:

- file extension
- description
- MIME type
- category

The generator also decorates some descriptions with tags such as `[COLOR]`, `[IMAGE]`, `[STITCH]`, `[QUILTING]`, or `[DEBUG]` so the generated output entries are clearer in the UI.

### Effect manifest generation: `lib/inx/extensions.py`

[lib/inx/extensions.py](../lib/inx/extensions.py) handles Ink/Stitch's non-input, non-output extensions.

It imports the `extensions` list from [lib/extensions/__init__.py](../lib/extensions/__init__.py), then iterates over every extension class except the generic `Input` and `Output` classes.

For each class, it:

1. computes the extension name in `snake_case`
2. loads a matching template from [templates/](../templates/)
3. renders the template with shared data such as thread palettes, font categories, output formats, and command lists
4. writes the rendered manifest to [inx/](../inx/)

This file also respects the `DEVELOPMENT_ONLY` flag from [lib/extensions/base.py](../lib/extensions/base.py). If an extension class is marked as development-only and the `BUILD` environment variable is set, the generator skips it so it does not appear in release builds.

### Shared generation utilities: `lib/inx/utils.py`

[lib/inx/utils.py](../lib/inx/utils.py) provides two key utilities:

- `build_environment()`, which constructs the Jinja environment and sets build-dependent globals
- `write_inx_file()`, which writes rendered XML into [inx/](../inx/)

`build_environment()` is where one of the most important development-versus-release differences is encoded. It sets the manifest's `<command>` differently depending on whether the `BUILD` environment variable is present:

- **source/development mode**: run `../inkstitch.py` with `interpreter="python"`
- **packaged build**: run a bundled binary such as `../bin/inkstitch`, `../bin/inkstitch.exe`, or the macOS app binary path

It also adjusts the icon path accordingly.

### How generation is triggered

The script [bin/generate-inx-files](../bin/generate-inx-files) is the command-line helper that actually runs generation. It prepares the Python import path, ensures `inkex` can be imported, and then calls `generate_inx_files()`.

The [Makefile](../Makefile) uses that script in the `inx` target, and packaged builds set `BUILD` so the generated manifests point to release binaries instead of source files.

## 4. The naming contract that ties the system together

There is a deliberate round-trip naming convention connecting templates, generated manifests, hidden parameters, and Python classes.

For a normal effect extension:

1. the class name is CamelCase, for example `Params`
2. [lib/extensions/base.py](../lib/extensions/base.py) converts that to `snake_case` via `InkstitchExtension.name()`, yielding `params`
3. [lib/inx/extensions.py](../lib/inx/extensions.py) loads [templates/params.xml](../templates/params.xml)
4. the generated manifest contains hidden `extension=params`
5. [inkstitch.py](../inkstitch.py) converts `params` back to `Params`
6. the dispatcher looks up `Params` in [lib/extensions/__init__.py](../lib/extensions/__init__.py)

That is why the hidden `extension` parameter matters so much. It is the bridge from the generated manifest back to the implementation class.

`Input` and `Output` are special cases:

- many generated input manifests all use hidden `extension=input`
- many generated output manifests all use hidden `extension=output`
- output manifests also include a hidden `format=<...>` parameter so one class can handle many formats

## 5. How Inkscape launches Ink/Stitch

Once the manifests exist and are installed where Inkscape can see them, Inkscape uses them as launch instructions.

At runtime, the sequence is roughly:

1. the user triggers an extension from a menu, opens an embroidery file, or saves to an embroidery format
2. Inkscape looks up the corresponding generated `.inx` file
3. Inkscape reads the manifest's parameters and `<script>` command
4. Inkscape launches the configured command as a separate process
5. Ink/Stitch receives hidden parameters such as `--extension=params`, `--extension=input`, or `--extension=output --format=pes`
6. the launched Ink/Stitch code performs the requested action and writes the expected result back to Inkscape

From Ink/Stitch's point of view, this is a process contract built around arguments, standard streams, and the `inkex` framework.

One subtle but important detail in [inkstitch.py](../inkstitch.py) is that it only parses the `--extension` argument itself. It leaves all other arguments in place for the called extension class or for `inkex`. That is why it uses `parse_known_args()` rather than trying to define the full CLI centrally.

## 6. How `inkstitch.py` dispatches to a concrete extension class

[inkstitch.py](../inkstitch.py) is the runtime entrypoint that nearly all generated manifests invoke.

Its job is not to implement every feature. Its job is to set up the runtime environment and route execution to the right class.

### Startup behavior

Before it dispatches, [inkstitch.py](../inkstitch.py) performs several pieces of startup work:

- determines `SCRIPTDIR`
- loads `DEBUG.toml` if present
- determines whether it is running as a frozen binary by checking `sys.frozen`
- refuses to run with no arguments, because Ink/Stitch is meant to be launched by Inkscape or by explicit developer tooling
- configures logging through `lib.debug.logging`
- decides whether it is running from Inkscape or in an offline/developer context
- in development mode, optionally reorders `sys.path` to prefer a pip-installed `inkex`
- enables debugging or profiling if configured

That setup work exists because the same entrypoint must function in both developer and packaged environments.

### Dispatch logic

The core dispatch sequence is straightforward:

1. import [lib/extensions/__init__.py](../lib/extensions/__init__.py)
2. parse hidden `--extension`
3. convert the extension name from `snake_case` to CamelCase by calling `title().replace("_", "")`
4. look up that class in the imported `lib.extensions` module with `getattr()`
5. instantiate the class
6. call `extension.run(args=remaining_args)`

For example:

- manifest hidden parameter: `params`
- computed class name: `Params`
- imported target: `lib.extensions.Params`

This is why [lib/extensions/__init__.py](../lib/extensions/__init__.py) is so important: it is both the dispatch registry and one of the inputs to `.inx` generation.

### Error handling and debug-versus-normal execution

[inkstitch.py](../inkstitch.py) runs extensions differently depending on whether debugging or profiling is active.

- In debug or profiling mode, it calls the extension more directly so debugging tools can see the real stack behavior.
- In normal mode, it wraps execution in a `try/except` block that catches common failures and reports them in a way that is appropriate for Inkscape users.

In normal mode it specifically handles:

- `XMLSyntaxError`, with a user-facing message about malformed SVG imports
- `InkstitchException`, which is shown directly to the user
- uncaught generic exceptions, which are formatted and displayed as errors

It also temporarily redirects `stderr` through helper functions in `lib.utils` to hide noisy GTK output from users.

## 7. What `lib/extensions/__init__.py` does

[lib/extensions/__init__.py](../lib/extensions/__init__.py) has two roles.

First, it imports all supported extension classes into one module namespace. That is what makes `getattr(extensions, extension_class_name)` in [inkstitch.py](../inkstitch.py) work.

Second, it defines the `extensions` list. [lib/inx/extensions.py](../lib/inx/extensions.py) iterates over that list when generating effect manifests.

So this file is effectively the central registration point for Ink/Stitch's extension suite.

If an extension class is not imported here, two things break at once:

- the dispatcher cannot find it at runtime
- the generator will not create its `.inx` manifest

## 8. What `InkstitchExtension` provides

Most effect-style Ink/Stitch extensions inherit from `InkstitchExtension` in [lib/extensions/base.py](../lib/extensions/base.py). That class itself subclasses `inkex.EffectExtension`.

This shared base class exists so that common document handling and embroidery-specific helpers do not have to be reimplemented in every effect.

### Automatic document updating in `load()`

The most important customization is `load()`. After letting `inkex` load the SVG document, it calls `update_inkstitch_document()` from [lib/update.py](../lib/update.py).

That means a large part of the extension suite automatically works on an up-to-date Ink/Stitch document model instead of each extension having to remember to upgrade legacy metadata on its own.

This is one reason the base class matters: it makes document version migration part of the normal loading lifecycle.

### Naming helper

`InkstitchExtension.name()` converts a class name from CamelCase to `snake_case`. That helper is used by the `.inx` generator and is part of the naming contract described earlier.

### Document and layer helpers

The base class also provides utility methods such as:

- `hide_all_layers()`
- `get_current_layer()`
- `get_base_file_name()`
- `uniqueId()`

These are convenience helpers that many extensions can reuse without duplicating SVG-specific logic.

### Selection and element traversal

Embroidery operations usually do not work on raw XML nodes directly. The base class provides a path from the current SVG selection to higher-level Ink/Stitch element objects.

Key helpers are:

- `get_nodes()`: traverses the selected nodes and descendants, or the whole document when nothing is selected
- `get_elements()`: converts traversed nodes into embroidery-aware element wrappers using `nodes_to_elements()`
- `no_elements_error()`: reports a user-friendly error if nothing embroiderable is available

This is the shared bridge between the SVG document and Ink/Stitch's embroidery object model.

### Converting elements to stitch groups

`elements_to_stitch_groups()` runs each embroiderable element through its `embroider()` method and collects the resulting stitch groups.

This is a crucial common step because many operations need to move from:

SVG selection -> Ink/Stitch elements -> stitch groups -> stitch plan -> exported output

The base class handles the early part of that pipeline so concrete extensions can focus on their specific job.

## 9. Effect, input, and output extensions are different runtime contracts

These three extension categories should not be mentally collapsed into one generic “extension” concept. They read different things, write different things, and often do not even use the same base class.

### Effect extensions

An effect extension is the most familiar Inkscape extension type. It operates on the current SVG document.

In Ink/Stitch, most effect extensions:

1. subclass `InkstitchExtension`
2. inherit `inkex.EffectExtension` behavior through that base class
3. let `inkex` load the current SVG document
4. run their custom `effect()` logic
5. return control to `inkex`, which writes the resulting SVG back to Inkscape

In other words, effect extensions are usually “SVG in, SVG out,” even if the extension's actual purpose is embroidery-related.

### Output extensions

[lib/extensions/output.py](../lib/extensions/output.py) implements the generic output extension.

An output extension is **not** just another effect with a different menu location. Its contract is different:

- it reads the current Ink/Stitch SVG document
- it converts that document into embroidery data
- it writes the final file bytes to standard output
- it intentionally stops the normal `inkex` SVG output path

The `Output` class still subclasses `InkstitchExtension`, because it needs document loading, selection handling, metadata, and stitch generation helpers. But its end result is not SVG.

`Output.parse_arguments()` is also special. It manually separates output-format options from the arguments that `inkex` should parse, because output formats may accept arbitrary `--name=value` options that the normal `inkex` parser is not prepared for.

In `effect()`, `Output` does the following:

1. gather embroiderable elements with `get_elements()`
2. read document metadata such as stitch length and collapse settings
3. convert elements to stitch groups
4. convert stitch groups to a stitch plan
5. apply thread palette matching
6. write the embroidery result to a temporary file
7. stream that file's bytes to `sys.stdout.buffer`
8. delete the temporary file
9. call `sys.exit(0)` so `inkex` does not append SVG afterward

That last step is essential. If `inkex` were allowed to continue with its default behavior, the process could emit SVG after the binary embroidery bytes, corrupting the output.

The temporary file exists because the lower-level writer in [lib/output.py](../lib/output.py) writes to a file path and delegates format-specific serialization to `pystitch`. `Output` then copies those bytes to stdout because that is what Inkscape expects from an output extension process.

### Input extensions

[lib/extensions/input.py](../lib/extensions/input.py) implements the generic input extension.

Input is not simply the mirror image of output.

An input extension does **not** take an existing SVG, modify it, and return another SVG. Instead, it takes a foreign embroidery file path and **creates a new SVG document** representing that design in a way Ink/Stitch can work with.

That is why `Input` does not subclass `InkstitchExtension` or `inkex.EffectExtension`. Its workflow is much simpler and different:

1. receive the input file path from Inkscape
2. reject color sidecar files such as `.edr`, `.col`, and `.inf`, because those are not full embroidery designs to import on their own
3. call `generate_stitch_plan()` to build an SVG-like stitch-plan document from the embroidery file
4. set the document's `inkstitch_svg_version` metadata so later Ink/Stitch operations know it is current
5. serialize the generated document to text
6. print that SVG text to standard output

This is why input and output are not “symmetric” in a simplistic sense:

- output converts an existing Ink/Stitch SVG into a foreign file format
- input converts a foreign file format into a new Ink/Stitch-compatible SVG document

## 10. Standard streams, temporary files, and process behavior

If you are new to Inkscape extensions, the most non-obvious part of the system is that the runtime contract is largely about **process I/O**.

Inkscape launches Ink/Stitch as a process. The process type determines what Inkscape expects back.

### When Ink/Stitch emits SVG

Ink/Stitch emits SVG in two major cases:

- normal effect extensions, usually via `inkex`'s standard `EffectExtension` lifecycle
- input extensions, which generate a new SVG document from an embroidery file and print it explicitly

### When Ink/Stitch emits non-SVG data

Ink/Stitch emits non-SVG bytes for output extensions. That behavior is deliberate and required.

`Output.effect()` switches standard output to binary mode on Windows, reads the produced file in binary mode, and writes those bytes to `sys.stdout.buffer`. This is how the generated embroidery file reaches Inkscape's save/export flow.

### Why temporary files are used

The temporary file in [lib/extensions/output.py](../lib/extensions/output.py) is not there because Ink/Stitch prefers files over streams in general. It is there because the lower-level writer in [lib/output.py](../lib/output.py) writes a format-specific embroidery file to a file path.

So the sequence is:

1. generate stitch data in memory
2. write the final format to a temporary file using the existing writer stack
3. stream the finished bytes to stdout for Inkscape
4. clean up the file

### Why some extensions intentionally call `sys.exit()`

For normal effect extensions, the `inkex` lifecycle eventually serializes SVG output. For output extensions, that would be the wrong thing to do.

After writing the export bytes, `Output.effect()` calls `sys.exit(0)` specifically to stop further processing. Without that explicit exit, the generic effect machinery could continue and emit SVG, which would violate the output-extension contract.

## 11. Development mode versus packaged mode

Ink/Stitch supports two important runtime contexts:

- running from source as a developer
- running as a packaged or frozen release

They are similar from Inkscape's point of view, but they are not identical.

### Manifest differences

The most visible difference is in [lib/inx/utils.py](../lib/inx/utils.py):

- in development mode, generated manifests execute `../inkstitch.py` with `interpreter="python"`
- in packaged builds, generated manifests execute the bundled binary directly

That difference is why the same template can support both environments.

### Build-time filtering

[lib/inx/extensions.py](../lib/inx/extensions.py) skips `DEVELOPMENT_ONLY` extensions when `BUILD` is set. That lets the source tree contain helper extensions that are useful to contributors without exposing them in release builds.

### Entrypoint behavior differences

[inkstitch.py](../inkstitch.py) also behaves differently depending on environment:

- it detects frozen mode through `sys.frozen`
- in source mode, `DEBUG.toml` can influence debugger and profiler setup
- in source mode, it may reorder `sys.path` to prefer a pip-installed `inkex`
- when launched with no arguments in a frozen build, it may show a GUI dialog instead of only printing to `stderr`
- in frozen normal mode, it suppresses warnings that would be unhelpful in end-user installations

### Build scripts in context

The build scripts do not define the extension runtime themselves, but they matter because they set the environment in which manifests are generated.

For example, the [Makefile](../Makefile) and packaging scripts set `BUILD`, which changes the command paths written into generated `.inx` files.

## 12. End-to-end examples

### Example A: an effect extension such as `Params`

1. [templates/params.xml](../templates/params.xml) is rendered into a generated `.inx` file in [inx/](../inx/)
2. the manifest includes hidden `extension=params`
3. the user launches the extension from Inkscape's Extensions menu
4. Inkscape executes the command from the manifest's `<script>` section
5. [inkstitch.py](../inkstitch.py) reads `--extension=params`
6. it converts `params` to `Params`
7. it finds `Params` in [lib/extensions/__init__.py](../lib/extensions/__init__.py)
8. it instantiates the class and calls `run()`
9. `inkex` loads the SVG document, while [lib/extensions/base.py](../lib/extensions/base.py) upgrades legacy document metadata during `load()`
10. the extension's `effect()` method runs
11. `inkex` serializes the updated SVG back to Inkscape

### Example B: importing a `.dst` file

1. [templates/input.xml](../templates/input.xml) is rendered into a format-specific input manifest
2. the manifest registers `.dst` as a supported input extension and passes hidden `extension=input`
3. the user opens a `.dst` file in Inkscape
4. Inkscape launches Ink/Stitch with the file path
5. [inkstitch.py](../inkstitch.py) dispatches to `Input`
6. [lib/extensions/input.py](../lib/extensions/input.py) converts the embroidery file into an SVG stitch-plan document
7. it prints that SVG to stdout
8. Inkscape receives the SVG as the opened document

### Example C: exporting a `.pes` file

1. [templates/output.xml](../templates/output.xml) is rendered into a format-specific output manifest
2. the manifest passes hidden `extension=output` and `format=pes`
3. the user saves or exports using that format
4. Inkscape launches Ink/Stitch
5. [inkstitch.py](../inkstitch.py) dispatches to `Output`
6. [lib/extensions/output.py](../lib/extensions/output.py) parses the output options and loads the current SVG
7. it converts the SVG embroidery objects into a stitch plan
8. it writes the final PES file to a temporary file via [lib/output.py](../lib/output.py)
9. it copies the PES bytes to stdout
10. it exits immediately so no SVG is appended

## 13. Common failure modes and debugging advice

### “Ink/Stitch is not doing anything when I run `inkstitch.py` directly”

That usually means the script was launched without the arguments Inkscape normally supplies. [inkstitch.py](../inkstitch.py) explicitly guards against this and exits with a message, because the normal contract is to be launched by Inkscape or by developer tooling that simulates that environment.

### The extension appears in code but not in Inkscape

Check the full registration chain:

1. is the class imported in [lib/extensions/__init__.py](../lib/extensions/__init__.py)?
2. is there a matching template in [templates/](../templates/)?
3. was manifest generation run so the file exists in [inx/](../inx/)?
4. is the generated extension filtered out by `DEVELOPMENT_ONLY` and `BUILD`?

If any one of those steps is missing, the extension may exist in Python code but still not be registered with Inkscape.

### A manifest exists but dispatch fails

This usually points to a naming contract problem. The hidden `extension` parameter, the template name, and the class name all have to agree.

For example, a hidden `extension=lettering_remove_kerning` expects a class named `LetteringRemoveKerning` to be imported by [lib/extensions/__init__.py](../lib/extensions/__init__.py).

### Output files are corrupted

One likely cause is misunderstanding the output extension contract. Output extensions must emit only the export bytes, not SVG afterward. That is why [lib/extensions/output.py](../lib/extensions/output.py) explicitly exits after writing to stdout.

### Old documents behave strangely

Remember that [lib/extensions/base.py](../lib/extensions/base.py) automatically updates documents through [lib/update.py](../lib/update.py) during load. If you are debugging legacy-file behavior, document upgrading is part of the runtime path and should be considered.

### Input import does not work for `.edr`, `.col`, or `.inf`

That is intentional. [lib/extensions/input.py](../lib/extensions/input.py) rejects those formats as standalone imports and instead tells the user to apply thread lists after importing the main embroidery file.

### Regenerate manifests when changing extension metadata

If you change a template, supported format list, or extension registration, remember that Inkscape only sees generated `.inx` files. The generated files in [inx/](../inx/) must be refreshed, typically through [bin/generate-inx-files](../bin/generate-inx-files) or the [Makefile](../Makefile) target that calls it.

## 14. Summary

If you remember only a few things, remember these:

- Ink/Stitch is a **suite** of extensions, not a single monolithic extension.
- A `.inx` file is **manifest metadata**, not the implementation.
- [inkstitch.py](../inkstitch.py) is a **dispatcher**, not the home of all extension logic.
- [lib/extensions/__init__.py](../lib/extensions/__init__.py) is the central registry used by both dispatch and manifest generation.
- [lib/extensions/base.py](../lib/extensions/base.py) gives most effect-style extensions their shared document-loading, upgrading, selection, and stitch-conversion behavior.
- Input, effect, and output extensions have **different runtime contracts**.
- Output extensions may intentionally write non-SVG bytes to stdout and then exit.
- Development and packaged builds differ mainly in manifest command paths, extension visibility, and debugging/runtime setup.

Once that model is clear, the runtime path becomes predictable:

generated `.inx` manifest -> Inkscape launches command -> [inkstitch.py](../inkstitch.py) reads `--extension` -> dispatch to `lib/extensions/*` class -> extension performs its specific effect/input/output contract.
