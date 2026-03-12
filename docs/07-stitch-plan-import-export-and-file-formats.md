# Ink/Stitch Stitch Plan, Import/Export, and File Formats

This document explains the part of Ink/Stitch that sits between object-level stitch generation and final embroidery file writing.

If you are new to the codebase, the key idea is this:

- element code decides how a particular object wants to sew
- stitch-plan code decides how the entire design should sew as one machine program

That separation is why Ink/Stitch has several related but different abstractions:

- [`Stitch`](../lib/stitch_plan/stitch.py): one position plus machine-oriented flags
- [`StitchGroup`](../lib/stitch_plan/stitch_group.py): one object-level chunk of sewing intent
- [`ColorBlock`](../lib/stitch_plan/color_block.py): one same-thread machine run
- [`StitchPlan`](../lib/stitch_plan/stitch_plan.py): the complete ordered design

The same planning layer is also used during import. Ink/Stitch reads machine stitches into a `StitchPlan`, then renders that plan back into SVG-based manual-stitch paths and command markers.

---

## 1. Why the stitch-plan layer exists

Embroidery elements such as fills, satins, strokes, lettering, or manual stitches do not directly write PES, DST, EXP, or other file bytes. Their job is to describe stitching for their own local geometry.

The bridge from elements to planning is in [`lib/extensions/base.py`](../lib/extensions/base.py). `InkstitchExtension.elements_to_stitch_groups()` walks the embroiderable elements and calls each element’s `embroider(...)` method. The result is an ordered list of `StitchGroup` objects.

So the high-level pipeline is:

1. SVG nodes become embroidery elements.
2. Each element emits one or more `StitchGroup`s.
3. [`stitch_groups_to_stitch_plan()`](../lib/stitch_plan/stitch_plan.py) turns those groups into a `StitchPlan`.
4. Export code maps that plan into `pystitch` commands and machine files.
5. Import code reads machine stitches into a `StitchPlan` and then renders the plan back into SVG.

This layer exists because many important decisions can only be made when Ink/Stitch can see the whole design order, not just one object at a time. For example:

- whether two same-color groups should be sewn continuously or separated by a jump
- when to add tie-ins and tie-offs
- when to insert trims, stops, and color changes
- how to group same-color output into machine color sections
- how to compute design-level statistics such as stitch count, thread estimate, and dimensions

Without a stitch-plan layer, every embroidery element would need to know too much about neighboring elements and file-format behavior.

### The separation in one sentence

`StitchGroup` answers: **“How should this object sew?”**

`StitchPlan` answers: **“How should the machine sew the whole design?”**

---

## 2. `Stitch` and stitch-level flags

The lowest-level representation is [`lib/stitch_plan/stitch.py`](../lib/stitch_plan/stitch.py).

`Stitch` inherits from `Point`, so it has:

- `x`
- `y`

But in Ink/Stitch, a stitch is more than a coordinate. It can also carry machine and planning state:

- `jump`: move without sewing
- `stop`: stop for operator intervention
- `trim`: trim the thread
- `color_change`: change to the next thread
- `min_stitch_length`: optional per-stitch minimum length override for duplicate filtering
- `tags`: arbitrary labels used by other code to track meaning or origin
- `color`: optional color payload

The `is_terminator` property is true for stitches that act as command boundaries:

- trim
- stop
- color change

### Why a stitch carries more than coordinates

Embroidery output is not only “needle goes here”. It is a mixed stream of geometry and commands. A single unified object makes later processing much easier:

- exporting to file formats
- counting trims and stops
- rendering the stitch plan into SVG
- filtering duplicate points without deleting real commands

### Tags

Tags let other parts of the code attach semantic information to a stitch without changing the core class. The stitch itself treats tags as opaque strings.

One concrete example appears in [`lib/stitch_plan/color_block.py`](../lib/stitch_plan/color_block.py): duplicate filtering preserves stitches tagged as `lock_stitch`, because tie stitches are intentionally short and must not be removed by length-based cleanup.

### Coordinate units

Inside the stitch-plan layer, coordinates are usually handled in SVG pixel space. Import and export explicitly convert between pixels and machine units using `PIXELS_PER_MM`.

---

## 3. `StitchGroup` as intermediate representation

[`lib/stitch_plan/stitch_group.py`](../lib/stitch_plan/stitch_group.py) defines `StitchGroup`, the intermediate representation between element logic and full-design planning.

A `StitchGroup` stores:

- `stitches`
- `color`
- `trim_after`
- `stop_after`
- `lock_stitches`
- `force_lock_stitches`
- `min_jump_stitch_length`

The class docstring explains the key design rule: jump stitches are allowed between `StitchGroup`s, but not inside one.

### What that means in practice

A `StitchGroup` says:

> “These stitches belong together as one continuous object-level sewing segment, with this color and these boundary instructions.”

It is not the final export representation.

That is important because one object may produce:

- one `StitchGroup` if it can sew continuously
- multiple `StitchGroup`s if the planner may need to insert travel/jump behavior between internal sections

### Attached color

The group carries its intended thread color so the planner can decide whether it continues the current machine color run or starts a new one.

### `trim_after` and `stop_after`

These are requests attached to the group boundary. They do not directly write machine commands on their own. The stitch-plan assembly logic interprets them in context and inserts the actual trim or stop stitches at the right moment.

### Lock stitches

`lock_stitches` holds start and end tie strategies. `get_lock_stitches("start")` and `get_lock_stitches("end")` generate actual securing stitches based on the group geometry.

They are stored here rather than always inserted immediately because the planner still needs to decide whether a tie-in or tie-off is necessary in the whole-design context.

### Minimum jump behavior

`min_jump_stitch_length` lets an object override the global collapse length. In effect it says, “when deciding whether the next travel is long enough to require a jump boundary, use this threshold for transitions after me.”

### Forced lock behavior

`force_lock_stitches` tells the planner to add lock stitches even if global same-color collapsing would otherwise avoid them.

### Why this abstraction is useful

If elements tried to emit final color blocks or machine-format commands directly, they would need knowledge about later elements, color changes, stops, palette matching, and file writing. `StitchGroup` keeps object code local and leaves whole-design decisions to the correct layer.

### Example: one object emits multiple groups

Imagine an object that produces two blue stitched islands far apart from each other. It can return two blue `StitchGroup`s. The planner then decides whether the distance between them should be handled as continuous sewing, a jump, or a lock/jump/tie-in sequence.

---

## 4. `ColorBlock` and color-based grouping

[`lib/stitch_plan/color_block.py`](../lib/stitch_plan/color_block.py) defines `ColorBlock`, a sequence of stitches that all use the same thread color.

It contains:

- `color`
- `stitches`

Its `color` property normalizes values into a [`ThreadColor`](../lib/threads/color.py) when possible.

### Why same-color grouping matters

`ColorBlock` is not just a UI or simulator concept. It affects machine output structure.

Machine embroidery files are organized around thread changes. Two different objects can still belong to the same machine color run if they use the same thread and no color change happens between them.

So `ColorBlock` represents:

> “Everything the machine does while one thread color is active.”

### What `ColorBlock` provides

In addition to storing stitches, it provides:

- `num_stitches`
- `num_stops`
- `num_trims`
- `num_jumps`
- `estimated_thread`
- `bounding_box`
- `trim_after`
- `stop_after`

The last two are derived by inspecting the tail of the block, not by storing separate booleans.

### Command stitches live inside the block

`ColorBlock.add_stitch()` can append either a real stitch or a command stitch. If called with only flags such as `trim=True`, it reuses the last stitch position, which matches the idea that commands happen “at the current location”.

### Duplicate stitch filtering

`ColorBlock.filter_duplicate_stitches()` removes accidental near-duplicate points while protecting meaningful commands and intentional lock stitches.

It does not treat these as removable duplicates:

- jumps
- stops
- trims
- color changes
- stitches tagged as `lock_stitch`

### Example: object grouping is not color grouping

Suppose the design order is:

1. blue satin border
2. blue running-stitch detail
3. red fill

Items 1 and 2 may come from different objects, but they can still be part of the same `ColorBlock`. Item 3 must start a new `ColorBlock` because the thread changes.

---

## 5. `StitchPlan` assembly logic

The main planning logic lives in [`lib/stitch_plan/stitch_plan.py`](../lib/stitch_plan/stitch_plan.py).

That file contains both:

- `stitch_groups_to_stitch_plan(...)`
- the `StitchPlan` class itself

### What `StitchPlan` holds

`StitchPlan` is the whole ordered design, represented as a list of `ColorBlock`s plus design-level queries such as:

- `num_colors`
- `num_color_blocks`
- `num_stops`
- `num_trims`
- `num_stitches`
- `num_jumps`
- `bounding_box`
- `dimensions`
- `dimensions_mm`
- `extents`
- `estimated_thread`

