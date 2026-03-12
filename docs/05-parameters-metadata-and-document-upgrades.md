# Ink/Stitch Parameters, Metadata, and Document Upgrades

This chapter explains where Ink/Stitch configuration lives, how code turns that configuration into behavior, and why compatibility work matters so much in this project.

If you are new to the codebase, the most important idea is this:

> Ink/Stitch stores most of its embroidery intent inside the SVG itself.

That intent is split across two main layers:

- **per-element settings** stored as `inkstitch:*` attributes on SVG objects
- **document-level settings** stored in SVG metadata elements, with some defaults coming from persistent user settings

Those stored values are not incidental metadata. They are the application's saved state. They tell Ink/Stitch how to generate stitches, how to export them, and how to reopen an old design later without losing meaning.

Because these settings are embedded in SVG, changing a parameter name, changing its meaning, or changing its default behavior is a compatibility change. It affects existing documents, not just current code.

---

## 1. Where Ink/Stitch configuration lives

Ink/Stitch configuration does **not** come from one single place. It is layered.

At a high level, configuration lives in four places:

1. **Hardcoded defaults in Python code**
	- Examples: parameter defaults declared with `@param`, and document metadata defaults in [lib/utils/settings.py](../lib/utils/settings.py).
2. **Persistent user settings**
	- Stored outside the document in a user `settings.json` file via [lib/utils/settings.py](../lib/utils/settings.py).
3. **Document-level metadata**
	- Stored inside the SVG `<metadata>` section through [lib/metadata.py](../lib/metadata.py).
4. **Per-element overrides**
	- Stored directly on individual SVG nodes as `inkstitch:*` attributes defined in [lib/svg/tags.py](../lib/svg/tags.py) and read through [lib/elements/element.py](../lib/elements/element.py).

These layers exist because different settings answer different questions:

- “How should this specific path be stitched?” → per-element attribute
- “How should this whole design export?” → document metadata
- “What should new documents start with by default?” → user settings
- “What if nothing was explicitly set?” → hardcoded defaults

### A quick mental model

Think of Ink/Stitch state like this:

- **SVG object attributes** carry the embroidery meaning of individual shapes.
- **SVG metadata** carries document-wide behavior and version markers.
- **User settings** supply defaults for new or incomplete documents.
- **Python declarations** describe how all of this should be interpreted.

---

## 2. Per-element attributes and namespaced SVG storage

The authoritative registry of Ink/Stitch SVG attributes lives in [lib/svg/tags.py](../lib/svg/tags.py).

That file:

- registers the `inkstitch` XML namespace (`http://inkstitch.org/namespace`)
- defines the `INKSTITCH_ATTRIBS` mapping
- lists the supported per-element attribute names such as `fill_method`, `row_spacing_mm`, `ties`, `satin_column`, `trim_after`, and many others

Conceptually, `INKSTITCH_ATTRIBS['fill_method']` maps the logical parameter name `fill_method` to the fully namespaced SVG attribute `inkstitch:fill_method`.

### Why these attributes are core application data

It is tempting to think of `inkstitch:*` attributes as “extra metadata attached to SVG.” That is the wrong model.

For Ink/Stitch, these attributes are the persisted embroidery model.

They describe things such as:

- which fill algorithm to use
- whether an object is a satin column
- stitch lengths and spacing
- underlay settings
- tie-in / tie-off behavior
- trim and stop commands
- JSON-encoded structured settings for advanced features

If those attributes disappear, the document may still be valid SVG for drawing purposes, but it has lost essential embroidery intent.

### Why store settings in SVG instead of separate project files?

This design makes the document self-contained:

- the embroidery meaning travels with the artwork
- copying an object in Inkscape carries its Ink/Stitch settings with it
- version control sees the actual persisted state in one file
- a user can reopen the same SVG later and Ink/Stitch can reconstruct behavior from the document itself

This is why parameter storage is embedded directly in SVG nodes instead of being kept only in ephemeral UI state or separate sidecar files.

### Example: what per-element storage looks like

A path in an Ink/Stitch document might conceptually look like this:

```xml
<path
  d="..."
  inkstitch:fill_method="guided_fill"
  inkstitch:row_spacing_mm="0.4"
  inkstitch:fill_underlay="true"
  inkstitch:min_stitch_length_mm="0.2" />
```

