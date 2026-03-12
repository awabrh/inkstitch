# Ink/Stitch Advanced Subsystems and Contributor Workflow

This document covers the important parts of Ink/Stitch that sit outside the narrow “SVG shape in, stitches out” path. If you already understand the basic element pipeline, this is the next layer: the parts of the repository that make the system practical, extensible, and sometimes surprising.

The main idea to keep in mind is simple:

> In Ink/Stitch, embroidery behavior is not determined only by the visible base shape.

Important behavior can also come from command symbols, guide and pattern markers, subsystem-specific metadata, generated helper geometry, and contributor-facing tooling such as tests and debug infrastructure. If you only study the main element classes, you will miss real behavior that users depend on.

If you are new to the repository, read this as a map. You do not need to master every subsystem immediately, but you do need to know that they exist, what role they play, and where to look when a bug or feature request touches them.

## 1. Advanced document semantics beyond the base shape

The earlier architectural documents focus on the core embroidery pipeline: SVG content becomes element objects, element objects become stitch groups, and stitch groups become an output stitch plan. That is still the heart of the system, but contributor-level understanding requires one more step.

Ink/Stitch stores meaningful embroidery intent in several places:

- in shape geometry itself
- in Ink/Stitch parameters stored on SVG nodes
- in document-embedded command symbols and their connectors
- in sibling marker objects that act as guides, anchors, or patterns
- in subsystem-specific serialized data such as lettering or sew-stack configuration
- in generated intermediate SVG structures such as tartan groups

This means two visually similar shapes can embroider very differently because one has extra document semantics attached to it.

Three practical consequences follow from that:

1. Not all important behavior lives in the core element classes.
2. Some objects in the SVG exist mainly to influence other objects rather than to embroider themselves.
3. Tests and contributor docs are part of understanding the codebase, not just project administration.

When you debug, always ask two questions before reading stitch-generation code:

- “Is the behavior coming from the main object itself?”
- “Or is there an attached command, sibling guide, generated structure, or subsystem-specific setting involved?”

The rest of this document answers that question for the major advanced subsystems.

## 2. Commands

The command system lives in [lib/commands.py](../lib/commands.py). It is one of the best examples of Ink/Stitch’s document model being richer than simple per-object flags.

### Commands are embedded document semantics

Commands are not just booleans in a settings panel. They are represented directly in the SVG document using:

- symbol definitions in `<defs>`
- `<use>` instances of those symbols
- connector paths linking command symbols to target objects

For object-level commands, a command is literally a small command marker plus a connector pointing to the object it affects. The parsing logic in [lib/commands.py](../lib/commands.py) reconstructs that relationship by reading connector endpoints and symbol references.

That design matters because commands behave like part of the drawing:

- they can be moved in Inkscape
- they can be copied and cloned with objects
- they survive as document structure
- they can express positions, not just true/false state

The `Command` and `StandaloneCommand` classes in [lib/commands.py](../lib/commands.py) parse those two cases:

- connected commands attached to an object
- standalone commands that apply to a layer or the whole document

### Command categories

[lib/commands.py](../lib/commands.py) splits commands into three conceptual groups:

- **object commands** such as `starting_point`, `ending_point`, `target_point`, `stop`, `trim`, `ignore_object`, and `satin_cut_point`
- **layer commands** such as `ignore_layer`
- **global commands** such as `origin` and `stop_position`

That split is not cosmetic. It tells you where the command will be searched for and how broad its effect is.

### What commands actually do

#### Starting and ending positions

For fill-based elements, the effect is direct. In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `get_starting_point()` and `get_ending_point()` first check for `starting_point` and `ending_point` commands before falling back to neighboring stitch context.

That means a contributor cannot assume travel routing is always inferred from nearby objects. A command can override the natural route.

**Example:** two identical fill shapes can sew in different orders if one has a `starting_point` command attached. The geometry is unchanged, but the entry point into the fill graph changes, which can change travel, underpath behavior, and the visual place where stitching begins.

