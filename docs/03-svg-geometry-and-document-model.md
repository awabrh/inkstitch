# Ink/Stitch SVG, Geometry, and Document Model

This document explains the parts of SVG and Inkscape that Ink/Stitch actually depends on.

It is written for readers who are new both to SVG and to the Ink/Stitch codebase. The goal is not to turn you into an SVG expert. The goal is to make the geometry-related parts of the repository feel understandable instead of magical.

The most important idea to keep in mind is this:

> Ink/Stitch does not read an SVG document as a flat list of visible shapes. It reads a tree of XML nodes, interprets style and transforms, resolves references such as clones and clip paths, and only then turns geometry into embroidery objects.

---

## The short version

If you only remember a few things after reading this document, remember these:

1. An SVG file is a tree of XML elements, not a bag of paths.
2. Ink/Stitch cares most about path-like geometry, fill, stroke, groups, transforms, units, and references.
3. A single SVG node can become multiple embroidery objects, typically one fill object and one stroke object.
4. Raw coordinates are often not the final geometry because parent transforms and the document `viewBox` also matter.
5. Ink/Stitch stores its own settings directly on SVG nodes using namespaced `inkstitch:*` attributes.
6. Nodes inside `<defs>`, `<clipPath>`, and `<mask>` may influence output, but they are usually not stitched directly.
7. Real-world SVG is messy, so a lot of code exists to repair, normalize, clip, simplify, and validate geometry before stitch generation.

---

## 1. SVG concepts Ink/Stitch actually relies on

### SVG is an XML scene graph

At the file format level, SVG is XML. That means a document is a tree of nested elements.

For example, this is conceptually how a tiny drawing looks:

```xml
<svg>
	<g inkscape:groupmode="layer" inkscape:label="Layer 1">
		<rect ... />
		<path ... />
	</g>
	<defs>
		<clipPath id="clip1">...</clipPath>
	</defs>
</svg>
```

That structure matters because Ink/Stitch needs to answer questions such as:

- Is this node inside a hidden or ignored layer?
- Does a parent group apply a transform?
- Is this shape only a definition inside `<defs>`?
- Is this a real shape, a clone, a clip path, a mask, or a command symbol?
- Does a parent group apply clipping?

This is why the codebase contains tree-oriented helpers rather than only geometry helpers.

The central constants for “what kind of node is this?” live in [lib/svg/tags.py](../lib/svg/tags.py). That file registers namespaces and defines tag constants such as `SVG_PATH_TAG`, `SVG_GROUP_TAG`, `SVG_DEFS_TAG`, `SVG_USE_TAG`, `SVG_CLIPPATH_TAG`, and `SVG_MASK_TAG`. It also defines important tag categories such as `EMBROIDERABLE_TAGS` and `NOT_EMBROIDERABLE_TAGS`.

The document-level helper layer is [lib/svg/svg.py](../lib/svg/svg.py). It provides utilities such as:

- `get_document()` to get the root `<svg>` node from any descendant
- `generate_unique_id()` to create safe unique IDs when Ink/Stitch inserts new nodes
- `find_elements()` for namespace-aware XPath searches

The convenience import surface in [lib/svg/__init__.py](../lib/svg/__init__.py) re-exports the most commonly used SVG helpers. This is why many modules import geometry and unit helpers from `lib.svg` directly rather than from individual submodules.

### What parts of SVG matter most to Ink/Stitch?

Ink/Stitch does not need every corner of the SVG specification equally. The features that matter most are:

- path-like geometry
- fill and stroke style
- groups and layers
- transforms
- units and document size
- `viewBox`
- namespaced custom attributes
- clones (`<use>`)
- definitions and references (`<defs>`, clip paths, masks)

Other SVG features may still appear in documents, but these are the ones that show up constantly in the code.

### Shape types and why paths dominate

Ink/Stitch can encounter several basic SVG shape types:

- `<path>`
- `<line>`
- `<polyline>`
- `<polygon>`
- `<rect>`
- `<circle>`
- `<ellipse>`

Those are the main embroiderable shape types listed in [lib/svg/tags.py](../lib/svg/tags.py).

Path-like geometry is central because embroidery algorithms ultimately need boundaries, centerlines, outlines, or point sequences. A rectangle or circle may start life as a specialized SVG element, but the geometry algorithms work most naturally on path-like representations.

That is why [lib/elements/element.py](../lib/elements/element.py) defines `EmbroideryElement.path` in a generic way:

- if Inkscape can provide `node.get_path()`, Ink/Stitch uses it
- otherwise it falls back to the raw `d` attribute
- the path is then converted to a cubic superpath representation

From there, `parse_path()` applies transforms, and `flatten()` approximates Bézier curves as point lists for downstream geometric processing.

### What about text and images?

Text and images exist in SVG, but they are not central to stitch generation.

In [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py), text and image nodes are recognized, but they become `TextObject` or `ImageObject` wrappers rather than normal embroiderable geometry. That is an important design clue:

- text and images are part of the document model
- they may need warnings, troubleshooting, or conversion guidance
- but they are not the primary path to stitch generation

For a newcomer, the right mental model is: **Ink/Stitch is mostly about path-like vector geometry, even when the original SVG contains other kinds of nodes.**

---

## 2. Visual style vs embroidery semantics

One of the biggest conceptual bridges in the codebase is the difference between **SVG appearance** and **embroidery meaning**.

### Fill and stroke in plain SVG terms

In SVG:

- **fill** means the interior of a closed shape is painted
- **stroke** means the outline of a shape is painted

For example:

```xml
<rect
	x="10" y="10" width="40" height="20"
	style="fill:#f4b400; stroke:#202020; stroke-width:2" />
```

On screen, that looks like one rectangle with a colored inside and a dark outline.

### Why Ink/Stitch interprets fill and stroke differently

Embroidery does not directly reproduce SVG paint operations.

A fill usually turns into some kind of area-filling stitch strategy. A stroke usually turns into a running stitch, satin column, zig-zag, or another line-oriented stitch strategy. Those are different embroidery objects with different settings, algorithms, and validations.

This separation is implemented very explicitly in [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py), in `node_to_elements()`:

- if a node has a visible fill color, Ink/Stitch can create a `FillStitch`
- if a node has a visible stroke color, Ink/Stitch can create a `Stroke`
- if stroke-specific conditions are met, the stroke may instead become a `SatinColumn`
- if `stroke_first` is set, their processing order can be reversed

This means one SVG node can legitimately produce multiple embroidery objects.

### Example: one SVG node, two embroidery objects

Consider this node:

```xml
<path
	d="M 0,0 L 30,0 L 30,20 L 0,20 Z"
	style="fill:#4caf50; stroke:#000000; stroke-width:3"
	inkstitch:angle="45"
	inkstitch:row_spacing_mm="0.4" />
```

Ink/Stitch may interpret it as:

1. a `FillStitch` for the filled area
2. a `Stroke` or `SatinColumn` for the outline

This is why the SVG-to-embroidery step is **semantic**, not purely geometric. The visible object looks singular to the user, but the embroidery interpretation may be plural.

### Where style is read in code

[lib/elements/element.py](../lib/elements/element.py) contains the shared style-reading logic:

- `get_style()` retrieves computed style values
- `fill_color` and `stroke_color` interpret fill and stroke colors
- `_get_color()` defends against malformed color data and missing gradient references
- `stroke_width` computes the effective stroke width after unit conversion and transform scaling

That last point is especially important: even something that seems simple, like stroke width, cannot be trusted until transforms and units are accounted for.

### SVG appearance and embroidery intent are related, but not identical

This confusion is common and worth stating plainly.