Those values are not just hints for the UI. They are the saved instructions from which stitch generation is reconstructed.

---

## 3. The `@param` declaration model

The central declaration mechanism lives in [lib/elements/element.py](../lib/elements/element.py).

That file defines:

- the `Param` class
- the `param()` decorator
- `EmbroideryElement.get_params()`, which discovers declared parameters by reflecting over properties on an element class

### What `@param` does

The `@param` decorator attaches a `Param` object to a property getter. That single declaration carries several meanings at once:

- **storage key**: the SVG attribute name, such as `fill_method`
- **human-readable description**: the label shown in UI
- **default value**: what to use when the parameter is absent
- **type**: boolean, float, dropdown, combo, toggle, etc.
- **unit**: `mm`, `%`, `deg`, and so on
- **group**: which tab or section it belongs to
- **sort order**: how it should be ordered in UI
- **UI hints**: options, tooltips, and conditional visibility rules such as `select_items`

This matters architecturally because it keeps **code meaning, storage meaning, and UI meaning aligned**.

Without this system, Ink/Stitch would need separate definitions for:

- how a setting is stored in SVG
- how it is parsed
- how it appears in the parameters dialog
- how it is grouped and labeled

Instead, one declaration drives all three.

### Concrete example: `fill_method`

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `FillStitch.fill_method` is declared roughly as:

- name: `fill_method`
- description: “Fill method”
- type: `combo`
- default: `0` for UI selection purposes
- options: a list of fill algorithms such as auto fill, contour fill, guided fill, meander fill, tartan fill, and others

That one declaration is then used in three different ways:

1. **Storage**
	- The value is stored on the SVG element as `inkstitch:fill_method="guided_fill"` or another option id.
2. **Runtime access**
	- The property implementation calls `self.get_param('fill_method', 'auto_fill')`.
3. **UI generation**
	- The parameters dialog reads the `Param` metadata and builds the correct combo-box widget with the declared options.

### How the declaration reaches the UI

At a high level, [lib/extensions/params.py](../lib/extensions/params.py) does the following:

1. It gathers selected embroidery elements.
2. For each element class, it calls `cls.get_params()`.
3. It reads current values from the selected nodes.
4. It groups and sorts parameters using `group` and `sort_index`.
5. It creates widgets based on `param.type`.
6. It uses `description`, `tooltip`, `unit`, `options`, and `select_items` to build and conditionally show the UI.
7. On apply, it writes changed values back to the SVG via `set_param()`.

So the parameter system is **not** merely UI metadata. It is the bridge between persisted SVG state, runtime interpretation, and editor UI.

For more on the UI side, see [08-ui-simulator-and-interactive-tools.md](08-ui-simulator-and-interactive-tools.md).

---

## 4. Parameter parsing and unit conversion helpers

[lib/elements/element.py](../lib/elements/element.py) also defines the common helpers that turn stored SVG strings into typed runtime values.

This is important because SVG attributes are persisted as text, but stitch generation needs booleans, numbers, arrays, and structured objects.

### `get_param()`

`get_param(name, default)` is the base accessor.

- It reads the raw attribute from `self.node` using `INKSTITCH_ATTRIBS[name]`.
- It strips whitespace.
- If the attribute is missing or empty, it returns the supplied default.

Everything else builds on this.

### `get_boolean_param()`

`get_boolean_param()` reads a parameter and interprets common truthy strings such as:

- `yes`
- `y`
- `true`
- `t`
- `1`

This keeps SVG storage tolerant of legacy or manually edited values.

### `get_float_param()` and `get_int_param()`

These parse numeric values and, importantly, apply unit conversion when the parameter name ends with `_mm`.

That conversion multiplies by `PIXELS_PER_MM`, so a value stored in millimeters in the SVG becomes an internal distance in Ink/Stitch's geometry space.

This is a subtle but important point:

- **stored form** is often human-friendly, in millimeters
- **runtime form** inside element code is often in internal SVG/pixel units

That is why many properties have names like `row_spacing_mm` or `lock_end_scale_mm` in storage, but their Python property returns a converted internal numeric value.

### Split-value helpers