#### Target positions

`target_point` is another position-bearing command. In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), circular fill uses it as the target point for the pattern; otherwise it falls back to the shape centroid. This is a good example of a command altering embroidery behavior beyond base geometry.

#### Auto-route hints

`autoroute_start` and `autoroute_end` are used by routing-oriented extensions such as [lib/extensions/auto_run.py](../lib/extensions/auto_run.py) and [lib/extensions/auto_satin.py](../lib/extensions/auto_satin.py). Those extensions scan selected elements for command points and use them as route constraints.

So if a user says “auto-route starts in the wrong place,” that is not only an algorithm problem. It may be a document semantics problem: a command symbol is present, duplicated, or attached to the wrong object.

#### Stop, trim, and ignore behavior

These commands get folded into the stitch plan in different places.

- `ignore_object` is handled early during node traversal in [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py): the object is skipped before normal embroidery processing.
- `ignore_layer` is also handled during traversal, but by scanning the layer for standalone layer commands.
- `trim` and `stop` are applied after stitch groups are generated in [lib/elements/element.py](../lib/elements/element.py), where the final stitch group is marked with `trim_after` and `stop_after`.

This split is useful when debugging:

- if the object never appears in processing, think traversal and ignore commands
- if stitches are generated but machine actions are wrong afterward, think trim/stop propagation

#### Global origin and stop-position commands

Global commands affect export rather than local stitch generation. In [lib/output.py](../lib/output.py):

- `origin` overrides the default export origin, which would otherwise be the design bounding-box center
- `stop_position` causes the exporter to insert a jump to a specific point when a stop is encountered

This is a classic contributor trap. A user can report “the exported file is shifted” or “the machine jumps to the wrong place after a stop,” and the cause may not be in any fill or stroke algorithm at all. It may be a global command in the document.

#### Satin cut points

`satin_cut_point` is consumed by [lib/extensions/cut_satin.py](../lib/extensions/cut_satin.py). The extension requires those commands to decide where a satin column should be split. Again, the visible satin path alone is not enough.

### Commands clone with document structure

Commands are first-class enough that clone handling preserves them. In [lib/elements/clone.py](../lib/elements/clone.py), cloned objects recreate command attachments by cloning command groups and reconnecting them to the cloned node. That is one reason the command representation is structural instead of a plain attribute.

### What to remember about commands

When working on commands, think “document semantics carried by SVG structure,” not “UI toggle state.” That mental model makes the rest of the code much easier to follow.

## 3. Markers and patterns

Marker support lives primarily in [lib/marker.py](../lib/marker.py), with pattern application in [lib/patterns.py](../lib/patterns.py).

Commands are not the only case where auxiliary SVG objects matter. Markers let one object influence another object in the same group without being embroidered as normal geometry.

### What marker objects are

[lib/marker.py](../lib/marker.py) defines three important marker kinds:

- `anchor-line`
- `pattern`
- `guide-line`

The implementation works by scanning sibling elements in the same group for a `marker-start:url(#inkstitch-...-marker)` style. Marker definitions are ensured in the document `<defs>`, and then marker-bearing sibling elements are interpreted as geometry sources.

This is why [lib/elements/marker.py](../lib/elements/marker.py) exists: a marker object is a real object in the SVG tree, but as far as embroidery is concerned it is usually an auxiliary input, not a stitchable result. Its warning text explicitly says it will not be embroidered and instead applies to objects in the same group.

### Why markers matter architecturally

Markers prove that not all behavior is encoded solely in the main SVG shape. The main object may be a fill or stroke, but another sibling object supplies:

- a guide curve
- an anchor orientation
- a keep/remove pattern

That is important both for debugging and for cache invalidation. In [lib/elements/element.py](../lib/elements/element.py), marker-derived data contributes to cache keys, because changing a guide or pattern can change the stitch result even if the base object stays identical.

### Guide lines

Guide lines are used in multiple places.

