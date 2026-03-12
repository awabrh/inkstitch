# Ink/Stitch Embroidery Object Model

This document explains the semantic layer that sits between raw SVG content and the final stitch plan.

If you are new to the codebase, this is the main idea to keep in mind:

1. Ink/Stitch starts with SVG nodes.
2. It walks the document and decides which nodes matter for embroidery.
3. It wraps those nodes in semantic Python objects such as `FillStitch`, `Stroke`, and `SatinColumn`.
4. Those objects validate the input, interpret Ink/Stitch parameters and commands, and then generate one or more `StitchGroup` objects.
5. Lower-level stitch algorithms do the detailed geometric work.

That semantic middle layer lives primarily in [lib/elements/__init__.py](../lib/elements/__init__.py), [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py), and [lib/elements/element.py](../lib/elements/element.py), plus the concrete element classes such as [lib/elements/stroke.py](../lib/elements/stroke.py), [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), [lib/elements/satin_column.py](../lib/elements/satin_column.py), and [lib/elements/clone.py](../lib/elements/clone.py).

## Why Ink/Stitch has an object model between SVG and stitches

Ink/Stitch does **not** work directly on raw SVG nodes for everything, because raw SVG is not yet embroidery meaning.

An SVG node can tell you things like:

- what tag it is (`path`, `rect`, `use`, `text`, and so on)
- what its visual style is (`fill`, `stroke`, `stroke-width`)
- what transforms apply to it
- what custom Ink/Stitch attributes are attached to it

But that is still not enough to answer embroidery questions such as:

- Should this node become a fill, a stroke, a satin column, or more than one of those?
- Should stitch routing depend on the previous or next object?
- Does this geometry have a structural problem that should produce an error or warning?
- Which parameters belong to this kind of object?
- Should this result be cached, and if so, what makes one stitched result different from another?

The semantic object layer exists so that Ink/Stitch can attach embroidery-specific behavior to SVG-backed objects.

This layer provides several benefits:

- **Embroidery-specific interpretation**: a stroke-colored path can become a `Stroke` or a `SatinColumn`; a filled shape can become a `FillStitch`.
- **Separation of concerns**: traversal code decides *what nodes to consider*, while element classes decide *how to embroider them*.
- **Shared infrastructure**: parameter parsing, style lookup, command handling, path flattening, validation, and caching are implemented once in `EmbroideryElement`.
- **Specialized behavior**: each subclass can focus on the geometry and stitch logic that is unique to its embroidery meaning.
- **Practical robustness**: warnings, errors, and troubleshooting pointers are defined at the same layer where embroidery meaning is known.

In short, `EmbroideryElement` is **not** just a thin alias for an SVG node. It is a semantic wrapper that gives a node embroidery meaning.

## The main entry points in `lib/elements`

[lib/elements/__init__.py](../lib/elements/__init__.py) is a small but useful map of the subsystem. It re-exports:

- the base class `EmbroideryElement`
- the main concrete classes such as `FillStitch`, `Stroke`, `SatinColumn`, `Clone`, `TextObject`, and `ImageObject`
- the traversal and classification helpers `iterate_nodes()`, `node_to_elements()`, and `nodes_to_elements()` from [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py)

That file is not where the logic lives, but it shows the intended surface of the embroidery-object subsystem.

## How nodes are traversed and filtered

The traversal logic lives in [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py), mainly in `iterate_nodes()`.

### Selection-aware traversal

`iterate_nodes()` takes a root node and an optional `selection`.

- If a selection is present, Ink/Stitch only processes selected nodes and their descendants.
- If nothing is selected, Ink/Stitch processes the whole relevant document tree.

This is important because many extensions operate either on the current selection or on the whole design, and the traversal layer centralizes that behavior.

### Postorder traversal

The traversal is postorder: children are visited before the current node is added.

That matters because SVG groups are containers, not directly stitched elements. By walking children first, Ink/Stitch naturally collects actual embroiderable descendants in document order without trying to embroider the group itself.

### What gets skipped

`iterate_nodes()` deliberately filters out nodes that should not directly become embroidery objects:

- nodes whose tag is an XML comment
- nodes with the `ignore_object` command
- layers with the `ignore_layer` command
- hidden nodes (`display` effectively disabled)
- `defs`, `mask`, and `clipPath` containers
- command connectors and connector-type helper elements

