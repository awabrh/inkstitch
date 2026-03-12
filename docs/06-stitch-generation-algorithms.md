# Ink/Stitch Stitch Generation Algorithms

This document explains where Ink/Stitch's actual stitch-generation logic lives and how the main algorithm families work.

If you are new to embroidery software or new to this codebase, the most important idea is this:

> Turning SVG geometry into embroidery is **not** a simple matter of tracing paths.
>
> Ink/Stitch has to decide **where stitches go, in what order they are sewn, how they travel, how fabric distortion is compensated for, how underlay is built, and how to survive messy geometry**.

That is the real heart of the digitizing problem, and it is why the stitch-generation code is one of the most important and most complex parts of the project.

At a very high level, the flow is:

1. SVG nodes are classified into semantic embroidery objects such as `Stroke`, `FillStitch`, and `SatinColumn`.
2. Those objects read Ink/Stitch parameters, validate geometry, and decide which stitching strategy to use.
3. Lower-level stitch generators turn that semantic decision into ordered stitch points.
4. The result is one or more `StitchGroup` objects that later become a machine stitch plan.

For the semantic layer that sits before these algorithms, see [04-embroidery-object-model.md](04-embroidery-object-model.md).

## 1. Where stitch-generation logic lives

The core stitch-generation logic is split between two places:

- [lib/elements/](../lib/elements/) contains the **semantic embroidery object classes**.
- [lib/stitches/](../lib/stitches/) contains the **reusable geometric and routing algorithms**.

That division is important.

The element classes are where Ink/Stitch answers questions like:

- “Is this SVG thing a fill, a stroke, or a satin?”
- “Which parameters apply here?”
- “What shape should actually be stitched after expansion, clipping, or guide-line lookup?”
- “Where should this object start and end relative to neighboring objects?”

The stitch modules are where Ink/Stitch answers questions like:

- “How do I place stitch rows inside this polygon?”
- “How do I route between those rows without ugly jumps?”
- “How do I turn a path into even or randomized running stitches?”
- “How do I build a spiral, a meander, or a cross-stitch traversal?”

### The main code map

| Area | Main role |
| --- | --- |
| [lib/elements/stroke.py](../lib/elements/stroke.py) | Interprets stroked SVG objects as running stitch, ripple stitch, zigzag/simple satin, or manual stitch. |
| [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py) | Chooses among auto fill, contour fill, guided fill, circular fill, meander fill, cross stitch, tartan fill, linear gradient fill, or legacy fill. |
| [lib/elements/satin_column.py](../lib/elements/satin_column.py) | Implements much of the satin algorithm directly: rails, rungs, underlay, zigzag placement, split stitches, and routing. |
| [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py) | Core running-stitch primitives: even spacing, random spacing, bean stitch, zigzag transformation, and segment splitting helpers. |
| [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py) | Main graph-based routed fill algorithm for line fills inside polygons. |
| [lib/stitches/contour_fill.py](../lib/stitches/contour_fill.py) | Offset-ring and spiral-style fills. |
| [lib/stitches/guided_fill.py](../lib/stitches/guided_fill.py) | Fill rows derived from a user guide line, then routed with auto-fill-style travel logic. |
| [lib/stitches/circular_fill.py](../lib/stitches/circular_fill.py) | Circular and spiral fills around a target point. |
| [lib/stitches/meander_fill.py](../lib/stitches/meander_fill.py) | Tile-based meandering fill paths. |
| [lib/stitches/linear_gradient_fill.py](../lib/stitches/linear_gradient_fill.py) | Gradient-aware multi-color fill routing. |
| [lib/stitches/cross_stitch.py](../lib/stitches/cross_stitch.py) | Pixel-style cross-stitch generation and traversal. |
| [lib/stitches/tartan_fill.py](../lib/stitches/tartan_fill.py) | Stripe- and color-based tartan fill plus tartan run lines. |
| [lib/stitches/auto_satin.py](../lib/stitches/auto_satin.py) | Higher-level satin routing and restructuring across multiple satin objects. |

### A crucial clarification

It is wrong to think that the element classes are “the algorithms” by themselves.

- [lib/elements/stroke.py](../lib/elements/stroke.py) and [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py) are largely **dispatchers and parameter interpreters** that call into [lib/stitches/](../lib/stitches/).
- [lib/elements/satin_column.py](../lib/elements/satin_column.py) is the main exception: satin generation is important enough, and tightly coupled enough to satin-specific geometry, that much of the algorithm lives directly in the element class.