- In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `_get_guide_lines()` looks for `guide-line` marker geometry. If guide lines exist, guided fill can be used instead of ordinary auto-fill.
- In [lib/elements/stroke.py](../lib/elements/stroke.py), `get_guide_line()` returns either a stroke-based guide or a satin guide object.
- In [lib/stitches/ripple_stitch.py](../lib/stitches/ripple_stitch.py), guide lines determine how helper outlines are placed and transformed.

**Example:** if a fill with guided-fill settings appears to ignore its own natural orientation and instead follows a sibling line, that is expected. The sibling guide-line geometry is the intended input.

### Anchor lines

Anchor lines are especially important for guided satin or ripple-like behavior. In [lib/elements/stroke.py](../lib/elements/stroke.py), `get_anchor_line()` returns anchor geometry from a sibling marker element. In [lib/stitches/ripple_stitch.py](../lib/stitches/ripple_stitch.py), that anchor line can define the position, rotation, and scale used to place repeated satin guide patterns.

Without understanding anchor lines, guided satin behavior can look mysterious: the same outline may transform differently depending on a hidden helper line next to it.

### Patterns

Pattern handling is implemented in [lib/patterns.py](../lib/patterns.py). After stitch groups are generated, [lib/elements/element.py](../lib/elements/element.py) calls `apply_patterns()`.

Pattern application does two different kinds of work:

- for fill patterns, it filters stitches inside marked pattern regions while preserving structural stitches such as row starts, row ends, travel stitches, and certain underlay/satin-related stitches
- for stroke patterns, it inserts extra `pattern_point` stitches at intersections between the stitch path and pattern geometry

So patterns do not merely decorate the drawing. They actively reshape the stitch sequence.

**Example:** a sibling element marked as a `pattern` can carve holes out of fill stitching or add tagged points into a stroke path. The main embroidered shape does not change, but the resulting stitch list does.

### A debugging rule for markers and patterns

If a result seems wrong only when objects are grouped together, inspect the group for marker-bearing siblings before assuming the core algorithm is wrong.

## 4. Lettering

The lettering subsystem lives in [lib/lettering/](../lib/lettering/). Architecturally, it is much larger than “draw some text.” It is effectively its own asset pipeline and document-construction system.

### Why lettering is a substantial subsystem

Lettering has to do all of the following:

- discover available fonts from bundled and user directories
- load font metadata and variant files
- convert per-glyph SVG artwork into normalized reusable glyph objects
- lay out text with directionality, kerning, line spacing, and alignment
- preserve clips, markers, and commands embedded inside glyph art
- optionally run auto-satin over the rendered result
- optionally add trims and color sorting

That is why lettering deserves its own subsystem instead of being treated as a minor feature.

### High-level structure

Important files in [lib/lettering/](../lib/lettering/) include:

- [lib/lettering/utils.py](../lib/lettering/utils.py): font discovery from bundled, user, and custom font paths
- [lib/lettering/font.py](../lib/lettering/font.py): the main `Font` class and text rendering pipeline
- [lib/lettering/font_variant.py](../lib/lettering/font_variant.py): variant loading and glyph lookup for left-to-right, right-to-left, and vertical cases
- [lib/lettering/glyph.py](../lib/lettering/glyph.py): normalization of individual glyph artwork, clips, baseline, and embedded commands
- [lib/lettering/categories.py](../lib/lettering/categories.py) and [lib/lettering/font_info.py](../lib/lettering/font_info.py): supporting metadata organization

### Font discovery and metadata

[lib/lettering/utils.py](../lib/lettering/utils.py) searches multiple directories for fonts, including bundled fonts and user/custom font locations. Each font directory is represented by `Font`, which reads `font.json`, optional licensing data, and its SVG variant files.

That means lettering is not hardcoded into Python classes. Much of it is data-driven by font assets shipped with or added to Ink/Stitch.

### Variants and glyphs