This is one of the first places where Ink/Stitch stops thinking like a generic SVG renderer and starts thinking like an embroidery application.

For example, a clip path may contain valid geometry, but it exists to constrain other objects, not to become stitches by itself. The same is true for definitions, masks, and command connector helpers.

### Troubleshooting mode

`iterate_nodes()` has a `troubleshoot` flag. In normal stitching mode it collects embroiderable nodes (and clones) only. In troubleshoot mode it also includes text, images, and marker-backed objects so Ink/Stitch can report useful diagnostics for things that will not embroider directly.

That behavior is what allows wrappers like `TextObject` and `ImageObject` to participate in warnings even though they do not generate stitch groups.

## How nodes become embroidery elements

The classification logic lives in `node_to_elements()` in [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py).

This function is the bridge from “SVG node” to “semantic embroidery objects”.

### The most important rule

> **One SVG node may produce multiple `EmbroideryElement` instances.**

This is central to understanding Ink/Stitch.

An SVG node is allowed to have both a fill and a stroke. In embroidery terms, those are often two distinct operations with different stitch algorithms, different routing decisions, and different validation concerns. Ink/Stitch therefore models them as separate objects even though they came from the same source node.

### Classification rules at a high level

`node_to_elements()` handles several cases:

- hidden nodes produce no elements
- SVG clones (`<use>`) usually become a `Clone`
- embroiderable tags without a usable path become `EmptyDObject`
- marker-backed nodes become `MarkerObject`
- embroiderable path-like nodes may become one or more of:
	- `FillStitch`
	- `Stroke`
	- `SatinColumn`
- image nodes become `ImageObject`
- text nodes become `TextObject`

For normal path-like embroidery objects, `node_to_elements()` first creates a temporary base `EmbroideryElement` so it can inspect shared facts such as fill color, stroke color, stroke width, path count, and Ink/Stitch parameters. It then decides which specialized subclasses to instantiate.

### Fill, stroke, and satin classification

For an embroiderable node:

- if it has a non-transparent fill, Ink/Stitch adds a `FillStitch`
- if it has a stroke color, Ink/Stitch decides between `Stroke` and `SatinColumn`

The satin decision is explicit and conservative. A stroked node becomes a `SatinColumn` only when the `satin_column` parameter is enabled **and** the geometry looks suitable, specifically when either:

- the path has multiple subpaths, or
- the effective stroke width is greater than about `0.3 mm`

Otherwise the same stroked node becomes a `Stroke` instead.

This means that “stroke” in SVG does **not** map one-to-one to `Stroke` in Ink/Stitch. Sometimes the semantic meaning is satin.

### Ordering of multiple elements from one node

If a node produces both a fill and a stroke-derived element, the default order is:

1. `FillStitch`
2. `Stroke` or `SatinColumn`

If the Ink/Stitch parameter `stroke_first` is set, that order is reversed.

That small detail matters because embroidery order changes travel, layering, and the visual result.

### Example: one node becoming two elements

Suppose you have a single SVG path with:

- a blue fill
- a black stroke
- no `satin_column` parameter

Ink/Stitch will classify that one node into:

1. a `FillStitch` for the filled area
2. a `Stroke` for the outline

If the same node also has `satin_column=yes` and a sufficiently wide stroke, the second object becomes a `SatinColumn` instead of a `Stroke`.

So the correct mental model is not “one node equals one embroidery object”. The correct model is “one node may yield the set of embroidery objects needed to represent its embroidery meaning”.

## What `EmbroideryElement` provides

The base class in [lib/elements/element.py](../lib/elements/element.py) is where the shared machinery lives.

Subclasses are responsible for specialized embroidery meaning, but `EmbroideryElement` provides the infrastructure that makes those subclasses practical.

### 1. Parameter metadata and access

`EmbroideryElement` defines the `@param` decorator and the `Param` class.

This serves two roles:

- it documents which properties correspond to user-facing Ink/Stitch parameters
- it lets the class expose parameter metadata such as description, type, units, defaults, grouping, and UI options

At runtime, the base class offers helpers such as:

- `get_param()`
- `get_boolean_param()`
- `get_float_param()`
- `get_int_param()`
- `get_multiple_float_param()`
- `get_multiple_int_param()`
- `get_json_param()`

This is where parameter parsing is centralized instead of being duplicated in every subclass.

### 2. Unit conversion