SVG appearance is the starting point, but Ink/Stitch is not a screenshot-to-stitches converter. It interprets SVG constructs as hints for embroidery structures. That interpretation is often intuitive, but it is not identical to “whatever the screen renderer draws.”

---

## 3. Groups, layers, and traversal implications

### Plain SVG groups

An SVG `<g>` element is just a grouping node. Groups are used to:

- organize content
- share transforms
- share style
- share clipping
- structure a document into meaningful subtrees

Ink/Stitch usually does not stitch the group node itself. Instead, it traverses into the group and processes the relevant descendants.

### How Inkscape layers relate to SVG groups

Inkscape layers are not a totally separate format feature. They are implemented on top of SVG groups.

In practice, an Inkscape layer is usually a `<g>` element with attributes such as:

- `inkscape:groupmode="layer"`
- `inkscape:label="Layer Name"`

This relationship is important because it explains why layer handling code looks like group handling code with extra conventions.

[lib/svg/tags.py](../lib/svg/tags.py) defines `INKSCAPE_GROUPMODE` and `INKSCAPE_LABEL`. [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py) checks `INKSCAPE_GROUPMODE == "layer"` to apply layer-specific ignore logic.

### How traversal works

The main traversal helper is `iterate_nodes()` in [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py).

It performs a **postorder traversal** of the selected subtree or of the whole document when nothing is selected. In plain terms, that means it visits children before the current node.

During traversal it skips or filters several kinds of nodes:

- XML comments
- objects marked with ignore commands
- layers marked with ignore-layer commands
- hidden objects
- `<defs>`, `<mask>`, and `<clipPath>` for direct stitching
- command connectors and command symbols that would otherwise pollute the embroiderable node list

This is one of the clearest places where the codebase shows that Ink/Stitch thinks in terms of document structure, not just raw geometry.

### Why layer semantics affect behavior

Because layers are groups with conventions, they can carry special meaning:

- visibility and display state
- ignore-layer commands
- user expectations about drawing order and organization

So when you see layer-aware logic in traversal, it is not arbitrary. It is a consequence of Inkscape storing layer meaning on top of ordinary SVG grouping.

---

## 4. Coordinate transforms and units

Transforms and units are where many geometry bugs are born.

### Why raw path data is often misleading

A path’s raw `d` attribute is frequently not the final geometry that matters.

If a node is inside one or more transformed groups, or if the node itself has a transform, or if the document uses a `viewBox`, the final geometry on the canvas can be very different from the raw numbers stored in `d`.

For example:

```xml
<g transform="translate(50,20) rotate(90)">
	<path d="M 0,0 L 10,0" />
</g>
```

The raw path says “draw a 10-unit horizontal line starting at the origin.”

But after the group transform is applied, the line is no longer horizontal and no longer at the origin. If Ink/Stitch stitched the raw `d` data without transforms, the result would be in the wrong place and with the wrong orientation.

This is why [lib/svg/path.py](../lib/svg/path.py) exists.

### How Ink/Stitch applies transforms

[lib/svg/path.py](../lib/svg/path.py) contains the key transform helpers:

- `compose_parent_transforms()` walks upward through parent groups and links
- `get_node_transform()` combines parent transforms, the node’s transform, and the document `viewBox` transform
- `apply_transforms()` applies the combined transform to a path
- `get_correction_transform()` computes the inverse transform when Ink/Stitch inserts new nodes using absolute coordinates

Then [lib/elements/element.py](../lib/elements/element.py) uses this in `parse_path()`:

- `EmbroideryElement.path` gets the raw path-like geometry
- `parse_path()` calls `apply_transforms()`
- `paths` then calls `flatten()` to turn curves into point lists

So the geometry used by embroidery algorithms is already transformed into document space.

### Practical transform types

In SVG, common transforms include:

- translation: move something
- rotation: turn something
- scaling: resize something
- skewing: slant something

Ink/Stitch has to care because these change:

- where a shape is stitched
- how wide a stroke appears
- the direction of fill angles
- how clip paths align with shapes

This even affects parameters that do not look geometric at first glance. For example, `stroke_width` in [lib/elements/element.py](../lib/elements/element.py) computes a transform-aware effective stroke width. Under uneven scaling or skew, the code intentionally uses an approximation based on average X/Y scale, because “stroke width after transforms” is not always a single exact number.

### Why unit conversion matters so much

Embroidery settings are often given in millimeters, but SVG geometry is commonly expressed in pixels.

[lib/svg/units.py](../lib/svg/units.py) defines one of the most frequently used constants in the codebase:

- `PIXELS_PER_MM = 96 / 25.4`

That constant exists because modern SVG and Inkscape use 96 pixels per inch. Converting millimeters to pixels is therefore essential for turning embroidery settings into geometry-compatible values.

[lib/svg/units.py](../lib/svg/units.py) also provides:

- `parse_length_with_units()`
- `convert_length()`
- `get_doc_size()`
- `get_viewbox()`
- `get_viewbox_transform()`

[lib/elements/element.py](../lib/elements/element.py) relies on `PIXELS_PER_MM` heavily in parameter accessors such as:

- `get_float_param()`
- `get_int_param()`
- `get_split_mm_param_as_px()`

Any parameter whose name ends in `_mm` is treated as a millimeter-based value and converted to pixels.

### Example: why a unit mistake is damaging

Suppose a user sets `row_spacing_mm="2"`.

Ink/Stitch should interpret that as:

$$2 \text{ mm} \times \frac{96 \text{ px}}{25.4 \text{ mm}} \approx 7.56 \text{ px}$$

If the code accidentally treated `2` as 2 px instead of 2 mm, the stitch rows would be almost 3.8 times closer together than intended. In embroidery software, that kind of error is not cosmetic. It changes density, thread usage, and machine behavior.

This is why `PIXELS_PER_MM` appears everywhere: it is a core bridge between the design world and the embroidery world.

---

## 5. ViewBox correction and document coordinates

### What a `viewBox` is

The SVG `viewBox` defines how the document’s internal coordinate system maps onto its displayed size.

A simplified mental model is:

- `width` and `height` describe how big the document is meant to be
- `viewBox` describes which coordinate rectangle is mapped into that size

So a document can say, in effect, “show the rectangle from internal coordinates `(0, 0)` to `(1000, 1000)` inside a page that is 100 mm wide.”

That means internal coordinate values and visible size are related, but not identical.

### Why Ink/Stitch must compensate for `viewBox`

If Ink/Stitch ignored the `viewBox`, then imported geometry, path transforms, and stitch-plan previews could all end up shifted or scaled incorrectly.

[lib/svg/units.py](../lib/svg/units.py) handles this in `get_viewbox_transform()`:

- it reads `width`, `height`, and `viewBox`
- it computes translation for the viewBox origin
- it computes scale between viewBox space and document size
- it respects `preserveAspectRatio`

[lib/svg/path.py](../lib/svg/path.py) then includes this transform inside `get_node_transform()`, which means normal geometry parsing already accounts for it.

### Where the code corrects coordinates when writing SVG back out

There is another side to the same problem: when Ink/Stitch creates new SVG nodes, it must sometimes **undo** document-space transforms so the new nodes appear in the right place.

This shows up clearly in [lib/svg/rendering.py](../lib/svg/rendering.py), which renders stitch plans back into the SVG document for preview.

That file:

- creates a preview layer named `__inkstitch_stitch_plan__`
- generates path elements for color blocks or realistic stitches
- applies a correction transform so the preview geometry lands in the correct visible coordinate system

This is a useful architectural clue: the same coordinate-system issues affect both **reading** geometry and **writing** helper graphics back into the document.

### Example: how `viewBox` changes interpretation

Imagine a document like this:

```xml
<svg width="100mm" height="100mm" viewBox="0 0 1000 1000">
	<circle cx="500" cy="500" r="100" />
</svg>
```

The circle radius is not “100 mm”. It is 100 units in viewBox space. The conversion to actual displayed size depends on the mapping between the 1000-unit viewBox and the 100 mm page.

That is why a newcomer should never assume SVG coordinates are directly physical units without checking units and `viewBox` handling.

---

## 6. Namespaces and custom Ink/Stitch attributes

### XML namespaces in plain terms

Namespaces are a way to say “this attribute name belongs to a particular vocabulary.”

Without namespaces, different tools could accidentally reuse the same attribute names and collide.

In XML, a namespaced attribute often appears like this:

```xml
inkstitch:row_spacing_mm="0.4"
```

That means the attribute belongs to the `inkstitch` namespace, not to plain SVG itself.

### Why the `inkstitch` namespace is important

Ink/Stitch stores most of its persistent per-object settings directly on SVG nodes. This is not incidental metadata. It is a core persistence mechanism.

[lib/svg/tags.py](../lib/svg/tags.py) registers the namespace URI and constructs the `INKSTITCH_ATTRIBS` mapping. That mapping gives code a stable way to refer to namespaced attributes such as:

- `inkstitch:angle`
- `inkstitch:row_spacing_mm`
- `inkstitch:satin_column`
- `inkstitch:stroke_method`
- many more

### Where custom attributes are read and written

[lib/elements/element.py](../lib/elements/element.py) is the main consumer of these attributes.

It provides:

- `get_param()`
- `get_boolean_param()`
- `get_float_param()`
- `get_int_param()`
- `set_param()`
- `remove_param()`

That means an embroidery object’s settings live on the same SVG node as its geometry.

This design has several benefits:

- the SVG file itself carries the embroidery settings
- settings stay attached to the object when the document is saved
- fill and stroke interpretations can read the same node’s persisted data

### Why this matters to the codebase

A lot of Ink/Stitch behavior makes more sense once you understand that namespaced attributes are first-class data storage. They are not decoration. They are how the embroidery-specific model is persisted inside a standard SVG document.

---

## 7. Clones, defs, clip paths, and masks

These are some of the most confusing SVG features for newcomers because they affect output without always being directly visible as ordinary shapes.

### Clones: `<use>`

An SVG `<use>` element says, roughly, “reuse that other object here.”

That means the geometry a user sees on the canvas may come from a referenced source node rather than from the `<use>` element itself.

Ink/Stitch handles this explicitly.

In [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py), if a node is a clone and `clone_to_element` is not requested, `node_to_elements()` returns a `Clone` object rather than immediately treating it as ordinary geometry.

[lib/elements/clone.py](../lib/elements/clone.py) then handles clone-specific work such as:

- resolving the referenced node
- duplicating the relevant tree
- applying clone transforms
- adjusting fill angles after transform changes
- copying command information

That last point is subtle but important: a clone is not just geometry reuse. It may need embroidery semantics adjusted too.

### Why clone handling needs special care

Suppose the original object has a fill angle of 45°. If a clone rotates the object, the angle that made sense on the source may no longer make sense on the clone. That is why [lib/elements/clone.py](../lib/elements/clone.py) computes angle transforms and updates `inkstitch:angle` on cloned embroiderable nodes.

### `<defs>`: definitions, not scene content

The `<defs>` element is where SVG stores reusable definitions such as:

- reusable shapes
- gradients
- clip paths
- masks
- symbols
- filters

These definitions influence what appears in the visible scene, but they are usually not meant to render directly by themselves.

That is exactly why `iterate_nodes()` in [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py) skips `<defs>` for direct stitching.

### Example: why a node in `<defs>` should not be stitched directly

```xml
<svg>
	<defs>
		<path id="star" d="..." />
	</defs>

	<use href="#star" x="10" y="10" />
	<use href="#star" x="50" y="10" />
</svg>
```