So the real answer to “where do the stitch algorithms live?” is:

- **mostly in [lib/stitches/](../lib/stitches/)**
- **with satin generation heavily implemented in [lib/elements/satin_column.py](../lib/elements/satin_column.py)**

## 2. Relationship between element wrappers and algorithm modules

The best way to understand the architecture is to follow one object from classification to stitches.

### Stroke flow

In [lib/elements/stroke.py](../lib/elements/stroke.py), `Stroke.to_stitch_groups()` chooses among several stroke methods:

- running stitch
- ripple stitch
- zigzag/simple satin
- manual stitch

It reads parameters such as `running_stitch_length`, `running_stitch_tolerance`, `repeats`, `bean_stitch_repeats`, `zigzag_spacing`, `pull_compensation`, and `zigzag_angle`, then hands the actual geometric work to lower-level helpers such as:

- `running_stitch()` from [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py)
- `bean_stitch()` from [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py)
- `zigzag_stitch()` from [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py)
- `ripple_stitch()` from [lib/stitches/ripple_stitch.py](../lib/stitches/ripple_stitch.py)

In other words, `Stroke` decides **which family** of path stitching to use; the stitch module decides **how that family is drawn**.

### Fill flow

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `FillStitch.to_stitch_groups()` does several higher-level jobs before any fill algorithm runs:

- computes start and end points from commands and neighboring objects
- sorts multiple polygons for better routing
- generates fill underlay when requested
- applies shape expansion and related preprocessing
- dispatches to the chosen fill family

The dispatch targets include:

- `auto_fill()` in [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py)
- contour helpers in [lib/stitches/contour_fill.py](../lib/stitches/contour_fill.py)
- `guided_fill()` in [lib/stitches/guided_fill.py](../lib/stitches/guided_fill.py)
- `circular_fill()` in [lib/stitches/circular_fill.py](../lib/stitches/circular_fill.py)
- `meander_fill()` in [lib/stitches/meander_fill.py](../lib/stitches/meander_fill.py)
- `cross_stitch()` in [lib/stitches/cross_stitch.py](../lib/stitches/cross_stitch.py)
- `tartan_fill()` in [lib/stitches/tartan_fill.py](../lib/stitches/tartan_fill.py)
- `linear_gradient_fill()` in [lib/stitches/linear_gradient_fill.py](../lib/stitches/linear_gradient_fill.py)
- `legacy_fill()` in [lib/stitches/fill.py](../lib/stitches/fill.py)

Again, the element class decides **which algorithmic strategy applies** and what inputs it should receive. The stitch module does the detailed geometric work.

### Satin flow

Satin is more self-contained.

In [lib/elements/satin_column.py](../lib/elements/satin_column.py), `SatinColumn.to_stitch_groups()`:

- determines start and end behavior
- generates one or more underlay layers
- generates the visible top layer using one of several satin methods
- splits or reorders parts of the satin when an explicit ending point is requested
- connects layers with running stitches when needed

Much of the satin-specific logic is in methods such as:

- `do_center_walk()`
- `do_contour_underlay()`
- `do_zigzag_underlay()`
- `do_satin()`
- `do_e_stitch()`
- `do_s_stitch()`
- `do_zigzag()`

Those methods still reuse lower-level helpers from [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py) for evenly spaced running stitches and split-segment placement, but the satin geometry itself is driven in the element class.

### `auto_satin.py` is related, but it solves a different problem

[lib/stitches/auto_satin.py](../lib/stitches/auto_satin.py) is not the function that draws the zigzags for a single satin column.

Instead, it is a **higher-level routing and restructuring tool** for multiple satin elements. It introduces abstractions such as `SatinSegment`, `RunningStitch`, and `JumpStitch`, then uses graph routing to:

- reorder satin objects
- split satin columns into smaller sequential pieces
- insert running stitches between satins
- decide where jumps or trims are needed

That makes it conceptually closer to “satin object routing and editing” than to “single-column stitch placement.”

## 3. Running-stitch family

The running-stitch family is the simplest place to start because many other algorithms build on it.

The core implementation lives in [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py).

### Ordinary running stitch

The central entry point is `running_stitch()`, which chooses between:

- `even_running_stitch()` — tries to keep stitch spacing even along the path
- `random_running_stitch()` — randomizes phase and length within constraints

Both functions are trying to answer the same question:

> Given a continuous path, where should the needle penetrate so the machine approximates that path with acceptable stitch length and acceptable geometric error?

The `tolerance` parameter matters because stitches are allowed to approximate the curve rather than land on every original point. Smaller tolerance follows corners more strictly but usually increases stitch count.

The randomized mode is especially important for tightly packed curved fills, because perfectly regular spacing can create visible moiré-like patterns.

### Bean stitch

`bean_stitch()` in [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py) is conceptually simple but physically important.

Instead of placing a stitch once and moving on, it backtracks over each stitch according to a repeat pattern. That makes the line visually heavier without needing a satin column.

Algorithmically, bean stitch is not a different geometry generator. It is a **post-processing traversal pattern** applied to an existing stitch list.

### Zigzag-style path stitching

`zigzag_stitch()` in [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py) takes an already-sampled path and offsets successive points left and right of the path direction.

This is how [lib/elements/stroke.py](../lib/elements/stroke.py) implements its “simple satin” / zigzag stroke mode:

1. create a single running-stitch pass along the path
2. resample it to an appropriate spacing
3. offset alternate points perpendicular to the path
4. widen the offsets using pull compensation
5. optionally rotate the zigzag direction with `zigzag_angle`

So even a zigzag-looking stroke is not “just draw a wide stroke.” It is a derived stitch structure built on top of path sampling.

### Repeated and patterned traversal

In [lib/elements/stroke.py](../lib/elements/stroke.py), the `repeats` parameter makes the machine go back and forth along the same path. This is used for several stroke methods.

That is important because in embroidery, “same path, multiple passes” is a meaningful strategy:

- to increase visual weight
- to reinforce a line
- to build decorative rhythm
- to avoid switching to a different object type

### Ripple stitch

Ripple stitch is implemented in [lib/stitches/ripple_stitch.py](../lib/stitches/ripple_stitch.py). It is still part of the stroke-oriented family, but conceptually it behaves more like a light pattern fill along or around a path.

Its own module description says the key ideas clearly:

- open shapes are stitched back and forth
- closed shapes are treated more like spiral-filled regions
- the algorithm can use targets or guide lines
- it tolerates self-crossing and is intended for lighter, decorative stitching rather than dense structural fill

It also reuses routing ideas from the fill subsystem when clipping produces multiple routed segments.

### Example: a stroke-oriented algorithm path

Suppose a user draws a curving vine outline and chooses a normal running stitch with bean repeats.

The flow is:

1. [lib/elements/stroke.py](../lib/elements/stroke.py) decides the object is a `Stroke` using the `running_stitch` method.
2. `Stroke.to_stitch_groups()` calls `running_stitch()` from [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py).
3. That function samples the curve into stitch points using the requested length and tolerance.
4. `Stroke.do_bean_repeats()` then applies `bean_stitch()` so each stitch is backtracked.
5. If `repeats > 1`, the path may be traversed back and forth.

This example is useful because it shows the layering of responsibilities:

- the element class chooses behavior and parameters
- the stitch module places points
- post-processing changes thread buildup and traversal

## 4. Fill families

Ink/Stitch has many fill families because different shapes and design goals need different geometric strategies. These are **not** cosmetic variants of one underlying fill.

They encode different answers to questions such as:

- Should rows be parallel, concentric, guided, circular, tiled, or pixel-like?
- Should routing prioritize hidden travel, spiral continuity, or color grouping?
- Is the main goal coverage, texture, directional control, or color-pattern structure?

### Overview table

| Fill family | Main idea | Main module |
| --- | --- | --- |
| Auto Fill | Parallel rows plus explicit intra-shape routing | [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py) |
| Contour Fill | Successive inward offsets / spirals that follow the outline | [lib/stitches/contour_fill.py](../lib/stitches/contour_fill.py) |
| Guided Fill | Rows derived from a user guide line | [lib/stitches/guided_fill.py](../lib/stitches/guided_fill.py) |
| Circular Fill | Concentric or spiral structure around a target point | [lib/stitches/circular_fill.py](../lib/stitches/circular_fill.py) |
| Meander Fill | Tile-based wandering line through the shape | [lib/stitches/meander_fill.py](../lib/stitches/meander_fill.py) |
| Cross Stitch | Pixel-grid crosses with controlled diagonal layering | [lib/stitches/cross_stitch.py](../lib/stitches/cross_stitch.py) |
| Tartan Fill | Warp/weft stripe logic plus color-grouped fill and run lines | [lib/stitches/tartan_fill.py](../lib/stitches/tartan_fill.py) |
| Linear Gradient Fill | Parallel fill rows split into color sections by gradient logic | [lib/stitches/linear_gradient_fill.py](../lib/stitches/linear_gradient_fill.py) |
| Legacy Fill | Older row-oriented fill without modern auto-routing sophistication | [lib/stitches/fill.py](../lib/stitches/fill.py) |