Ink/Stitch commonly stores user-facing values in millimeters, but geometry is processed internally in SVG units. `EmbroideryElement` converts `*_mm` parameters into pixels using `PIXELS_PER_MM`.

That is one reason the semantic layer matters: it is the right place to normalize user settings into algorithm-ready values.

### 3. Style and color access

The base class also knows how to ask the SVG system for computed style information.

Important helpers include:

- `get_style()`
- `fill_color`
- `stroke_color`
- `stroke_scale`
- `stroke_width`

This is more than convenience. Embroidery behavior often depends on the *computed* style after inheritance, transforms, and SVG-specific details have been resolved.

### 4. Geometry preparation

`EmbroideryElement` exposes several geometry-oriented properties and helpers:

- `path`: the original SVG path as a cubic superpath
- `parse_path()`: the path after transforms are applied
- `paths`: flattened point lists suitable for many algorithms
- `shape`: an abstract property implemented by subclasses
- `clip_shape`: the clip path, if any

This layer converts SVG geometry into a form that embroidery code can actually use.

### 5. Command handling

Commands are integrated directly into the semantic layer through:

- `commands`
- `get_commands()`
- `get_command()`
- `has_command()`

That means subclasses do not need to reinvent command parsing. They can simply ask questions such as:

- Is there a `starting_point` command?
- Is there an `ending_point` command?
- Should this object `trim` or `stop` after stitching?
- Should this object be ignored entirely?

This is one reason `EmbroideryElement` is a semantic wrapper instead of a thin alias. Commands change embroidery meaning.

### 6. Lock stitches, trim, and stop behavior

The base class provides shared support for:

- minimum stitch length
- minimum jump stitch length
- lock-stitch configuration
- `trim_after`
- `stop_after`

Those settings belong here because they apply across multiple element types.

### 7. Validation hooks

Subclasses implement:

- `validation_errors()`
- `validation_warnings()`

The base class then uses `validate()` and `is_valid()` to enforce the error side of validation.

Warnings and errors are therefore part of the object model itself, not bolted on elsewhere.

### 8. Caching hooks

`EmbroideryElement` defines the cache pipeline:

- `_load_cached_stitch_groups()`
- `_save_cached_stitch_groups()`
- `get_cache_key()`
- `get_cache_key_data()`
- `uses_previous_stitch()`
- `uses_next_element()`

The subclass can contribute extra cache-key data or say whether surrounding context matters.

### 9. `embroider()` orchestration

The most important base-class method is `embroider()`.

This is the high-level orchestration point for turning one semantic element into stitch groups.

At a high level, `embroider()` does this:

1. determines the previous stitch from the prior stitch group, if any
2. attempts to load cached stitch groups
3. validates the element for fatal errors
4. calls the subclass’s `to_stitch_groups()` implementation
5. applies stitch patterns
6. applies trim/stop behavior to the last stitch group when appropriate
7. propagates minimum stitch settings to generated stitch groups
8. saves the result back into cache

So `to_stitch_groups()` is not the whole lifecycle. It is the subclass-specific generation step inside a broader orchestration pipeline.

## The three core element types: fill, stroke, satin

The three most important subclasses are [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), [lib/elements/stroke.py](../lib/elements/stroke.py), and [lib/elements/satin_column.py](../lib/elements/satin_column.py).

They all inherit the same infrastructure, but they represent very different embroidery ideas.

### Quick comparison

| Element type | What it means | Typical source SVG meaning | Main output style |
| --- | --- | --- | --- |
| `FillStitch` | Fill an area | non-transparent `fill` | rows, contours, gradients, meanders, cross stitch, and similar area fills |
| `Stroke` | Stitch along a path | `stroke` without satin interpretation | running stitch, ripple stitch, zigzag stitch, manual stitch |
| `SatinColumn` | Stitch side-to-side across a stroked path structure | `stroke` with satin meaning enabled | satin underlays plus a satin top layer |

### `FillStitch`: area-based embroidery

[lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py) is the semantic class for filled regions.

Its mental model is: **take a shape and cover its area with an embroidery strategy**.

Important responsibilities include:

- interpreting fill-specific parameters such as fill method, row spacing, angle, underlay, expansion, gradient settings, tartan settings, and routing controls
- turning the SVG geometry into polygonal `shape` data
- deciding start and end points, often using previous and next context
- choosing between fill algorithms such as `auto_fill`, `contour_fill`, `guided_fill`, `linear_gradient_fill`, `meander_fill`, `tartan_fill`, `cross_stitch`, and legacy fill modes
- generating one or more `StitchGroup` objects per shape or subshape