`FontVariant` in [lib/lettering/font_variant.py](../lib/lettering/font_variant.py) loads variant SVG files, updates older documents as needed, applies transforms, and extracts glyph layers.

`Glyph` in [lib/lettering/glyph.py](../lib/lettering/glyph.py) then normalizes each glyph by:

- flattening transforms into path geometry
- recording clips
- measuring bounding boxes and baseline
- moving glyph geometry to a common origin
- collecting embedded command relationships

That last point is easy to miss: glyph artwork can include command symbols and connectors. The glyph loader preserves enough information to recreate those connections when text is rendered.

### Rendering flow

The high-level rendering path is:

1. a lettering extension or GUI panel gathers user settings
2. it looks up a `Font`
3. `Font.render_text()` lays out lines, words, and glyphs
4. rendered glyph groups are inserted into the document
5. optional post-processing such as auto-satin, trims, marker symbol insertion, and color sorting runs afterward

Representative entry points include [lib/extensions/batch_lettering.py](../lib/extensions/batch_lettering.py) and [lib/extensions/lettering_along_path.py](../lib/extensions/lettering_along_path.py), both of which eventually call `Font.render_text()`.

### Lettering preserves advanced semantics

One of the most important architectural details in [lib/lettering/font.py](../lib/lettering/font.py) is that rendered text preserves more than visible path geometry.

It also:

- updates command IDs for copied glyph content
- reattaches clips
- ensures command and marker symbols exist in the destination document
- can add trim commands after letters, words, or lines
- can color-sort grouped lettering content

This is a strong signal that lettering is integrated with the rest of Ink/Stitch’s advanced document model, not isolated from it.

### Lettering is also a stitch-construction tool

If `Font.auto_satin` is enabled, [lib/lettering/font.py](../lib/lettering/font.py) runs the rendered geometry through auto-satin logic. In other words, lettering is not just importing decorative SVG. It is producing geometry that then re-enters the normal embroidery element pipeline.

## 5. Tartan

The tartan subsystem lives in [lib/tartan/](../lib/tartan/). It is a distinct subsystem because it has its own domain model, parsing rules, geometry expansion, routing logic, and generated SVG structures.

### What tartan logic is doing conceptually

Tartan is not just “fill this object with stripes.” It turns a tartan palette description into a set of warp and weft stripe geometries, clips them to an outline, routes them, and emits SVG elements that can then be embroidered.

This is a multi-stage conversion problem:

1. parse tartan palette code into stripe definitions
2. build geometric stripe shapes at the right scale, symmetry, and orientation
3. distinguish thin stripes that should act like strokes from wider stripes that should act like fill polygons
4. route those shapes in a sensible embroidery order
5. generate SVG elements grouped under a tartan container

### Main pieces of the subsystem

- [lib/tartan/palette.py](../lib/tartan/palette.py) parses tartan code formats and stores palette state
- [lib/tartan/utils.py](../lib/tartan/utils.py) converts stripe descriptions into polygons and linestrings
- [lib/tartan/svg.py](../lib/tartan/svg.py) builds a generated SVG group representing the tartan pattern
- [lib/tartan/fill_element.py](../lib/tartan/fill_element.py) prepares tartan fill elements for normal embroidery processing
- [lib/tartan/colors.py](../lib/tartan/colors.py) supports palette color interpretation

### Palette parsing is its own domain model

`Palette` in [lib/tartan/palette.py](../lib/tartan/palette.py) supports multiple input styles, including Ink/Stitch-specific color codes and tartan threadcount-style descriptions. That alone is already a real subsystem concern rather than a small option toggle.

The palette also tracks:

- warp and weft stripe sets
- symmetry vs repeating sets
- whether warp and weft are equal
- per-stripe render modes and widths

### Geometry generation and routing

In [lib/tartan/utils.py](../lib/tartan/utils.py), `stripes_to_shapes()` expands abstract stripe definitions into actual polygons or linestrings, grouped by color. Narrow stripes can be downgraded to stroke-like geometry. Neighboring polygons are merged, optionally intersected with the outline, and prepared for later routing.