The path inside `<defs>` is a reusable template. The visible instances are the two `<use>` nodes.

If Ink/Stitch stitched the `<defs>` path directly, it would embroider an object that the user may never have intended as a visible design element. The actual embroiderable instances are the references placed in the visible scene.

### Clip paths

A clip path limits where geometry is visible. It does not usually mean “embroider the clip path itself.” It means “restrict this other object to the area defined by the clip path.”

[lib/svg/clip.py](../lib/svg/clip.py) handles clip-path geometry:

- `get_clip_path()` collects clip information from the node and its ancestor groups
- `_clip_paths()` resolves clip geometry and applies transforms
- the code handles powerclip-related path effects, including inverse clipping in some cases
- clip shapes are validated and combined into multipolygons

[lib/elements/element.py](../lib/elements/element.py) exposes the result as `clip_shape`.

Then element subclasses use it:

- [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py) intersects fill geometry with the clip shape
- [lib/elements/stroke.py](../lib/elements/stroke.py) clips line-based geometry
- [lib/elements/image.py](../lib/elements/image.py) clips image-derived bounds for warnings and troubleshooting

### Masks

Masks can also contain geometry, but their purpose is to affect visibility of other content, not to become ordinary embroiderable shapes themselves.

That is why [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py) skips `<mask>` during direct traversal, just like `<clipPath>` and `<defs>`.

### Summary mental model for these features

- `<use>` means “this visible thing references another thing”
- `<defs>` means “this subtree stores reusable resources”
- `<clipPath>` means “use this geometry to restrict visibility”
- `<mask>` means “use this content to modulate visibility”

All of them can influence the final result, but they do not behave like ordinary visible drawing nodes during traversal.

---

## 8. Why geometry validation and cleanup are necessary

Real SVG documents are rarely mathematically pristine.

Users edit shapes repeatedly. Inkscape effects rewrite paths. Boolean operations create tiny slivers. Clips produce awkward intersections. Clones inherit transforms. Gradients can reference missing IDs. Documents may come from other tools with inconsistent unit data.

Ink/Stitch therefore contains a lot of code whose job is not “generate the perfect stitch plan from perfect input,” but rather “survive and normalize the imperfect input that real users actually produce.”

### Invalid polygons and self-intersections

Filled geometry is especially sensitive to invalid polygons.

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py):

- `original_shape` builds a multipolygon from flattened path data
- `shape` checks validity
- invalid shapes are repaired with `make_valid()`
- coordinates are normalized with `set_precision()`
- clipping intersections are guarded against geometry-engine exceptions

The same file also defines `InvalidShapeError`, which makes the user-facing consequence explicit: some invalid shapes simply cannot be stitched reliably until repaired.

This is where self-intersections often show up in practice. A path that looks plausible on screen can still represent a polygon topology that is invalid for fill algorithms.

### Malformed paths or missing geometry

Some nodes do not actually contain usable geometry.

In [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py), an embroiderable tag with no usable path becomes an `EmptyDObject`.

[lib/elements/empty_d_object.py](../lib/elements/empty_d_object.py) then produces a warning explaining that the object has no geometry information.

For line-based shapes, [lib/elements/stroke.py](../lib/elements/stroke.py) also includes recovery logic for degenerate paths, such as synthesizing a tiny fallback segment when only one point is present.

### Malformed gradients or broken style references

Even style lookup can be invalid.

In [lib/elements/element.py](../lib/elements/element.py), `_get_color()` catches:

- unrecognized color values
- missing gradient references
- other cases where computed style cannot be resolved cleanly

So robustness is not only about polygon topology. It also includes defensive interpretation of style information.

### Odd transforms and approximations

Transforms can create geometry that is hard to interpret exactly, especially when skew and uneven scaling are involved.

[lib/elements/element.py](../lib/elements/element.py) documents this directly in `stroke_scale`: for complicated transforms, the effective stroke width is approximated from the transformed unit vectors on the X and Y axes.