### Auto fill: the main routed fill algorithm

[lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py) is one of the most important modules in the whole codebase.

Conceptually, it does **two jobs**:

1. generate fill rows by intersecting the shape with a grating of lines
2. decide how to travel between those rows so the shape is stitched efficiently and cleanly

That second step is what makes it more than a simple “parallel row fill.”

`auto_fill()`:

- optionally adjusts the shape for pull compensation
- creates row segments with `intersect_region_with_grating()`
- builds a graph of fill segments and boundary connections with `build_fill_stitch_graph()`
- builds a separate travel graph with `build_travel_graph()`
- finds a stitch path through those graphs
- converts the path to final stitches with `path_to_stitches()`

The graph-building step is especially important. The code comments explicitly discuss building an Eulerian-friendly graph so a valid traversal exists.

So for auto fill, routing is not an afterthought. It is built into the algorithm itself.

#### Why this matters

If a polygon has holes, narrow channels, or awkward start/end constraints, “just place rows” is not enough. The algorithm must also decide:

- where to enter and leave each row set
- how to move between disconnected row segments
- whether travel should stay inside the shape as underpath stitches

### Contour fill: outline-following fill

[lib/stitches/contour_fill.py](../lib/stitches/contour_fill.py) solves a different problem.

Instead of filling with a family of parallel lines, it repeatedly offsets the polygon inward with `offset_polygon()` and builds a tree of nested rings.

That makes it suitable for shapes where the visual effect should follow the border rather than cut across it.

Contour fill supports several strategies:

- `inner_to_outer()` — recursively travels nested offset rings
- `single_spiral()` — a single spiral from outside toward the center
- `double_spiral()` — a Fermat-style outward-and-back spiral

It also supports:

- join-style choices that affect how corners are offset
- optional smoothing of the final path
- an `avoid_self_crossing` mode in the recursive path search

This is a good example of a fill family that is algorithmically distinct, not just visually different.

### Guided fill: let the user define the dominant direction

[lib/stitches/guided_fill.py](../lib/stitches/guided_fill.py) starts from a guide line rather than a plain angle.

Its job is to convert that guide into many fill rows that better reflect the intended flow of the design.

There are two main conceptual stages:

1. build stitchable lines by copying or offsetting the guide structure across the shape
2. reuse auto-fill-style graph routing to travel through the resulting segments

This is why guided fill feels different from normal auto fill: the user is influencing the **structure of the rows**, not just their angle.

If no usable guide line exists, [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py) falls back to normal auto fill.

### Circular fill: fill around a target

[lib/stitches/circular_fill.py](../lib/stitches/circular_fill.py) is built around a target point.

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), that target comes either from a `target_point` command or from the shape centroid.

The algorithm then:

- generates concentric circles around the target
- builds a spiral-like path through them
- intersects that path with the shape
- routes the resulting segments with the same graph/travel ideas used elsewhere

So circular fill is not just “auto fill with a different angle.” It changes the geometric basis of the row system from straight lines to rings around a center.

### Meander fill: tile-based wandering geometry

[lib/stitches/meander_fill.py](../lib/stitches/meander_fill.py) uses pattern tiles from the tile system, not simple rows.

Its flow is roughly:

1. choose a tile pattern
2. convert the tiled pattern to a graph clipped to the shape
3. ensure disconnected components are linked if needed
4. find start and end nodes near the requested entry/exit points
5. iteratively grow a path through the graph
6. smooth and optionally zigzag or bean-stitch the result

This family solves a texture problem rather than a pure coverage problem. It is intended for decorative wandering fills that do not look like strict row fills.

### Cross stitch: preserve cross structure, not just density