Some parameters can accept one value or two space-separated values.

`get_split_float_param()` handles that case:

- no value → return default pair
- one value → use the same value for both components
- two values → parse both separately

Example: in [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `meander_scale_percent` is read through `get_split_float_param()`. That lets a user write either:

- one percentage, such as `120`, meaning scale both axes equally
- two percentages, such as `120 80`, meaning horizontal and vertical scaling differ

`FillStitch.meander_scale` then converts that pair into runtime scale factors.

There are related helpers for repeated lists as well:

- `get_multiple_int_param()`
- `get_multiple_float_param()`
- `get_split_mm_param_as_px()`

### JSON parameter access

Some settings are too structured to fit comfortably into a single scalar string.

For that, `EmbroideryElement` provides:

- `get_json_param()`
- `set_json_param()`

These store JSON in a single SVG attribute and parse it back into a `DotDict`-like object.

#### Example: `sew_stack`

In [lib/sew_stack/__init__.py](../lib/sew_stack/__init__.py), the `SewStack` class loads:

- `inkstitch:sew_stack` using `get_json_param('sew_stack', default=dict(layers=list()))`

That JSON describes a stack of stitch layers. When edited, `save()` writes the structure back with `set_json_param()`.

This is still per-element persisted state; it is just structured rather than scalar.

### A concrete parameter flow: declaration → storage → runtime logic

Here is one complete example using `fill_method`:

1. **Declaration**
	- [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py) declares `fill_method` with `@param(...)` and a list of options.
2. **Storage**
	- The chosen option is persisted on the SVG node as `inkstitch:fill_method`.
3. **Parsing**
	- The property implementation reads it with `get_param('fill_method', 'auto_fill')`.
4. **Runtime behavior**
	- Later in `FillStitch` stitch generation, the code branches on `self.fill_method` and calls methods such as `do_guided_fill()`, `do_contour_fill()`, `do_meander_fill()`, or `do_auto_fill()`.
5. **UI**
	- The params dialog reads the same declaration and builds the matching combo box.

That is the core pattern repeated across the codebase.

---

## 5. Document-level metadata and defaults

Document-wide settings are handled by [lib/metadata.py](../lib/metadata.py).

The key class is `InkStitchMetadata`, a dict-like wrapper around the SVG document's `<metadata>` section.

### How metadata is stored

When you write:

```python
metadata['min_stitch_len_mm'] = 0.1
```

`InkStitchMetadata` creates or updates a child element in the metadata section with an `inkstitch` namespace tag and stores the value as JSON text.

Conceptually it becomes something like:

```xml
<metadata>
  <inkstitch:min_stitch_len_mm>0.1</inkstitch:min_stitch_len_mm>
  <inkstitch:collapse_len_mm>3</inkstitch:collapse_len_mm>
  <inkstitch:rotate_on_export>90</inkstitch:rotate_on_export>
</metadata>
```

This differs from per-element settings in two important ways:

- metadata applies to the **whole document**, not one object
- metadata is stored as child elements in `<metadata>`, not as attributes on individual shapes

### What kinds of values live here?

Typical document metadata includes:

- `min_stitch_len_mm`
- `collapse_len_mm`
- `rotate_on_export`
- `thread-palette`
- `inkstitch_svg_version`

Some of these are seeded by defaults in [lib/utils/settings.py](../lib/utils/settings.py), while others are simply created when a feature uses them.

### How defaults are initialized

`InkStitchMetadata.__init__()` loops through `DEFAULT_METADATA` from [lib/utils/settings.py](../lib/utils/settings.py). If a defaulted metadata key is missing, it writes a value from `global_settings`, such as:

- `default_min_stitch_len_mm`
- `default_collapse_len_mm`

This means that simply wrapping a document in `InkStitchMetadata` can materialize missing document metadata from the current user's global defaults.

That behavior is important for understanding precedence.

### Example: a document setting influencing output behavior

In [lib/extensions/output.py](../lib/extensions/output.py), the export code reads document metadata and passes it into stitch plan generation:

- `collapse_len_mm`
- `min_stitch_len_mm`

Those values influence how stitch groups are turned into the final stitch plan for the whole document.

The same file also uses document metadata for export-specific behavior:

- `thread-palette` is applied to the stitch plan
- `rotate_on_export` is passed into export settings before writing the embroidery file

So document metadata is not passive bookkeeping. It directly changes runtime results.

---

## 6. User/global settings

Persistent user settings live in [lib/utils/settings.py](../lib/utils/settings.py).

That module defines:

- `DEFAULT_METADATA`: built-in defaults for some document metadata values
- `DEFAULT_SETTINGS`: built-in defaults for user preferences
- `GlobalSettings`: a dict-like wrapper around a user `settings.json` file
- `global_settings`: the singleton used throughout the codebase

### What user settings are for

User settings hold values that should persist across documents for one installation or user profile, such as:

- default minimum stitch length
- default collapse length
- cache size
- simulator preferences
- lettering UI preferences
- various tool defaults

These are **not** the same thing as document metadata.

- **User settings** belong to the local user environment.
- **Document metadata** belongs to the SVG file and travels with it.

If you send someone an SVG, you are sending document metadata and per-element attributes with it. You are **not** sending your personal `settings.json`.

### Precedence and layering: the important nuance

There is no single universal precedence chain for every setting, but a useful rule of thumb is:

1. **Hardcoded defaults in code** provide a fallback.
2. **User settings** customize defaults for this installation.
3. **Document metadata** stores document-wide choices inside the SVG.
4. **Per-element attributes** override behavior for one object when such an override exists.

However, not all settings participate in all four layers.

#### Example: minimum stitch length layering

Minimum stitch length is a good example because it exists at multiple levels:

- **Hardcoded base default**: `DEFAULT_METADATA['min_stitch_len_mm'] = 0.1`
- **User-level default**: `global_settings['default_min_stitch_len_mm']`
- **Document-level value**: metadata key `min_stitch_len_mm`
- **Per-element override**: `inkstitch:min_stitch_length_mm` on an individual object

In practice, the flow works like this:

1. A new or incomplete document gets `min_stitch_len_mm` initialized from the current user's default.
2. Document-wide operations such as export use `metadata['min_stitch_len_mm']`.
3. An individual object may also define `inkstitch:min_stitch_length_mm`.
4. In [lib/elements/element.py](../lib/elements/element.py), `EmbroideryElement.embroider()` applies `self.min_stitch_length` to each produced stitch group with `set_minimum_stitch_length()`.

So a contributor should not assume “the default” comes from one place. There are multiple layers, and the active one depends on what behavior is being discussed.

---

## 7. Versioning, migration, and document upgrades

Compatibility logic lives primarily in [lib/update.py](../lib/update.py).

This is one of the most important files to understand if you change parameter names, parameter semantics, or persisted command structures.

### Why Ink/Stitch needs explicit upgrades

Because Ink/Stitch stores its state inside SVG, older documents keep old state forever unless the application migrates them.

That means a code change such as:

- renaming a parameter
- changing accepted values
- changing the meaning of a boolean
- changing the units of a stored value
- changing default behavior
- renaming command symbols in the SVG

can break old files unless upgrade logic translates the old representation into the new one.

This is why schema changes are compatibility work, not mere refactors.

### Version marker: `inkstitch_svg_version`

Ink/Stitch uses document metadata to store a version marker:

- `inkstitch_svg_version`

`update_inkstitch_document()` reads that marker, compares it to the current `INKSTITCH_SVG_VERSION`, and decides whether migration is needed.

If the document is unversioned but contains Ink/Stitch data, Ink/Stitch treats it as an older document and can run migrations.

If the document has no Ink/Stitch elements at all, the updater simply stamps the current version and stops.

### What upgrade logic actually does

`update_legacy_params()` runs migrations incrementally from the document's stored version up to the current one.

The current file contains version-specific steps such as:

- `_update_to_one()`
- `_update_to_two()`
- `_update_to_three()`

That incremental design matters. A document from version 1 must be able to reach version 3 by applying the missing transformations in order.

### Example: legacy parameter renaming

One major migration in `_update_to_one()` converts old `embroider_*` attributes into namespaced `inkstitch:*` attributes.

For example, a legacy attribute like:

- `embroider_fill_method`

is rewritten into the modern namespaced attribute registered in [lib/svg/tags.py](../lib/svg/tags.py).

This is a clear example of why storage names are part of the compatibility contract.

### Example: legacy value conversion

Another migration converts older numeric `fill_method` values into newer string ids:

- `0` → `auto_fill`
- `1` → `contour_fill`
- `2` → `guided_fill`
- `3` → `legacy_fill`

That means even when a parameter keeps the same conceptual purpose, changing its representation still requires upgrade logic.

### Example: changed defaults requiring migration

The updater also handles cases where default behavior changed over time.

For example, `_update_to_one()` includes logic for changes such as:

- setting `fill_underlay` explicitly when older documents relied on previous implicit behavior
- assigning a `running_stitch_length_mm` default for non-satin elements when older files omitted it

This is important because changing a default in new code does **not** automatically preserve the old appearance of old documents. Sometimes the upgrader must write an explicit value so old files continue to behave as intended.

### Example: units and semantics changes

Migration code also corrects stored values when units or semantics changed.

One example in `_update_to_one()` converts legacy `grid_size`, which had been stored in pixels even though it should have been millimeters, into the new `grid_size_mm` representation.

Another example in `_update_to_three()` splits zigzag stroke pull compensation into a more specific `stroke_pull_compensation_mm` value and adjusts the numeric meaning.

This kind of migration is more than renaming. It is semantic translation.

### Command migrations matter too

Upgrades are not limited to parameter attributes.

`update_legacy_commands()` renames old command symbols such as:

- `inkstitch_fill_start` → `starting_point`
- `inkstitch_fill_end` → `ending_point`
- `inkstitch_satin_start` → `autoroute_start`

and then updates or repositions command uses accordingly.

So when you change command identifiers or command behavior, you are also changing persisted document structure and may need migration code.

---

## 8. Practical contributor implications

If you change anything in the parameter or metadata schema, ask yourself four questions.

### 1. Where is this value stored?

Is it stored as:

- a per-element `inkstitch:*` attribute?
- a metadata element in `<metadata>`?
- a user setting in `settings.json`?

You need to know which persistence layer you are changing.

### 2. Who reads it?

Possible readers include:

- element runtime code in [lib/elements/element.py](../lib/elements/element.py) and subclasses
- export code such as [lib/extensions/output.py](../lib/extensions/output.py)
- preferences UI
- parameters UI in [lib/extensions/params.py](../lib/extensions/params.py)
- cache key generation in `EmbroideryElement.get_cache_key()`

If you change representation, all readers must still agree.

### 3. Does an old document need help?

If the answer is yes, add migration logic in [lib/update.py](../lib/update.py).

Typical triggers for upgrade work include:

- renaming a parameter
- changing allowed values
- changing boolean encoding
- changing units
- changing a default in a way that would alter old output
- moving data between attributes or metadata
- renaming command symbols or related structure

### 4. Does the UI still describe reality?

Because `@param` declarations drive the parameters dialog, a change in runtime behavior often also requires checking:

- labels
- options
- units
- grouping
- conditional visibility
- default values

If those drift out of sync, the SVG may store one thing while the UI suggests another.

---

## Common confusion points clarified

### `inkstitch:*` attributes are core persisted state

They are not decorative metadata. They are the saved embroidery instructions attached to objects.

### Defaults do not all come from one place

Some defaults live in `@param` declarations, some in `DEFAULT_METADATA`, some in user settings, and some are written into the document when metadata is first initialized.

### Document metadata and user settings are different

Document metadata is part of the SVG and travels with it. User settings are local to one user's environment.

### Changing settings schema has backward-compatibility impact

If a persisted key or value changes, old SVG documents still contain the old form. That is why upgrade logic exists.

---

## Summary

To understand Ink/Stitch configuration, keep this model in mind:

- **Per-element settings** live on SVG nodes as `inkstitch:*` attributes.
- **Document-level settings** live in SVG metadata through `InkStitchMetadata`.
- **User settings** provide persistent defaults outside the document.
- **`@param` declarations** connect storage, runtime parsing, and UI.
- **Upgrade code** preserves meaning when stored schema or behavior changes.

If you remember only one contributor rule, remember this:

> In Ink/Stitch, changing a stored parameter name or meaning is a document compatibility change.

Treat it with the same care you would give to a file format migration.