That is a good example of the codebase preferring a practical answer over pretending the input is simpler than it really is.

### Geometry normalization deeper in stitch algorithms

The cleanup story does not end at the element layer.

[lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py) performs additional geometry work such as:

- `make_valid()`
- `set_precision()`
- buffering and unions
- smoothing outlines
- `graph_make_valid()` to repair routing graphs before pathfinding

That file is a good example of how geometry-heavy algorithm modules assume they may still receive awkward shapes and must continue defending against them.

### Why this robustness exists

Embroidery generation is less forgiving than screen rendering.

An SVG viewer can often display something that is topologically ambiguous or geometrically inconsistent. A stitch generator usually cannot. It needs coherent paths, valid regions, reasonable units, and stable intersections.

So when you see repair code, precision normalization, fallback logic, or warnings, do not treat them as incidental error handling. They are part of the core design of the system.

---

## 9. Practical examples that connect the concepts to code

### Example 1: a filled-and-stroked object

```xml
<ellipse
	cx="40" cy="20" rx="18" ry="10"
	style="fill:#ffcc00; stroke:#222222; stroke-width:2" />
```

What the user sees:

- one yellow ellipse with a dark outline

What Ink/Stitch may do:

1. convert the ellipse into path-like geometry via Inkscape’s path API
2. inspect style through `EmbroideryElement`
3. create a `FillStitch` because a visible fill exists
4. create a `Stroke` because a visible stroke exists

Relevant code:

- [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py)
- [lib/elements/element.py](../lib/elements/element.py)

This example is the clearest demonstration that SVG visual appearance and embroidery semantics are related, but not identical.

### Example 2: transforms make raw path data misleading

```xml
<g transform="translate(100,50) scale(2)">
	<path d="M 0,0 L 10,0" style="stroke:black; fill:none" />
</g>
```

Raw path data alone says “a 10-unit line from `(0,0)` to `(10,0)`.”

But the visible geometry is a translated, scaled line from `(100,50)` to `(120,50)` in document coordinates.

Relevant code:

- [lib/svg/path.py](../lib/svg/path.py) combines transforms
- [lib/elements/element.py](../lib/elements/element.py) calls `parse_path()`

This is why a path’s raw `d` attribute is often not enough.

### Example 3: why unit conversion matters

```xml
<path
	d="M 0,0 L 30,0 L 30,20 L 0,20 Z"
	inkstitch:row_spacing_mm="0.4" />
```

The `0.4` value is not in SVG pixels. It is in millimeters because the parameter name ends in `_mm`.

Relevant code:

- [lib/svg/units.py](../lib/svg/units.py)
- [lib/elements/element.py](../lib/elements/element.py)

If that value were misread as pixels, density would be drastically wrong.

### Example 4: a node inside `<defs>`

```xml
<defs>
	<path id="motif" d="..." />
</defs>
<use href="#motif" x="10" y="10" />
```

Relevant code:

- [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py)
- [lib/elements/clone.py](../lib/elements/clone.py)

The definition is a resource. The visible instance is the `<use>` node. Traversal therefore skips `<defs>` for direct stitching and handles the instance specially.

### Example 5: clip paths affect interpretation without being stitched directly

```xml
<clipPath id="clipA">
	<circle cx="20" cy="20" r="10" />
</clipPath>

<rect x="0" y="0" width="40" height="40" clip-path="url(#clipA)" />
```

The circle defines a clipping region. It does not necessarily mean “embroider a circle and a rectangle.” It means “embroider the rectangle, but only where it survives clipping.”

Relevant code:

- [lib/svg/clip.py](../lib/svg/clip.py)
- [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py)
- [lib/elements/stroke.py](../lib/elements/stroke.py)

---

## 10. How the required code references fit together

This section summarizes the specific files you will keep seeing when working in this part of the codebase.

### Core files