[lib/stitches/cross_stitch.py](../lib/stitches/cross_stitch.py) is fundamentally different from the line-fill families.

The shape is converted into a pixel-like cross-stitch geometry, and the algorithm then tries to build Eulerian cycles through those crosses while preserving how the diagonals layer.

That is important because a cross stitch is not just two arbitrary line segments. The order of the diagonals is part of the appearance.

The module supports multiple families such as:

- simple cross
- upright cross
- half cross
- double cross
- flipped variants

This is a good reminder that some stitch families are defined by **symbolic structure** as much as by raw geometry.

### Tartan fill: stripe logic plus routing

[lib/stitches/tartan_fill.py](../lib/stitches/tartan_fill.py) is one of the most domain-specific fill modules.

It starts from tartan settings and stripe definitions, then builds:

- warp and weft stripe shapes
- optional herringbone variants
- color-grouped fill lines
- separate color-grouped run lines

Each color group is then routed into stitch groups using fill-style graph logic.

This is why tartan fill is not just “a striped auto fill.” It has its own structure:

- stripe geometry
- color grouping
- ordering of fill versus run elements
- tartan-specific parameters such as `rows_per_thread` and `herringbone_width`

### Linear gradient fill: color-aware line grouping

[lib/stitches/linear_gradient_fill.py](../lib/stitches/linear_gradient_fill.py) takes a normal fill-like line system and adds gradient-aware color partitioning.

It:

- reads the SVG linear gradient and its stops
- generates lines perpendicular to the gradient direction
- divides those lines into color sections
- routes each color section separately
- removes travel where color changes make that travel visually unnecessary

This means the algorithm is doing both geometry and embroidery color sequencing.

### Legacy fill

The legacy fill implementation lives in [lib/stitches/fill.py](../lib/stitches/fill.py) as `legacy_fill()`.

It still matters because older behavior remains part of the codebase, and because it provides a useful contrast with auto fill.

`legacy_fill()` focuses on:

- intersecting the region with a grating
- grouping runs of row segments
- converting each section to staggered stitches
- supporting options such as `flip`, `reverse`, and `skip_last`

Compared with [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py), it is much closer to “generate rows and stitch them” and much less about explicit graph-based travel routing.

### Example: two fill methods solving different problems

Consider two shapes:

1. a rectangular badge with a hole and an awkward requested exit point
2. a round medallion where you want the stitches to visually follow the outline

For the badge, **auto fill** is usually the better mental model because the hard problem is routing between row segments and holes without messy travel.

For the medallion, **contour fill** may be the better mental model because the hard problem is not routing parallel rows but generating outline-following paths that feel natural for a round shape.

These are not cosmetic alternatives. They solve different geometric problems.

## 5. Satin generation

Satin generation is conceptually different from both path stitching and area fill.

A satin column is a structured band whose visible stitches typically run from one side of the column to the other, producing a dense zigzag-like surface.

### Rails and rungs

The main satin implementation is [lib/elements/satin_column.py](../lib/elements/satin_column.py).

The classic Ink/Stitch satin model is based on:

- **rails**: the two boundaries of the column
- **rungs**: internal guide connections that tell the algorithm how stitches should flow across the column

That is why the file contains validation warnings such as:

- rails forming a closed path
- missing rungs
- dangling rungs
- too many rung intersections
- unequal point counts when no rungs exist

Those warnings are not just input policing. They reflect genuine algorithmic needs. Satin geometry is not defined only by width; it is defined by how one side maps to the other.

### How the top layer is generated

`SatinColumn.to_stitch_groups()` builds the satin in layers.

For the visible top layer it chooses among several satin methods:

- `do_satin()` — standard satin zigzag across the rails
- `do_e_stitch()` — an “E” pattern
- `do_s_stitch()` — an “S” pattern
- `do_zigzag()` — a lighter zigzag-style variant

The standard satin method works by plotting corresponding point pairs on the two rails, then stitching across those pairs in sequence.

That sounds simple, but several nontrivial concerns are layered into it:

- pull compensation widens the stitch span
- short stitches may be inset in dense areas
- long spans may be split into intermediate penetrations
- split placement may be default, simple, or staggered
- randomization can change split position and spacing
- start/end handling may require splitting the stitched path into ordered groups

### Split methods and randomization

Satin columns frequently need split stitches because a wide satin can otherwise create stitches that are too long.