`FillStitch` is often context-sensitive. Its `uses_previous_stitch()` and `uses_next_element()` methods normally return `True` unless explicit commands override them. That is because fill routing often depends on where the needle is coming from and where it should head next.

`FillStitch.to_stitch_groups()` makes this very clear:

- it derives a starting point from a `starting_point` command or the previous stitch group
- it derives a preferred ending point from an `ending_point` command or the next element
- it sorts multiple shapes to get a nicer route
- it may generate underlay first and top fill afterward

This is a good example of why semantic objects exist. “Filled SVG shape” is only the input; the embroidery object is responsible for route planning, underlay, and choosing the actual fill algorithm.

### `Stroke`: path-following embroidery

[lib/elements/stroke.py](../lib/elements/stroke.py) is the semantic class for stitched outlines and line-like embroidery.

Its mental model is: **follow this path with a line-oriented stitch method**.

`Stroke` supports multiple stroke methods, including:

- running stitch / bean stitch
- ripple stitch
- zigzag stitch
- manual stitch

It interprets parameters such as:

- stitch length and tolerance
- repeats
- bean-stitch repeats
- zigzag spacing and angle
- maximum stitch length for manual paths
- guide lines and anchor lines for ripple-related behavior

Unlike `FillStitch`, `Stroke` usually does not depend on previous or next element context for routing, so it typically reuses cache entries more easily.

### `SatinColumn`: structurally interpreted stroke geometry

[lib/elements/satin_column.py](../lib/elements/satin_column.py) is the semantic class for satin columns.

Its mental model is: **interpret this stroked path as a satin structure, then zig-zag across that structure with optional underlays and stitch variants**.

This is more specialized than `Stroke`.

`SatinColumn` deals with ideas such as:

- rails and rungs
- center lines and compensated shapes
- underlay layers
- split stitches
- stitch direction control
- satin variants such as classic satin, `E` stitch, `S` stitch, and zigzag modes

It is also context-sensitive when configured to start or end at the nearest point. Its `uses_previous_stitch()` and `uses_next_element()` depend on whether explicit starting/ending commands exist and whether nearest-point routing is enabled.

This is a good example of subclasses being the place where embroidery meaning emerges. A raw SVG stroke does not contain a concept like “rail” or “rung”. `SatinColumn` introduces that meaning.

## Core differences between `Stroke`, `FillStitch`, and `SatinColumn`

Although all three are created from ordinary SVG styling and geometry, they think about the source node differently.

### `FillStitch`

- prioritizes area coverage
- works mainly from polygonal shape geometry
- often uses previous/next context to choose entry and exit
- may create underlay and top-fill phases
- commonly delegates to fill algorithms in [lib/stitches/](../lib/stitches/)

### `Stroke`

- prioritizes following a path centerline or path sequence
- works mainly from flattened path point lists
- offers line-oriented stitch styles such as running, zigzag, ripple, or manual
- usually has simpler context dependence than fills or satin columns

### `SatinColumn`

- prioritizes side-to-side satin construction across a stroke-defined structure
- requires geometry that can be interpreted as rails and optionally rungs, or as a simple satin path
- often combines underlay and top-layer logic into a more structured result
- has stronger structural validation than a plain `Stroke`

## Other important wrappers: clone, text, and image

### `Clone`

[lib/elements/clone.py](../lib/elements/clone.py) handles SVG `<use>` elements.

This is not just a trivial indirection. A clone can inherit transforms and styles, and Ink/Stitch may need to adjust embroidery-specific properties such as fill angle.

`Clone` therefore:

- resolves the referenced source into a temporary copied tree
- applies transforms and merged style in clone context
- adjusts fill angles when necessary
- converts the resolved content back through `iterate_nodes()` and `nodes_to_elements()`
- delegates actual embroidery to the resulting real elements

So a `Clone` is a semantic wrapper whose main job is to turn clone semantics into a stitchable temporary reality.

### `TextObject`

[lib/elements/text.py](../lib/elements/text.py) wraps text nodes.

It does **not** generate stitches. Instead, it provides a structured validation warning telling the user that text objects are not directly stitchable and should be converted or recreated in an embroidery-friendly way.