In [lib/tartan/svg.py](../lib/tartan/svg.py), `TartanSvgGroup.generate()` turns an outline element into an `inkstitch-tartan-*` group, computes fill shapes, routing lines, travel paths, and final SVG children.

This code reuses core stitch-routing infrastructure such as fill-stitch graphs and travel-graph path finding, but it does so in service of a tartan-specific geometry expansion problem.

### Generated SVG groups matter

The tartan system generates wrapper groups and helper elements, then hides the original outline inside the tartan group. [lib/tartan/fill_element.py](../lib/tartan/fill_element.py) contains cleanup logic that knows how to pull a tartan fill element back out of an `inkstitch-tartan` group and normalize transforms.

That is exactly why tartan deserves to be treated as a subsystem: it introduces generated document structure, not just different parameter values.

### Why a newcomer can postpone tartan, but should still know it exists

You can work on many core bugs without understanding tartan deeply. But if you touch:

- generated fill geometry
- routing within patterned fills
- palette parsing
- tartan-specific UI or settings

then you are in a separate architectural area with its own assumptions.

## 6. Sew stack

The sew stack subsystem lives in [lib/sew_stack/](../lib/sew_stack/). It is an advanced composition mechanism that lets a single SVG object produce embroidery through an ordered stack of stitch layers.

### What sew stack is for

Normally, an object becomes one or more standard embroidery elements such as fill, stroke, or satin. Sew stack adds another way to think about embroidery: instead of deriving stitching only from the built-in element interpretation, a node can carry an explicit layered configuration.

That makes sew stack a layering-oriented subsystem rather than a single algorithm.

### Core structure

[lib/sew_stack/__init__.py](../lib/sew_stack/__init__.py) defines `SewStack`, which subclasses `EmbroideryElement`. It reads two important values from the SVG-backed parameters:

- `sew_stack`: JSON configuration describing the layer list
- `sew_stack_only`: whether only the sew-stack interpretation should be used

It then instantiates layer objects from the registry in [lib/sew_stack/stitch_layers/__init__.py](../lib/sew_stack/stitch_layers/__init__.py).

Each layer class derives from `StitchLayer` in [lib/sew_stack/stitch_layers/stitch_layer.py](../lib/sew_stack/stitch_layers/stitch_layer.py), which defines the interface for:

- defaults
- layer identity
- enable/disable state
- stitch generation

### Layer classes and editor metadata

The currently registered layer example is `RunningStitchLayer` in [lib/sew_stack/stitch_layers/running_stitch/running_stitch_layer.py](../lib/sew_stack/stitch_layers/running_stitch/running_stitch_layer.py). It demonstrates the architectural pattern clearly:

- layer behavior lives in the layer class
- editable properties are declared in an editor class
- shared functionality is split into mixins

The supporting UI metadata system is defined in [lib/sew_stack/stitch_layers/stitch_layer_editor.py](../lib/sew_stack/stitch_layers/stitch_layer_editor.py), and the mixin rationale is documented in [lib/sew_stack/stitch_layers/mixins/README.md](../lib/sew_stack/stitch_layers/mixins/README.md).

So sew stack is not only “multiple passes.” It is a framework for composable stitch-layer types.

### How sew stack integrates with normal element creation

Node-to-element conversion in [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py) always considers sew stack when creating embroidery elements. A `SewStack` object is constructed alongside normal fill/stroke/satin handling, and it is appended when the debug-controlled `sew_stack_enabled` flag is active.

That makes sew stack both architecturally real and, at least in the current codebase, somewhat feature-gated. Tests account for that by using [tests/utils.py](../tests/utils.py) to adjust expected element counts based on whether sew stack is enabled.

### Why sew stack matters conceptually

Sew stack changes the answer to a basic question:

> “What is the embroidery meaning of this SVG object?”