This is the representation used for rendering, statistics, thread handling, export, and imported-file reconstruction.

### How `stitch_groups_to_stitch_plan()` assembles the plan

At a high level, the function takes an ordered list of `StitchGroup`s and performs whole-design planning.

#### 1. Validate and normalize settings

If there are no stitch groups, Ink/Stitch reports an error.

If `collapse_len` is absent, it defaults to `3.0` mm and is converted into SVG pixel units.

#### 2. Start the first color block

A new `StitchPlan` is created, and the first `ColorBlock` uses the first group’s color.

The function also tracks:

- `previous_stitch_group`
- `need_tie_in`

`need_tie_in` means “before sewing the next real stitches, should a jump/tie-in sequence be inserted?”

#### 3. Handle color changes

If the current group’s color differs from the active block’s color, the planner:

1. ties off the previous group if needed
2. appends a `color_change=True` stitch to the current block
3. creates a new `ColorBlock` for the new color
4. marks the new group as needing a tie-in

This is where object output becomes machine color structure.

#### 4. Handle same-color movement between groups

If the color stays the same, the planner decides whether the distance between the previous block end and the next group start should be collapsed into continuous sewing or treated as a jump boundary.

The decision priority is:

1. `previous_stitch_group.force_lock_stitches`
2. `previous_stitch_group.min_jump_stitch_length`
3. global `collapse_len`

If the transition requires a lock boundary, the planner adds end lock stitches from the previous group when available and marks the next group as needing a tie-in.

#### 5. Insert tie-ins and jumps

When `need_tie_in` is true, the planner checks for start lock stitches.

- If start locks exist, it inserts a jump to the first lock stitch and then appends the lock stitches.
- Otherwise, it inserts a jump to the first real stitch.

Only after that does it append the group’s real stitches.

#### 6. Respect `trim_after` and `stop_after`

After the group’s stitches are appended, the planner checks its boundary requests:

- if `trim_after` or `stop_after` is set, add end lock stitches first when available
- if `trim_after` is set, append a trim command stitch
- if `stop_after` is set, append a stop command stitch

Either case forces the next group to begin with a tie-in.

#### 7. Tie off the end of the design

After the loop, if the design has not already ended at a boundary that handled securing, the planner adds end lock stitches for the last group.

#### 8. Remove an empty trailing block

If planning created an empty final color block after a stop, that block is deleted.

#### 9. Filter duplicate stitches

Finally, `stitch_plan.filter_duplicate_stitches(min_stitch_len)` removes accidental duplicates while preserving commands and tagged lock stitches.

### Where whole-design decisions are made

This file is where Ink/Stitch decides:

- tie-ins
- tie-offs
- jumps
- trims
- stops
- color changes
- same-color collapse vs jump boundaries

That is the main answer to the question, “Where are whole-design machine decisions made?”

### Example: multiple stitch groups becoming a stitch plan

Imagine three groups in order:

1. Group A: blue, left leaf
2. Group B: blue, right leaf, far away from A
3. Group C: red, flower center

Possible planned result:

- `ColorBlock` 1, blue
	- jump to A
	- tie-in for A
	- A stitches
	- tie-off for A because B is far away
	- jump to B
	- tie-in for B
	- B stitches
	- tie-off for B because color changes next
	- color change command
- `ColorBlock` 2, red
	- jump to C
	- tie-in for C
	- C stitches
	- final tie-off

Three `StitchGroup`s became two `ColorBlock`s inside one `StitchPlan`.

### Example: when a jump leads to locks or trims

Suppose Group A and Group B are the same color, but their endpoints are 20 mm apart and the collapse length is 3 mm.

The planner will not create one long accidental travel stitch. Instead it can:

1. add end lock stitches for A
2. mark B as needing a tie-in
3. insert a jump at the start of B
4. add start lock stitches for B

If Group A also had `trim_after=True`, then the planner would insert a trim after the end locks, and the next group would still begin with a jump/tie-in sequence.

### Example: a color change creates a new color block

If the next group’s thread color is different, Ink/Stitch does not keep appending to the same block. It:

1. ties off the old color if needed
2. inserts a `color_change` command in the old block
3. creates a new `ColorBlock` for the new thread

So `ColorBlock` boundaries are real machine-output boundaries.

---

## 6. Export pipeline to machine formats

Export is handled mainly by:

- [`lib/extensions/output.py`](../lib/extensions/output.py)
- [`lib/output.py`](../lib/output.py)
- `pystitch`