In [lib/elements/satin_column.py](../lib/elements/satin_column.py), `get_split_points()` dispatches among:

- a default split strategy
- a simple strategy
- a staggered strategy

The default strategy can also use random phase and random jitter. This is part of distortion-aware and appearance-aware digitizing:

- perfectly repeated penetration positions can create harsh patterns
- randomized or staggered splits can distribute density more attractively

### Underlay for satin columns

Satin generation includes several underlay types directly in [lib/elements/satin_column.py](../lib/elements/satin_column.py):

- `do_center_walk()`
- `do_contour_underlay()`
- `do_zigzag_underlay()`

These are structural layers placed before the visible satin.

They exist because the visible satin is dense, directional, and physically aggressive on fabric. Without support underneath, it can sink, shift, spread unevenly, or pull the fabric into a narrower result than the design intended.

### Simple satin from strokes versus full satin columns

It is also important not to confuse two related things:

- **zigzag/simple satin stroke mode** in [lib/elements/stroke.py](../lib/elements/stroke.py)
- **full satin column generation** in [lib/elements/satin_column.py](../lib/elements/satin_column.py)

The stroke version works by taking a path and offsetting points into a zigzag structure.

The satin-column version works from explicit side geometry and guidance structure. It is more powerful and more robust for real satin work because it can respond to width changes, bends, underlay, and rail alignment.

### `auto_satin.py` as satin routing across objects

[lib/stitches/auto_satin.py](../lib/stitches/auto_satin.py) belongs in the satin story because it handles multi-object satin routing.

Its abstractions show its purpose:

- `SatinSegment` represents part of a satin column
- `RunningStitch` represents an inserted travel path
- `JumpStitch` represents an unavoidable jump between objects

It can split, reorder, and reconnect satin objects to produce better sewing order. That is a routing problem across satin objects, not just inside one satin.

## 6. Underlay and compensation

Underlay and compensation are central to the embroidery algorithms. They are not optional trivia.

### Why underlay exists

Embroidery happens on fabric, not on an ideal mathematical plane.

Top stitches can:

- sink into soft fabric
- pull edges inward
- spread differently depending on direction
- lose crispness if stitched directly on unstable material

Underlay is the preparatory structure that helps control those effects.

Algorithmically, underlay means “generate an additional stitch system before the visible layer, often with different angle, density, inset, or path type.”

### Fill underlay

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `do_underlay()` uses [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py) again, but with underlay-specific parameters such as:

- `fill_underlay_angle`
- `fill_underlay_row_spacing`
- `fill_underlay_max_stitch_length`
- `fill_underlay_inset`
- `underlay_underpath`

That is a good example of underlay as an algorithmic concept rather than a separate decorative feature. The same routing machinery is reused, but with a structurally different parameter set.

### Satin underlay

In [lib/elements/satin_column.py](../lib/elements/satin_column.py), the underlay types have distinct structural jobs:

- **center-walk underlay**: running stitches down and back near the centerline to anchor the column
- **contour underlay**: stitches along the inside edges to define boundaries and support the satin edges
- **zigzag underlay**: a lower-density zigzag support structure under the final satin

These may be combined, and the code explicitly orders and connects them before sewing the top layer.

### Compensation and distortion-aware logic

Compensation exists because fabric and thread distort the result.

Important examples include:

- **fill pull compensation** in [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py), where the shape itself can be adjusted before rows are generated
- **stroke pull compensation** in [lib/elements/stroke.py](../lib/elements/stroke.py), where zigzag width is widened
- **satin pull compensation** in [lib/elements/satin_column.py](../lib/elements/satin_column.py), where points are pushed outward from the column center
- **short-stitch inset** in satin generation, which reduces density problems in tight areas
- **random width decrease/increase** and random zigzag spacing for satin variation
- **random stitch length** in running/fill families to reduce visible artifacts

These are not after-the-fact visual tweaks. They change the actual geometry that gets stitched.

### Example: why underlay matters physically and algorithmically

Imagine a wide satin column on a stretchy knit fabric.

Without underlay:

- the top satin may sink into the fabric
- the edges may lose definition
- the column may narrow noticeably due to pull

With center-walk plus contour underlay:

- the fabric is pre-stabilized along the column path
- the edges get structural support before the dense top layer arrives
- the satin algorithm has a better foundation for the visible zigzag layer