This is useful because the semantic layer is not only for “things that stitch”; it is also for “things that need meaningful embroidery diagnostics”.

### `ImageObject`

[lib/elements/image.py](../lib/elements/image.py) plays a similar role for images.

It can determine geometry for diagnostic purposes, but `to_stitch_groups()` returns no stitches. Its value is in producing user-facing warnings with a meaningful pointer location.

Again, the object model is about semantic embroidery meaning, and sometimes that meaning is: “this object is not directly embroiderable, and here is how to fix it”.

## Validation and warnings

Validation support is defined in [lib/elements/validation.py](../lib/elements/validation.py).

That file defines:

- `ValidationMessage`
- `ValidationError`
- `ValidationWarning`
- `ObjectTypeWarning`

Each validation message can include:

- a short name
- a description
- a position in the design
- a list of steps to solve the problem

This is not accidental plumbing. It is product behavior.

Ink/Stitch works with user-authored geometry, and user-authored geometry is often imperfect. The object model is where Ink/Stitch decides whether a problem is fatal, survivable, or merely informational.

### Errors vs warnings

- `validation_errors()` reports problems that should stop stitching for that element.
- `validation_warnings()` reports problems where Ink/Stitch can still attempt a result, but the user should probably fix the design.

`EmbroideryElement.validate()` only enforces fatal errors. It raises an `InkstitchException` via `fatal()` on the first error.

Warnings are still important. The troubleshoot extension in [lib/extensions/troubleshoot.py](../lib/extensions/troubleshoot.py) asks each element for warnings and errors and places visible pointers into the document. That is how this validation model becomes a user-facing robustness feature rather than hidden internal bookkeeping.

### Examples of validation in the main subclasses

`FillStitch` can report:

- `InvalidShapeError` for geometrically invalid fill shapes
- `UnconnectedWarning` or `BorderCrossWarning` for problematic outlines
- `SmallShapeWarning` for shapes too small to fill well
- `StrokeAndFillWarning` when a node has both fill and stroke color
- guide-line warnings for guided fill

`Stroke` can report:

- `TooNarrowSatinWarning` when the user requested satin behavior but the stroke is too narrow to classify as satin
- guide-line warnings for ripple-related features

`SatinColumn` can report:

- `NotStitchableError` when the satin structure cannot be interpreted properly
- warnings for closed rails, missing rungs, dangling rungs, too many intersections, narrow satin, and similar structure problems

### Example: invalid shape producing errors or warnings

Imagine a filled path whose border crosses itself.

- `FillStitch.validation_warnings()` may report `BorderCrossWarning` or `UnconnectedWarning` depending on what Shapely says about the original shape.
- If the final derived fill shape is invalid enough that it cannot be stitched, `FillStitch.validation_errors()` yields `InvalidShapeError`.
- During `embroider()`, `validate()` turns that error into a fatal user-facing exception so Ink/Stitch does not silently generate nonsense stitches.

That is exactly the kind of practical robustness this layer is designed to provide.

## Caching and context-sensitive generation

Stitch generation can be expensive, so [lib/elements/element.py](../lib/elements/element.py) caches stitch groups.

But Ink/Stitch cannot cache carelessly. Two stitched results are only interchangeable if all relevant inputs are the same.

### What goes into the cache key

`EmbroideryElement.get_cache_key()` includes a large amount of context, including:

- the class name
- parameter values
- parsed path geometry
- clip shape
- computed style
- gradient data
- command data
- pattern data
- guide and ripple marker data
- subclass-specific cache-key data
- tartan-related data
- previous-stitch context, if relevant
- next-element context, if relevant

This is a strong hint about how important the semantic layer is. The cache is not keyed only by SVG path data; it is keyed by embroidery meaning.

### Why previous/next context matters

Some elements change their route depending on surrounding objects.

For example:

- `FillStitch` can use the end of the previous stitch group as its starting point.
- `FillStitch` can use the next element to choose a better exit point.
- `SatinColumn` can start or end at a nearest point unless commands override that behavior.

Because of that, two identical-looking elements may still need different stitch results when their neighbors change.

The base class handles this through:

- `uses_previous_stitch()`
- `uses_next_element()`

If a subclass says it does not care about previous or next context, the cache can be reused more broadly. If it does care, the cache key includes that context.

### Example: how surrounding context changes generation

Consider a `FillStitch` object that has no explicit `starting_point` or `ending_point` commands.