Export is not only byte serialization. It includes planning, command mapping, thread handling, origin selection, scaling, and final file writing.

### Top-level export flow

In [`lib/extensions/output.py`](../lib/extensions/output.py), `Output.effect()`:

1. gathers embroiderable elements
2. reads metadata such as `collapse_len_mm`, `min_stitch_len_mm`, and the chosen thread palette
3. turns elements into `StitchGroup`s with `elements_to_stitch_groups(...)`
4. turns those groups into a `StitchPlan` with `stitch_groups_to_stitch_plan(...)`
5. applies thread-palette information with [`ThreadCatalog`](../lib/threads/catalog.py)
6. writes the result to a temporary embroidery file
7. streams the file to stdout so Inkscape can save it to the user’s chosen destination

That temporary-file/stdout behavior matters because Inkscape extensions receive the produced file data through stdout.

### Pattern creation and thread metadata

In [`lib/output.py`](../lib/output.py), `write_embroidery_file(...)` creates `pystitch.EmbPattern()`.

For each `ColorBlock`, it first adds thread metadata with:

```python
pattern.add_thread(color_block.color.pystitch_thread)
```

That uses [`lib/threads/color.py`](../lib/threads/color.py) to convert `ThreadColor` into the structure `pystitch` expects.

### Command translation

`get_command(stitch)` maps Ink/Stitch flags to `pystitch` commands:

- `jump` -> `pystitch.JUMP`
- `trim` -> `pystitch.TRIM`
- `color_change` -> `pystitch.COLOR_CHANGE`
- `stop` -> `pystitch.STOP`
- otherwise -> `pystitch.NEEDLE_AT`

The pattern is then filled with `pattern.add_stitch_absolute(...)`.

### Origin handling

`get_origin(svg, bounding_box)` chooses the origin like this:

1. use a global `origin` command if the SVG defines one
2. otherwise use the center of the stitch plan’s bounding box

There is also special handling for a global `stop_position` command: before a stop, `jump_to_stop_point(...)` can move the machine to a requested parking location.

### Scaling and unit conversion

The stitch-plan layer works in SVG pixels, but machine formats usually work in millimeters or tenths of a millimeter.

`write_embroidery_file(...)` sets:

```python
scale = 10 / PIXELS_PER_MM
```

That converts pixels to tenths of a millimeter. Instead of rewriting every stitch coordinate manually, Ink/Stitch passes these settings to `pystitch`:

- `translate = -origin`
- `scale = (scale, scale)`

So export is:

1. emit stitches in internal coordinate space
2. let `pystitch` apply translation and unit conversion during file writing

### Additional export settings

`write_embroidery_file(...)` also sets:

- `full_jump = True`
- `trims = True`
- `encode = True` for most machine formats

CSV export is treated specially so post-processing does not obscure the raw stitch/command order that users may want to compare with the simulator.

### How export uses `pystitch`

Ink/Stitch uses `pystitch` for:

- embroidery pattern objects
- thread list storage
- command encoding
- final format writing

Ink/Stitch itself still owns the higher-level planning logic.

---

## 7. Import pipeline from machine formats back to SVG-based structures

Import is handled mainly by:

- [`lib/extensions/input.py`](../lib/extensions/input.py)
- [`lib/stitch_plan/generate_stitch_plan.py`](../lib/stitch_plan/generate_stitch_plan.py)
- [`lib/svg/rendering.py`](../lib/svg/rendering.py)

The main idea is that import is a reconstruction step, not a perfect inversion of authoring.

Machine files usually preserve final stitch coordinates and many commands, but not high-level source information such as “this used to be a satin column with these parameters”.

### Top-level input flow

In [`lib/extensions/input.py`](../lib/extensions/input.py), `Input.run(args)`:

1. receives the embroidery filename
2. rejects color-only sidecar files such as `.edr`, `.col`, and `.inf`
3. calls `generate_stitch_plan(embroidery_file)`
4. writes current Ink/Stitch SVG metadata onto the generated SVG document
5. prints the SVG back to Inkscape

The rejection of `.edr`, `.col`, and `.inf` is intentional: they are color-list files, not stitch-geometry files.

### Reading an embroidery file into a `StitchPlan`

[`lib/stitch_plan/generate_stitch_plan.py`](../lib/stitch_plan/generate_stitch_plan.py) performs the actual import conversion.

#### 1. Read with `pystitch`

`pystitch.read(embroidery_file)` loads the embroidery pattern.