Without sew stack, the answer is mostly derived from style and parameters. With sew stack, the answer may instead be “a configurable ordered series of layer objects, each with its own stitching logic.”

That is a meaningful architectural shift, not a minor option.

## 7. Tests and what they tell you about the codebase

Tests live in [tests/](../tests/). For a newcomer, they are not just a safety net. They are executable documentation about what the project considers important and stable.

### What the tests cover

The current test set is selective rather than exhaustive. It focuses heavily on code that can be validated without a full live Inkscape UI session.

Representative files include:

- [tests/test_output.py](../tests/test_output.py)
- [tests/test_clone.py](../tests/test_clone.py)
- [tests/test_elements_utils.py](../tests/test_elements_utils.py)
- [tests/conftest.py](../tests/conftest.py)

### Test style

Many tests build tiny SVG trees in memory using `inkex.tester` helpers rather than loading large fixture files. That makes the tests relatively readable and good for learning.

The suite also includes some environment-specific helpers:

- [tests/conftest.py](../tests/conftest.py) disables cache usage for test stability
- [tests/utils.py](../tests/utils.py) abstracts over whether sew stack is enabled

### What representative tests teach you

#### Output tests

[tests/test_output.py](../tests/test_output.py) checks export-level behavior rather than geometry internals. Two especially useful facts it documents are:

- writing the same JEF output twice should be deterministic
- enabling trim changes the exported result

That tells a contributor that exporter behavior is part of the project’s stable contract, not an afterthought.

#### Clone tests

[tests/test_clone.py](../tests/test_clone.py) is especially rich. It covers transform inheritance, angle behavior, hidden children, style inheritance, and clone-specific handling. If you are unsure how cloned embroidery elements are *supposed* to behave, this file is one of the fastest ways to learn.

It also reinforces an important architectural lesson: document transformations and copy semantics are central to embroidery correctness.

#### Element traversal tests

[tests/test_elements_utils.py](../tests/test_elements_utils.py) documents how node iteration and element conversion should treat:

- hidden objects
- hidden groups
- root embroiderable nodes
- traversal order

That makes it useful whenever a user reports that something “should not stitch” or “is being skipped unexpectedly.”

### Example: using a test as a specification

Suppose you want to know whether a hidden rectangle inside a visible group should still produce an embroidery element. [tests/test_elements_utils.py](../tests/test_elements_utils.py) answers that directly: hidden objects and children of hidden groups should be ignored.

That is a good example of tests revealing intended behavior in part of the system. You do not need to infer policy from the traversal code alone.

### What is harder to test automatically

Some important behavior is still difficult to capture fully in automated tests:

- wxPython UI interactions
- packaged-app behavior across macOS, Windows, and Linux
- exact Inkscape extension runtime integration
- visually “good” embroidery outcomes for tricky geometry
- large or pathological geometric edge cases

So the tests are important, but they are not the entire validation story. For contributor work, you often need both automated tests and hands-on SVG reproduction files.

## 8. Debugging and contributor workflow

This is the practical section: how to move through the repository without getting lost.

### Where to start reading code

Start from the symptom category, not from whichever file looks most central.

#### If the bug is about object selection, skipped objects, or wrong element type

Start with:

- [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py)
- [lib/elements/element.py](../lib/elements/element.py)

These files decide what becomes an embroidery element, what is ignored, and how marker-only objects are treated.

#### If the bug is about fill order, route entry/exit, guided fills, or stitch geometry

Start with:

- [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py)
- [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py)
- [lib/marker.py](../lib/marker.py)
- [lib/commands.py](../lib/commands.py)

Many geometry issues turn out to involve guide lines or start/end commands rather than the fill graph itself.

#### If the bug is about ripple, satin guides, or helper-line behavior

Start with:

- [lib/elements/stroke.py](../lib/elements/stroke.py)
- [lib/stitches/ripple_stitch.py](../lib/stitches/ripple_stitch.py)
- [lib/marker.py](../lib/marker.py)

#### If the bug is about exports, machine jumps, stop positions, or design origin