- If it follows an object that ends near the fill’s left edge, `FillStitch` may start routing from that side.
- If the next object is near the top edge, `FillStitch` may choose an exit that heads upward.

Now move the neighboring objects.

The fill’s shape has not changed, but the preferred route through that shape may change. That is why context-sensitive elements cannot treat stitch generation as a pure function of the SVG node alone.

## Relationship to lower-level stitch algorithms

The `EmbroideryElement` subclasses are **not** the entire algorithmic story.

They are orchestrators and semantic interpreters. The lower-level stitch algorithms often live in [lib/stitches/](../lib/stitches/).

Examples:

- `Stroke` calls functions such as running stitch, bean stitch, zigzag stitch, and ripple stitch algorithms.
- `FillStitch` calls fill algorithms such as auto fill, contour fill, guided fill, cross stitch, meander fill, linear gradient fill, and tartan fill.
- `SatinColumn` contains substantial satin-specific logic, but it still relies on shared geometric helpers and lower-level processing routines.

This division of labor is important:

- the element class decides **what kind of embroidery object this is**
- the algorithm module decides **how to compute the detailed stitch pattern for that kind of object**

That separation makes the codebase easier to understand and extend.

## Worked examples

### Example 1: a filled-and-stroked SVG node becomes two embroidery elements

Suppose one SVG path has:

- `fill: blue`
- `stroke: black`
- `stroke-width: 1 mm`
- no satin setting

Traversal includes the node.

`node_to_elements()` then classifies it into:

1. `FillStitch(node)` because the fill is present and not fully transparent
2. `Stroke(node)` because the stroke is present and not interpreted as satin

These are two separate `EmbroideryElement` instances backed by the same SVG node.

That is legitimate and expected.

### Example 2: a stroke becomes a satin column instead of a regular stroke

Now take a stroked path with:

- `stroke: black`
- `stroke-width: 1.2 mm`
- `satin_column: true`

If the geometry is suitable, `node_to_elements()` chooses `SatinColumn(node)` instead of `Stroke(node)`.

If you reduce the stroke width below about `0.3 mm` on a simple path, the same node will no longer classify as satin. It will remain a `Stroke`, and `Stroke.validation_warnings()` can emit `TooNarrowSatinWarning` to explain why.

### Example 3: an invalid shape produces warnings or errors

Take a self-intersecting filled path.

- `FillStitch.validation_warnings()` may warn that the border crosses itself or that the fill is effectively unconnected.
- `FillStitch.validation_errors()` may emit `InvalidShapeError` if the derived fill geometry is not stitchable.

The semantic layer therefore protects the stitch generators from bad input while also producing useful user guidance.

### Example 4: previous and next context affect generation

Take a fill object between two neighboring shapes.

- With no explicit start/end commands, `FillStitch` may enter near the previous object’s end point and exit toward the next object.
- If you add a `starting_point` command, it stops using previous-stitch context.
- If you add an `ending_point` command, it stops using next-element context.

That is why the object model includes both command interpretation and context-aware cache keys.

## Common confusion points clarified

### `EmbroideryElement` is not just a wrapper for convenience

It is the point where SVG data becomes embroidery semantics.

### Subclasses are where embroidery meaning begins to emerge

`Stroke`, `FillStitch`, and `SatinColumn` are not just categories for organizing code. They introduce distinct routing rules, validation rules, cache behavior, and algorithm choices.

### Validation and caching are core design features

They are built into the base element lifecycle because embroidery generation depends on trustworthy geometry and often on expensive calculations.

### One node can map to multiple embroidery objects for good reasons

That is not an edge case. It is a natural consequence of SVG allowing combined visual styling and Ink/Stitch needing separate embroidery operations for those visual components.

## A compact mental model to keep in mind

When you read this part of the codebase, think in this pipeline:

1. `iterate_nodes()` decides which SVG nodes are relevant.
2. `node_to_elements()` turns each relevant node into one or more semantic embroidery objects.
3. Each `EmbroideryElement` subclass interprets parameters, styles, commands, and geometry.
4. `embroider()` validates, caches, and orchestrates generation.
5. `to_stitch_groups()` and lower-level stitch algorithms produce the actual stitch groups.

If you understand that pipeline, you understand why Ink/Stitch uses semantic embroidery objects and how this layer connects SVG input to final stitch generation.