#### 2. Iterate machine color blocks

The code calls `pattern.get_as_colorblocks()`, which yields:

- `raw_stitches`
- `thread`

For each pair, Ink/Stitch creates a new `ColorBlock` in a new `StitchPlan`.

#### 3. Convert coordinates back to SVG pixels

Each raw machine coordinate is converted with:

```python
x * PIXELS_PER_MM / 10.0
y * PIXELS_PER_MM / 10.0
```

That reverses the export-side pixels-to-tenths-of-a-millimeter conversion.

#### 4. Map machine commands back into `Stitch` objects

The importer handles commands like this:

- `pystitch.STITCH` -> append a normal `Stitch`
- `pystitch.TRIM` -> append a trim command stitch, or if command import is disabled, start a new block without storing the trim
- `pystitch.STOP` -> append a stop command stitch and then start a new block

By default, import keeps commands visible as symbols.

#### 5. Clean up the imported plan

After reading, Ink/Stitch removes empty color blocks and drops a redundant final stop at the very end of the design.

### Rendering the imported `StitchPlan` back into SVG

Once the imported plan exists, `generate_stitch_plan()` creates a new SVG document sized from the plan’s `extents` and calls [`render_stitch_plan()`](../lib/svg/rendering.py).

That rendering code in [`lib/svg/rendering.py`](../lib/svg/rendering.py) creates a stitch-plan layer and then, for each `ColorBlock`, creates a corresponding SVG group.

For standard rendering, `color_block_to_paths(...)`:

1. splits a color block into contiguous point lists
2. breaks paths at trims, and optionally at jumps
3. creates SVG path elements for each run
4. marks those paths with `stroke_method = manual_stitch`
5. adds visual command markers or command attributes for trim/stop boundaries

This is how imported embroidery becomes editable SVG content again: as manual-stitch paths plus command markers, grouped by color block.

### Stitch-plan visualization and rendering

[`lib/svg/rendering.py`](../lib/svg/rendering.py) matters for more than the simulator. It is the module that converts a `StitchPlan` into visible SVG structures.

`render_stitch_plan(...)` can render the plan either as simplified path segments or as more realistic thread-like strokes. For import, the important mode is the SVG-path/manual-stitch representation.

### Final SVG adjustments during import

After rendering, `generate_stitch_plan()`:

- renames the stitch-plan layer to the input filename
- removes the fixed layer id
- translates the layer so the embroidery origin sits at the center of the canvas

The code explicitly notes that this is not the same thing as visually centering the design. It centers the origin, not necessarily the design’s bounding box.

### Example: import reconstructs a manual-stitch SVG

Suppose an imported DST file contains:

- blue border stitches
- a trim
- more blue detail stitches
- a stop
- red center stitches

Ink/Stitch reconstructs that approximately as:

1. a `StitchPlan` with blue and red `ColorBlock`s
2. command stitches for trim and stop where requested by import mode
3. one SVG layer containing grouped manual-stitch paths
4. command symbols or attributes attached to the relevant path boundaries

What is preserved reasonably well:

- stitch coordinates
- color order
- many explicit machine commands
- thread metadata, if the source file stored it

What is reconstructed rather than preserved:

- original SVG object boundaries
- satin/fill/stroke parameters
- authoring-time intent
- many high-level distinctions lost when the design was flattened into machine stitches

That is why import should be understood as translation back into a stitch-plan-based SVG representation, not perfect source recovery.

---

## 8. Thread colors and palettes

Thread metadata and palette matching are handled mainly by:

- [`lib/threads/color.py`](../lib/threads/color.py)
- [`lib/threads/catalog.py`](../lib/threads/catalog.py)
- [`lib/threads/palette.py`](../lib/threads/palette.py)

### `ThreadColor`

[`lib/threads/color.py`](../lib/threads/color.py) defines `ThreadColor`, which stores:

- RGB color
- `name`
- `number`
- `manufacturer`
- `description`
- `chart`

It can be built from CSS-like colors, RGB tuples, or imported `EmbThread` data from `pystitch`.

It also exposes `pystitch_thread`, which converts the thread into the structure needed by `pystitch` during export.

### Palette catalog loading

[`ThreadCatalog`](../lib/threads/catalog.py) loads thread palettes from two places:

1. the user’s Inkscape palette directory
2. Ink/Stitch’s bundled `palettes/` directory

It searches for `InkStitch*.gpl` files and parses them through [`ThreadPalette`](../lib/threads/palette.py).