So underlay changes both the physical result and the algorithmic stitching sequence.

## 7. Routing and geometry challenges

One of the biggest beginner misconceptions is to think that stitch generation is mostly about placing visible rows.

In practice, **routing is part of the fill/stroke/satin problem**.

### Routing inside a fill object

For routed fill families such as auto fill, guided fill, circular fill, linear gradient fill, tartan fill, and even clipped ripple paths, the algorithm has to decide:

- how to connect segments
- how to choose a path through them
- when to travel along boundaries
- whether travel should be hidden as underpath inside the shape
- how to respect requested starting and ending points

That is why the graph-building functions in [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py) matter so much.

### Routing across multiple subshapes

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), multiple component polygons are sorted based on the chosen start point. This is already a routing decision before the low-level fill even starts.

Linear gradient fill and tartan fill also perform color-aware sorting of their stitch groups after generation.

### Routing in satin

Satin routing happens both:

- **inside one satin column**, where underlays and top layers must connect cleanly
- **across multiple satin columns**, where [lib/stitches/auto_satin.py](../lib/stitches/auto_satin.py) may insert running stitches or jumps and even split columns for a better overall path

### Robustness and messy geometry

These algorithms must cope with real user artwork, which means they must handle:

- tiny shapes that cannot meaningfully support a fill
- narrow regions where rows or satins become unstable
- invalid polygons and self-crossing borders
- disconnected fill components
- multiple or missing guide lines
- guide lines outside the target shape
- clipped or partially empty geometry
- rails and rungs that do not intersect correctly

This is why the element classes define many warnings and fallbacks.

Some examples visible in the code:

- [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py) warns about invalid shapes, disjoint guide lines, tiny shapes, and impossible expansion/inset operations.
- [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py) falls back to outline-style stitching if no useful gratings or graphs can be formed.
- [lib/stitches/guided_fill.py](../lib/stitches/guided_fill.py) falls back to normal auto fill when the guide-driven rows do not work.
- [lib/elements/satin_column.py](../lib/elements/satin_column.py) warns when rails/rungs are not structurally valid for satin generation.

### Example: why naïve geometry-to-stitch conversion is insufficient

Take a donut-shaped fill with a hole, a requested starting point on one side, and a requested ending point on the other.

A naïve approach might:

1. generate parallel rows
2. stitch them in geometric order
3. jump whenever the rows break around the hole

That would ignore the real embroidery questions:

- how to travel between row fragments without visible mess
- how to hide travel inside the object where possible
- how to respect the requested exit point
- how to avoid ugly density buildup at row ends

Ink/Stitch's routed fill algorithms exist precisely because the naïve conversion is not good enough.

## 8. Parameter-driven behavior

Ink/Stitch's stitch algorithms are strongly parameter-driven. The parameter list is not just decoration around a fixed core algorithm.

Changing parameters changes the actual geometry, density, routing, and travel behavior.

### Common parameter families and what they really do

#### Density and spacing parameters

Examples:

- `running_stitch_length`
- `max_stitch_length`
- `row_spacing`
- `end_row_spacing`
- `zigzag_spacing`
- `staggers`
- `repeats`

These control far more than “tight versus loose.” They affect:

- how many rows or points exist
- whether a fill graph has enough usable segments
- whether long spans need split stitches
- how regular or irregular the visual rhythm looks

#### Direction and structure parameters

Examples:

- `angle`
- `guided_fill_strategy`
- `contour_strategy`
- `join_style`
- `satin_method`
- `split_method`
- `tartan_angle`

These choose the geometric model, not just a preference setting.

#### Routing-related parameters

Examples:

- `underpath`
- `skip_last`
- `flip`
- `reverse`
- `stop_at_ending_point`
- start/end point commands

These alter how the object is traversed, often without changing the basic visible row family.

#### Distortion and support parameters

Examples:

- `pull_compensation_mm`
- `pull_compensation_percent`
- `expand_mm`
- underlay spacing, angle, inset, and length parameters
- satin short-stitch parameters
- randomization parameters

These exist because the algorithms are fabric-aware, not purely geometric.

### Why contributors need to understand parameters before editing algorithms

When you change an algorithm, you are usually also changing the meaning of one or more parameters.

For example:

- changing how `row_spacing` is interpreted can alter density, routing graph structure, and underlay behavior
- changing satin split logic changes the practical meaning of `max_stitch_length` and `split_method`
- changing guide-line interpretation changes the meaning of guided-fill parameters and user expectations