Start with:

- [lib/output.py](../lib/output.py)
- [lib/commands.py](../lib/commands.py)

Do not start with stitch generation. Global commands may be the real cause.

#### If the bug is about lettering, tartan, or sew stack

Go directly to the subsystem:

- [lib/lettering/](../lib/lettering/)
- [lib/tartan/](../lib/tartan/)
- [lib/sew_stack/](../lib/sew_stack/)

Trying to debug these features only from the generic element pipeline usually wastes time.

#### If the bug is about the extension entry point or user-facing workflow

Look in:

- [inkstitch.py](../inkstitch.py)
- [lib/extensions/](../lib/extensions/)
- [lib/gui/](../lib/gui/)

### Example: choosing where to start on a bug report

Imagine a report saying: “My exported file pauses correctly, but the frame moves to a strange location after Stop.”

A newcomer might open fill or stroke generation first. That is usually the wrong place. The better path is:

1. inspect [lib/output.py](../lib/output.py) for stop handling
2. notice `jump_to_stop_point()` and the `stop_position` global command
3. inspect [lib/commands.py](../lib/commands.py) to understand how that command is represented in the SVG
4. only then ask whether the document contains more than one such command or an incorrectly placed one

That is the kind of triage skill that keeps you from getting lost.

### Runtime issues vs geometry issues vs UI issues

It helps to separate three common categories of debugging.

#### Runtime / extension-launch issues

These are problems such as:

- Ink/Stitch not starting correctly
- wrong extension class being launched
- environment differences between development and packaged builds
- exception handling and warning suppression

Start with [inkstitch.py](../inkstitch.py), which is the main launcher. It decides:

- whether the code is running as a frozen packaged app
- whether debugging/profiling is active
- how `inkex` is resolved in development mode
- how extension classes are loaded from [lib/extensions/](../lib/extensions/)

#### Geometry / stitch-algorithm issues

These are problems such as:

- bad fill routing
- wrong start/end behavior
- ripple misplacement
- pattern removal behaving unexpectedly

Start with the element class and the specific stitch algorithm, but do not forget attached commands and markers.

#### UI / workflow issues

These are problems such as:

- a dialog not reflecting settings
- a lettering or tartan control producing unexpected document state
- preview-time behavior differing from generated SVG state

Start with the relevant extension or GUI panel, then follow the data back into the subsystem.

### Debug infrastructure

Development-time debugging is supported by:

- [DEBUG_template.toml](../DEBUG_template.toml)
- [lib/debug/debug.py](../lib/debug/debug.py)
- [inkstitch.py](../inkstitch.py)

[DEBUG_template.toml](../DEBUG_template.toml) shows what can be enabled, including debugger selection, profiling, frozen-mode simulation, and a sew-stack feature flag.

[lib/debug/debug.py](../lib/debug/debug.py) provides lightweight logging plus SVG debug output. When enabled, it can write debug layers, line strings, graphs, points, and timing information. For geometry-heavy work, that SVG logging can be much more useful than plain text logs because it lets you inspect the intermediate shapes visually.

### Development mode vs packaged mode

The code behaves differently depending on whether it runs as a packaged, frozen application.

From [inkstitch.py](../inkstitch.py):

- packaged mode is detected through the `frozen` runtime state
- development mode can prefer the pip-installed `inkex` instead of the Inkscape-bundled one
- debugger and profiler startup are development-focused features
- packaged mode suppresses some warnings differently and uses more user-facing error presentation

This matters because “works in development but not in the packaged build” can be a real class of bug, not just bad luck.

### Contributor expectations and project conventions

Before changing code, read:

- [CODING_STYLE.md](../CODING_STYLE.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [requirements.txt](../requirements.txt)

[CODING_STYLE.md](../CODING_STYLE.md) explains an important project value: readability is a feature. The code is intentionally written to be understandable, sometimes at the cost of brevity.

[CONTRIBUTING.md](../CONTRIBUTING.md) covers contributor expectations, collaboration norms, and where different kinds of contribution are welcome.

[requirements.txt](../requirements.txt) tells you what technical ecosystem you are entering. Key libraries include:

- `inkex` for Inkscape extension integration
- `wxPython` for desktop UI
- `shapely` for geometry
- `networkx` for routing/graph problems
- `pystitch` for embroidery output
- `pytest`, `mypy`, and `flake8` for validation

That dependency list is part of understanding the codebase. It tells you what kinds of abstractions and failure modes to expect.

### A practical reading order for newcomers

If you are new and want to stay oriented:

1. start from the specific extension or user action
2. find the element or subsystem it creates or invokes
3. identify any commands, markers, or generated helper structures involved
4. read the representative tests for that area
5. only then dive into the lowest-level stitch algorithm

That order usually gives faster understanding than starting from the deepest geometry code.

## 9. Build/release awareness for contributors

You do not need to become a packaging expert to contribute effectively, but you do need enough build awareness to avoid common confusion.

### Generated files vs source files

A few important project artifacts are generated, not hand-maintained as primary sources.

The [Makefile](../Makefile) makes this explicit with targets such as:

- `inx`
- `locales`
- `version`
- `style`
- `type-check`
- `test`

If you change extension metadata or templates, you may need to regenerate `.inx` files rather than editing generated output directly.

### INX generation

[bin/generate-inx-files](../bin/generate-inx-files) generates the Inkscape extension descriptors from templates. It even supports alternate naming for side-by-side development installs.

That means `.inx` files are part of the runtime story, but not always the most useful place to make a source edit.

### Translation and version generation

The [Makefile](../Makefile) also drives locale and version generation. Contributors should know these steps exist because changed strings, metadata, or release packaging may depend on generated outputs even when the Python logic is unchanged.

### Packaging and frozen builds

[bin/build-python](../bin/build-python) handles PyInstaller-based packaging with OS-specific behavior for macOS, Linux, and Windows. This is where packaged-app concerns such as icons, bundled libraries, and distribution layout are handled.

You do not need to memorize the packaging details, but you should remember this distinction:

- **development mode** runs the repository as source code
- **packaged mode** runs a bundled app with different environment assumptions

If a bug only appears in installers or only on one packaged platform, this build path is relevant.

### Validation commands matter

The repository already tells you the main validation workflow:

- [Makefile](../Makefile) exposes `test` and `type-check`
- [bin/style-check](../bin/style-check) runs the project’s `flake8` configuration
- [requirements.txt](../requirements.txt) lists the dev tools needed to run those checks

This is another place where contributor docs are part of code understanding. They show what the project considers a safe change process.

### What build awareness should prevent

A little build knowledge helps you avoid several common mistakes:

- editing generated files instead of their templates or sources
- assuming packaged behavior matches source-tree behavior exactly
- forgetting that extension metadata and translations may need regeneration
- debugging an environment issue as if it were an algorithm issue

## 10. Final mental model

If you remember only one thing from this document, remember this:

Ink/Stitch is not just a pipeline from three core element classes to an embroidery file. It is a document-driven system with embedded semantics, auxiliary geometry, specialized subsystems, and contributor tooling that all shape the final result.

As a contributor, you should now be able to explain:

- what advanced subsystems exist beyond the core pipeline
- how commands, markers, and patterns affect embroidery behavior
- where [lib/lettering/](../lib/lettering/), [lib/tartan/](../lib/tartan/), and [lib/sew_stack/](../lib/sew_stack/) fit architecturally
- where to look in [tests/](../tests/) for intended behavior
- how [CODING_STYLE.md](../CODING_STYLE.md), [CONTRIBUTING.md](../CONTRIBUTING.md), and [requirements.txt](../requirements.txt) support responsible changes
- why build and runtime mode differences matter when debugging

That is the level of understanding that keeps a newcomer from getting lost while still leaving room to learn each subsystem in depth when needed.