### Palette matching

`match_and_apply_palette(...)` either:

- uses a specifically requested palette, or
- tries to infer a palette from the stitch plan’s color blocks

Automatic matching only succeeds if more than 80% of the stitch plan’s colors are exact matches for a palette.

### Applying a palette

When a palette is applied, Ink/Stitch updates each `ColorBlock`’s `ThreadColor` metadata to the nearest palette thread, including name, number, manufacturer, and description. Special cutwork chart information is preserved instead of being overwritten.

### How nearest-color selection works

[`lib/threads/palette.py`](../lib/threads/palette.py) compares colors in CIE Lab space using `delta_e_cie1994` with textile-oriented weighting. So palette matching is based on perceptual color distance, not just naive RGB comparison.

### Where palettes fit into the pipeline

Colors live on `ColorBlock`s inside the `StitchPlan`, so palette work naturally happens after stitch-plan assembly and before export.

On import, source files may already provide thread metadata. Ink/Stitch preserves and uses that when building imported color blocks and rendering the resulting SVG.

---

## 9. Practical contributor implications

When working in this area, the most important rule is to make changes at the correct layer.

### If you are changing an embroidery element

Return good `StitchGroup`s.

That means deciding:

- where continuous local sewing starts and ends
- which color each group uses
- whether the group requests `trim_after` or `stop_after`
- what lock-stitch strategies are available
- whether a custom minimum jump threshold is needed

Do not try to build final machine color blocks directly there.

### If you are changing whole-design machine behavior

Edit [`lib/stitch_plan/stitch_plan.py`](../lib/stitch_plan/stitch_plan.py). That is where logic for tie-ins, tie-offs, jump/collapse decisions, trims, stops, color changes, and duplicate filtering belongs.

### If you are changing export behavior

Start with:

- [`lib/extensions/output.py`](../lib/extensions/output.py)
- [`lib/output.py`](../lib/output.py)
- the `pystitch` integration points

### If you are changing import behavior

Start with:

- [`lib/extensions/input.py`](../lib/extensions/input.py)
- [`lib/stitch_plan/generate_stitch_plan.py`](../lib/stitch_plan/generate_stitch_plan.py)
- [`lib/svg/rendering.py`](../lib/svg/rendering.py)

### If you are changing thread metadata or palettes

Start with:

- [`lib/threads/color.py`](../lib/threads/color.py)
- [`lib/threads/catalog.py`](../lib/threads/catalog.py)
- [`lib/threads/palette.py`](../lib/threads/palette.py)

---

## 10. Common confusion points clarified

### `StitchGroup` is not the final export representation

Correct. It is an intermediate, object-level description. The stitch-plan layer may still insert jumps, ties, trims, stops, and color changes around it.

### `ColorBlock` is not just a UI concept

Correct. It reflects machine-output structure by active thread color and directly affects export behavior.

### Export is not only byte serialization

Correct. Export includes planning, palette application, command mapping, origin handling, scaling, and final writing through `pystitch`.

### Import is not a perfect inverse of authoring

Correct. Import reconstructs a useful SVG representation of the stitch plan, usually as manual-stitch paths and command markers. It cannot perfectly recover high-level authoring intent that is no longer present in the machine file.

---

## 11. Summary

If you remember only four things, remember these:

1. [`Stitch`](../lib/stitch_plan/stitch.py) is one coordinate plus machine/planning flags.
2. [`StitchGroup`](../lib/stitch_plan/stitch_group.py) is an object-level intermediate representation.
3. [`ColorBlock`](../lib/stitch_plan/color_block.py) is a same-thread machine-output grouping.
4. [`StitchPlan`](../lib/stitch_plan/stitch_plan.py) is the complete planned design used for rendering, statistics, import reconstruction, and export.

Whole-design decisions like jumps, trims, ties, and color transitions are made in the stitch-plan layer, especially [`lib/stitch_plan/stitch_plan.py`](../lib/stitch_plan/stitch_plan.py).

Export uses [`lib/extensions/output.py`](../lib/extensions/output.py), [`lib/output.py`](../lib/output.py), and `pystitch` to map that plan into machine commands and file data.

Import uses [`lib/extensions/input.py`](../lib/extensions/input.py), [`lib/stitch_plan/generate_stitch_plan.py`](../lib/stitch_plan/generate_stitch_plan.py), and [`lib/svg/rendering.py`](../lib/svg/rendering.py) to rebuild a stitch-plan-based SVG representation.