So before editing a stitch generator, you usually need to inspect both:

- the relevant algorithm module in [lib/stitches/](../lib/stitches/)
- the parameter definitions and call sites in the corresponding element class in [lib/elements/](../lib/elements/)

## 9. Practical advice for contributors changing algorithms

If you need to change stitching behavior, start from the semantic object that owns that behavior.

### If you want to change stroke behavior

Inspect:

- [lib/elements/stroke.py](../lib/elements/stroke.py)
- [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py)
- [lib/stitches/ripple_stitch.py](../lib/stitches/ripple_stitch.py)

Look here for:

- running-stitch placement
- bean-stitch behavior
- zigzag/simple satin strokes
- repeated traversal
- ripple pattern generation

### If you want to change routed fill behavior

Inspect:

- [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py)
- [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py)
- [lib/stitches/fill.py](../lib/stitches/fill.py) for legacy comparisons

Look here for:

- grating intersection
- graph construction
- travel routing
- underpath behavior
- pull compensation for fills

### If you want to change a specific fill family

Inspect the matching module directly:

- contour behavior: [lib/stitches/contour_fill.py](../lib/stitches/contour_fill.py)
- guided rows: [lib/stitches/guided_fill.py](../lib/stitches/guided_fill.py)
- circular behavior: [lib/stitches/circular_fill.py](../lib/stitches/circular_fill.py)
- meander texture: [lib/stitches/meander_fill.py](../lib/stitches/meander_fill.py)
- cross stitch: [lib/stitches/cross_stitch.py](../lib/stitches/cross_stitch.py)
- tartan: [lib/stitches/tartan_fill.py](../lib/stitches/tartan_fill.py)
- gradient fills: [lib/stitches/linear_gradient_fill.py](../lib/stitches/linear_gradient_fill.py)

### If you want to change satin generation

Inspect:

- [lib/elements/satin_column.py](../lib/elements/satin_column.py)
- [lib/stitches/auto_satin.py](../lib/stitches/auto_satin.py) if the problem is ordering across multiple satins
- [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py) for shared split/running helpers

### Practical habits that help

1. **Trace from `to_stitch_groups()` first.** That shows how parameters, start/end logic, and algorithm dispatch fit together.
2. **Check fallbacks and warnings.** Many bugs only appear on ugly geometry, tiny shapes, or invalid guide structures.
3. **Think about travel, not just visible rows.** A change that looks correct in a static picture may create awful routing.
4. **Treat underlay and compensation as first-class behavior.** They are part of the algorithm, not optional extras.
5. **Test narrow, tiny, holed, and disconnected shapes.** Easy shapes rarely reveal the real failures.
6. **Remember color grouping.** Gradient and tartan fills especially are multi-group algorithms, not single-pass fills.

## Final mental model

If you finish this document with only one strong mental model, let it be this:

- [lib/elements/stroke.py](../lib/elements/stroke.py), [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), and [lib/elements/satin_column.py](../lib/elements/satin_column.py) decide **what kind of embroidery object** they are dealing with and **which parameters and geometry** apply.
- [lib/stitches/running_stitch.py](../lib/stitches/running_stitch.py), [lib/stitches/auto_fill.py](../lib/stitches/auto_fill.py), [lib/stitches/contour_fill.py](../lib/stitches/contour_fill.py), [lib/stitches/guided_fill.py](../lib/stitches/guided_fill.py), [lib/stitches/circular_fill.py](../lib/stitches/circular_fill.py), [lib/stitches/meander_fill.py](../lib/stitches/meander_fill.py), [lib/stitches/linear_gradient_fill.py](../lib/stitches/linear_gradient_fill.py), [lib/stitches/cross_stitch.py](../lib/stitches/cross_stitch.py), [lib/stitches/tartan_fill.py](../lib/stitches/tartan_fill.py), and [lib/stitches/auto_satin.py](../lib/stitches/auto_satin.py) contain the reusable algorithm families and routing machinery.
- Fill, stroke, and satin generation differ because they solve different geometric and physical problems.
- Underlay, compensation, and routing exist because thread and fabric are physical constraints, not cosmetic afterthoughts.

That is why stitch generation in Ink/Stitch is complex: it is where geometry, routing, and textile reality all meet.