- [lib/svg/tags.py](../lib/svg/tags.py)  
	Central registry of SVG, Inkscape, XLink, and Ink/Stitch tag and attribute names. It defines which tags are considered embroiderable and builds the `INKSTITCH_ATTRIBS` mapping.

- [lib/svg/units.py](../lib/svg/units.py)  
	Handles unit parsing and conversion, document size, `viewBox`, and the critical `PIXELS_PER_MM` bridge between embroidery settings and SVG geometry.

- [lib/svg/__init__.py](../lib/svg/__init__.py)  
	Re-exports commonly used SVG helpers so the rest of the codebase can import them from a single place.

- [lib/svg/svg.py](../lib/svg/svg.py)  
	Document-level helpers for getting the root SVG node, finding elements, generating unique IDs, and doing small tree-management tasks.

- [lib/svg/rendering.py](../lib/svg/rendering.py)  
	Shows the “write geometry back into SVG” side of the coordinate problem by rendering stitch-plan previews with correction transforms.

- [lib/elements/utils/nodes.py](../lib/elements/utils/nodes.py)  
	The main traversal and node-classification layer. It decides which nodes are relevant and how one node turns into one or more embroidery elements.

- [lib/elements/element.py](../lib/elements/element.py)  
	The shared semantic base class. It is where path parsing, transform application, style access, parameter access, unit conversion, clipping access, validation hooks, and caching hooks come together.

### Closely related geometry-heavy files

- [lib/svg/path.py](../lib/svg/path.py)  
	Applies composed transforms and provides inverse correction transforms for newly inserted geometry.

- [lib/svg/clip.py](../lib/svg/clip.py)  
	Resolves clip-path geometry, including transformed and inherited clips.

- [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py)  
	Converts transformed paths into polygonal fill regions, repairs invalid geometry, and performs clipping.

- [lib/elements/stroke.py](../lib/elements/stroke.py)  
	Converts transformed paths into line-oriented geometry, clips strokes, and handles degenerate cases.

- [lib/elements/clone.py](../lib/elements/clone.py)  
	Resolves `<use>` references and adjusts embroidery semantics such as fill angle after transforms.

- [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py)  
	A downstream algorithm module that continues geometry cleanup and graph repair after the document-model layer has done its work.

---

## 11. A practical end-to-end mental model

When Ink/Stitch processes a document, a simplified mental model is:

1. Start with an SVG XML tree.
2. Traverse the tree, not a flat list of objects.
3. Skip non-scene or special-purpose subtrees such as `<defs>`, masks, and clip paths for direct stitching.
4. Interpret Inkscape layers as special groups.
5. For each relevant node, inspect style, custom `inkstitch:*` attributes, and references such as clones.
6. Convert basic shapes into path-like geometry.
7. Apply node, parent, and `viewBox` transforms.
8. Convert units so embroidery settings in millimeters can interact with geometry in pixels.
9. Resolve clips and other document-structure effects.
10. Split one SVG node into the right embroidery semantics: fill, stroke, satin, clone, warning object, and so on.
11. Validate and normalize geometry before passing it deeper into stitch-generation algorithms.

If you understand that flow, the geometry-related parts of the repository stop feeling like isolated utility functions and start looking like one coherent pipeline.

---

## 12. What a newcomer should now be able to explain

After reading this document, you should be able to explain:

- how SVG nodes are structured and traversed as a tree
- why fill and stroke are semantically important to Ink/Stitch
- why one node can become multiple embroidery objects
- why transforms and `viewBox` corrections matter before geometry is used
- why units and `PIXELS_PER_MM` appear throughout the codebase
- why namespaced `inkstitch:*` attributes are central persistence, not incidental metadata
- why clones, `<defs>`, clip paths, and masks need special handling
- why geometric cleanup, validation, and repair code are necessary in real documents

That is the conceptual foundation for understanding the rest of Ink/Stitch’s geometry and stitch-generation code.
