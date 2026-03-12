# Ink/Stitch UI, Simulator, and Interactive Tools

This document explains the user-facing layer that sits on top of Ink/Stitch's embroidery model and stitch-generation code.

If you are new to the codebase, keep this mental model in mind:

1. Ink/Stitch starts with SVG nodes and Ink/Stitch attributes stored in the SVG file.
2. Core element classes interpret those nodes as embroidery objects such as fills, strokes, and satin columns.
3. Stitch-generation code turns those objects into stitch groups and then into a `StitchPlan`.
4. The UI layer lets users inspect and edit settings, preview the result, simulate sew-out order, and troubleshoot problems.
5. The UI is a view and editing surface over that data. It is not where the embroidery algorithms live.

The most important files for this document are:

- [lib/extensions/params.py](../lib/extensions/params.py) for the parameter dialog and its live preview loop
- [lib/gui/](../lib/gui/) for shared wxPython panels and dialogs
- [lib/gui/presets.py](../lib/gui/presets.py) for saving and loading named settings
- [lib/gui/warnings.py](../lib/gui/warnings.py) for preview-rendering warnings in the params dialog
- [lib/gui/simulator/](../lib/gui/simulator/) for the simulation window, playback controls, and visualization widgets
- [lib/svg/rendering.py](../lib/svg/rendering.py) for converting a `StitchPlan` into SVG preview layers

This document also builds directly on [05-parameters-metadata-and-document-upgrades.md](05-parameters-metadata-and-document-upgrades.md). That earlier document explains how parameters are declared and stored. This one explains how the same metadata becomes concrete user interface.

## 1. UI layers in Ink/Stitch

Ink/Stitch has several layers that are easy to confuse when you first open the codebase.

| Layer | Main responsibility | Typical files |
| --- | --- | --- |
| Extension runtime | Integrate with Inkscape, load the document, gather the selection, handle upgrades, launch dialogs or emit output | [lib/extensions/base.py](../lib/extensions/base.py), extension entry points in [lib/extensions/](../lib/extensions/) |
| Core model and algorithms | Interpret SVG as embroidery objects and generate stitches | [lib/elements/](../lib/elements/), [lib/stitches/](../lib/stitches/), [lib/stitch_plan/](../lib/stitch_plan/) |
| User-facing UI | Show dialogs, simulator windows, previews, warnings, presets, and helper tools | [lib/gui/](../lib/gui/), plus UI-launching extension files such as [lib/extensions/params.py](../lib/extensions/params.py) and [lib/extensions/element_info.py](../lib/extensions/element_info.py) |

### Where the wxPython UI lives

The wxPython-based desktop UI lives primarily in [lib/gui/](../lib/gui/).

That directory contains reusable user-interface building blocks such as:

- preset management in [lib/gui/presets.py](../lib/gui/presets.py)
- warning display in [lib/gui/warnings.py](../lib/gui/warnings.py)
- simulator windows and panels in [lib/gui/simulator/](../lib/gui/simulator/)
- inspection and helper dialogs such as [lib/gui/element_info.py](../lib/gui/element_info.py), [lib/gui/abort_message.py](../lib/gui/abort_message.py), and [lib/gui/request_update_svg_version.py](../lib/gui/request_update_svg_version.py)

However, the UI usually does **not** start in `lib/gui/` by itself. The entry point is typically an extension class in [lib/extensions/](../lib/extensions/). For example, [lib/extensions/params.py](../lib/extensions/params.py) creates the embroidery-parameters window and wires it to the simulator.

### What is *not* UI code

New contributors often look at a dialog first and assume the logic must be there. In Ink/Stitch that is usually wrong.

- The dialog decides **what to show** and **when to re-render**.
- The element classes decide **what a setting means**.
- The stitch algorithms decide **what stitches to produce**.

For example, when the params dialog changes a fill angle or satin setting, the dialog does not recalculate stitches itself. Instead, it updates the backing SVG attributes and asks the normal embroidery pipeline to regenerate a preview.

### One selected SVG object can lead to multiple UI tabs

Another common surprise is that the params dialog does not operate on raw SVG objects one-to-one.

In [lib/extensions/params.py](../lib/extensions/params.py), `Params.embroidery_classes()` decides whether a selected node should be treated as a `FillStitch`, `Stroke`, `SatinColumn`, `Clone`, or some combination of those. A single SVG path with both fill and stroke can therefore produce more than one embroidery class, and the UI will show tabs for the embroidery meanings rather than just the original SVG element.

That is a direct consequence of Ink/Stitch's object model, described in [04-embroidery-object-model.md](04-embroidery-object-model.md).

## 2. The params dialog and how it is built

The main params dialog lives in [lib/extensions/params.py](../lib/extensions/params.py). This file is the most important place to read if you want to understand how parameter metadata becomes an editor.

At a high level, `Params.effect()` does the following:

1. gathers the selected nodes
2. reads document metadata such as minimum stitch length and collapse length
3. creates a [lib/gui/simulator/split_simulator_window.py](../lib/gui/simulator/split_simulator_window.py) `SplitSimulatorWindow`
4. places a `SettingsPanel` on one side and a `SimulatorPanel` on the other
5. starts a live preview loop so edits re-render the stitch plan

### The window structure

The UI assembled by `Params.effect()` is split into two halves:

- `SettingsPanel` in [lib/extensions/params.py](../lib/extensions/params.py) contains the notebook of tabs, the presets panel, warning area, and action buttons.
- `SimulatorPanel` in [lib/gui/simulator/simulator_panel.py](../lib/gui/simulator/simulator_panel.py) contains the interactive simulation view.

This split is important architecturally. The left side edits parameters. The right side visualizes the resulting stitch plan.

### How element metadata is gathered

The dialog does not hard-code a list of settings for fills, strokes, and satins.

Instead, `Params.create_tabs()` does this work dynamically:

1. `get_nodes_by_class()` groups the current selection by embroidery class.
2. For each class, `cls.get_params()` reads parameter declarations from the class's `@param`-decorated properties.
3. `get_values()` reads the current parameter values from all selected nodes of that class.
4. `group_params()` organizes parameters by their declared `group` and `sort_index`.
5. `ParamsTab` instances are created from the resulting metadata.

The key takeaway is that the dialog is mostly metadata-driven. The code is mostly assembling generic widgets from `Param` objects, not hand-authoring every field.

### How tabs are grouped and displayed

`Params.create_tabs()` uses the parameter `group` value to decide notebook tabs:

- parameters without a `group` go into the main tab for that embroidery class
- parameters with a `group` become additional tabs

Those extra tabs are treated as dependent tabs. This is how sections such as underlay settings appear as their own notebook pages while still belonging to the main embroidery object.

Examples:

- In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `fill_underlay` is declared as a `toggle` in the `Fill Underlay` group, so the UI gets a separate underlay tab.
- In [lib/elements/satin_column.py](../lib/elements/satin_column.py), `contour_underlay` and `center_walk_underlay` similarly create grouped underlay tabs for satin settings.

`sort_tabs()` in [lib/extensions/params.py](../lib/extensions/params.py) also tries to keep enabled tabs and dependent tabs together, which makes the UI feel more coherent when an object has several related groups.

### How controls are chosen from parameter definitions

The widget factory logic is in `ParamsTab.__do_layout()` in [lib/extensions/params.py](../lib/extensions/params.py).

It chooses controls by inspecting each parameter's metadata:

- `type='boolean'` becomes a checkbox
- `type='dropdown'` becomes a `wx.Choice`
- `type='combo'` becomes a bitmap combo box, usually backed by `ParamOption` objects
- a parameter with multiple different current values across the selection becomes an editable combo box so the user can pick or type a value
- a normal scalar value becomes a text box
- `type='random_seed'` gets a text field plus a dedicated re-roll button

The UI also shows:

- the parameter description as a label
- the tooltip as hover help
- the unit as a trailing label such as `mm`, `%`, or `deg`
- a change indicator button that marks a setting for saving

### How toggles work

If a tab contains a parameter with `type='toggle'`, `ParamsTab` treats that parameter specially:

- it is pulled out of the normal field list
- it becomes a checkbox at the top of the tab
- the remaining controls in that tab are enabled or disabled based on the toggle state

This is the pattern used for settings such as underlay sections. It is why those tabs feel like optional feature blocks rather than just loose collections of fields.

### How paired tabs and dependencies work

The dialog supports two important relationships beyond simple grouping.

#### Dependent tabs

If a parent tab is disabled, its dependent tabs are disabled too. This keeps related settings from becoming active when the primary feature is turned off.

#### Paired tabs

`pair_tabs()` in [lib/extensions/params.py](../lib/extensions/params.py) detects toggles marked with `inverse=True` and pairs them with their non-inverse counterpart.

The main example is the `satin_column` toggle:

- [lib/elements/stroke.py](../lib/elements/stroke.py) declares `satin_column` as `type="toggle", inverse=True` with the label `Running stitch along paths`
- [lib/elements/satin_column.py](../lib/elements/satin_column.py) declares the same logical parameter as a normal `toggle` with the label `Custom satin column`

The result is a mutually exclusive UI relationship: enabling the satin interpretation disables the running-stitch interpretation, and vice versa.

### How multiple selected objects are handled

The params dialog is designed for batch editing.

If several selected objects have different values for a parameter:

- booleans can become three-state checkboxes
- text-like values can become dropdown-capable combo boxes
- the summary text at the top of the tab explains that objects had different values

This is why the dialog can safely edit a mixed selection without pretending all objects already agree.

### How changes are reflected back into SVG-backed settings

This is one of the most important behavioral details in the whole UI.

When a field changes:

1. `ParamsTab.changed()` records which input changed.
2. `param_changed()` marks the field as needing to be saved.
3. `apply()` writes the current changed values back to the backing element nodes with `set_param()`.
4. the `on_change` hook triggers `SettingsPanel.update_preview()`.
5. the preview is regenerated from the updated SVG-backed state.

So the dialog is not editing a separate temporary data model. It writes changes into the in-memory SVG element parameters and then re-runs the normal embroidery pipeline.

That does **not** mean the file is immediately committed to disk. If the user cancels, Ink/Stitch exits without outputting the modified SVG. But for preview purposes, the dialog is already working against updated element settings.

### The live preview loop

The preview pipeline inside `SettingsPanel` is:

1. stop and clear the simulator
2. ask `PreviewRenderer` from [lib/gui/simulator/simulator_renderer.py](../lib/gui/simulator/simulator_renderer.py) to regenerate the preview in a background thread
3. call `SettingsPanel.render_stitch_plan()` to re-run embroidery on the current elements
4. convert stitch groups into a `StitchPlan`
5. send that `StitchPlan` back to the simulator

`PreviewRenderer` matters because stitch generation can be expensive. It lets the dialog stay responsive while a preview is recalculated.

The render loop is also cancellable. `PreviewRenderer.update()` sets a stop flag, and `SettingsPanel.render_stitch_plan()` calls `check_stop_flag()` between elements. That prevents stale preview work from continuing after the user changes another setting.

## 3. From `@param` declarations to concrete controls

This is the most important architectural connection in the UI subsystem.

The `@param` system is **not only storage metadata**. It is also a UI-generation mechanism.

The storage-focused side is explained in [05-parameters-metadata-and-document-upgrades.md](05-parameters-metadata-and-document-upgrades.md). The UI-focused side works like this:

1. a property on an embroidery element is decorated with `@param(...)`
2. [lib/elements/element.py](../lib/elements/element.py) stores that metadata in a `Param` object
3. `EmbroideryElement.get_params()` discovers all decorated properties on the class
4. [lib/extensions/params.py](../lib/extensions/params.py) reads the `Param` objects and current values
5. `ParamsTab` turns those `Param` objects into actual wxPython controls
6. the user's edits are saved back as Ink/Stitch SVG attributes
7. the normal embroidery code reads those values again through typed helpers such as `get_float_param()` or `get_boolean_param()`

### Example: a parameter definition turning into a concrete control

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `fill_method` is declared roughly like this:

- name: `fill_method`
- description: `Fill method`
- type: `combo`
- options: `_fill_methods`

That one declaration supplies all of the following:

- the SVG parameter key that stores the chosen method
- the human-readable label shown in the dialog
- the fact that the dialog should build a combo-style widget
- the option list shown to the user
- the default value if nothing is stored yet

`ParamsTab.__do_layout()` sees `type='combo'` and builds a bitmap combo box. The algorithm code later reads the chosen option via `self.get_param('fill_method', 'auto_fill')`.

That is a good example of why the parameter metadata matters architecturally: one declaration drives storage, UI, and runtime behavior.

### Example: conditional UI driven by parameter metadata

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `guided_fill_strategy` is declared with:

- `type='dropdown'`
- `select_items=[('fill_method', 'guided_fill')]`

That means the control should only appear when the `fill_method` selector is currently set to `guided_fill`.

`ParamsTab` implements this through `choice_widgets` and `update_choice_widgets()`. When the parent choice changes, the UI hides controls that belong to the old choice and shows the ones that belong to the new choice.

This is metadata-driven conditional UI, not a hard-coded `if` statement for that one field.

### Example: enabled/disabled dependent controls

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `enable_random_stitch_length` declares:

- `type='boolean'`
- `enables=['random_stitch_length_jitter_percent']`

That does not hide the jitter control. Instead, `update_enable_widgets()` in [lib/extensions/params.py](../lib/extensions/params.py) enables or disables it when the checkbox changes.

This gives Ink/Stitch two different kinds of dependency behavior:

- `select_items` for show/hide behavior
- `enables` for enable/disable behavior

### Example: grouping metadata creates tabs

In [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py), `fill_underlay` and its related parameters use `group=_('Fill Underlay')`.

That single grouping choice causes the params dialog to create a dedicated underlay tab instead of mixing those fields into the main fill tab.

### Example: separation between UI and core embroidery logic

Consider `row_spacing_mm` on a fill object.

- The UI side only knows it should show a field labeled `Spacing between rows` with a unit of `mm`.
- The core logic in the fill code decides what row spacing actually means for routing and stitch generation.

If you changed the fill algorithm, you would usually edit [lib/elements/fill_stitch.py](../lib/elements/fill_stitch.py) and lower-level stitch modules, not the UI widget construction code.

That separation is intentional and important.

## 4. Preview rendering and simulation

Ink/Stitch has two closely related but distinct preview concepts:

1. an interactive simulator that plays through a `StitchPlan`
2. rendered SVG previews that turn a `StitchPlan` into visible SVG content

These share data, but they are not the same implementation.

### First distinction: there are two different `render_stitch_plan` concepts

This is a frequent source of confusion.

- `SettingsPanel.render_stitch_plan()` in [lib/extensions/params.py](../lib/extensions/params.py) computes a **`StitchPlan` object** for live preview.
- `render_stitch_plan()` in [lib/svg/rendering.py](../lib/svg/rendering.py) converts a **`StitchPlan` into SVG geometry**.

The same name is used for two related stages, so be careful when reading the code.

### How the simulator gets its data

The live params dialog computes preview data like this:

1. selected nodes are converted into embroidery elements with `nodes_to_elements()`
2. each element is copied and asked to `embroider(...)`
3. the resulting stitch groups are passed to `stitch_groups_to_stitch_plan(...)`
4. document metadata such as `collapse_len_mm` and `min_stitch_len_mm` is applied during that conversion
5. the finished `StitchPlan` is handed to the simulator

That means the simulator is showing the same kind of data that later export and preview features use. It is not inventing its own interpretation of the design.

### What the simulator UI does

The simulator subsystem lives in [lib/gui/simulator/](../lib/gui/simulator/).

The main pieces are:

- [lib/gui/simulator/split_simulator_window.py](../lib/gui/simulator/split_simulator_window.py): window that places settings and simulator side by side
- [lib/gui/simulator/simulator_panel.py](../lib/gui/simulator/simulator_panel.py): container panel that wires the subpanels together
- [lib/gui/simulator/drawing_panel.py](../lib/gui/simulator/drawing_panel.py): actual stitch rendering and animation
- [lib/gui/simulator/control_panel.py](../lib/gui/simulator/control_panel.py): playback buttons, speed, stitch navigation, command navigation, slider
- [lib/gui/simulator/view_panel.py](../lib/gui/simulator/view_panel.py): toggles for needle penetration points, jumps, trims, stops, color changes, page visibility, crosshair, settings, and info dialogs
- [lib/gui/simulator/simulator_slider.py](../lib/gui/simulator/simulator_slider.py): custom slider that overlays color sections and command markers

The simulator UI is therefore not a single widget. It is a fairly rich viewer built around a `StitchPlan`.

### What the simulator renders

`DrawingPanel` in [lib/gui/simulator/drawing_panel.py](../lib/gui/simulator/drawing_panel.py) renders:

- stitch lines grouped by color block
- optional jump-stitch display
- optional needle penetration points
- an optional crosshair at the current stitch location
- a page rectangle and desk background when page display is enabled
- a scale bar

The control panel and slider also expose command-level structure such as:

- trims
- stops
- jumps
- color changes

So the simulator is not just “play stitched lines forward.” It is an interactive inspection tool for sew order and machine events.

### A concrete example of simulator data flow

Suppose the user changes a fill method from `Auto Fill` to `Guided Fill`.

The flow is:

1. the params dialog writes the new `fill_method` into the backing element parameter
2. `PreviewRenderer` asks the normal embroidery pipeline to regenerate stitch groups
3. those stitch groups become a new `StitchPlan`
4. `SimulatorPanel.load()` passes the plan into `DrawingPanel` and `ControlPanel`
5. the simulator updates its color sections, stitch counts, markers, and playback view

The simulator did not decide what `Guided Fill` means. It merely displayed the new plan produced by the core logic.

### Path preview versus realistic stitch preview

[lib/svg/rendering.py](../lib/svg/rendering.py) is the code that turns a `StitchPlan` into visible SVG output.

It supports two different visual styles.

#### Simple path preview

With `realistic=False`, `render_stitch_plan()` calls `color_block_to_paths()`.

That creates ordinary SVG paths for each color block, which is useful for:

- fast previews
- stitch-plan preview layers
- PDF and PNG generation when you want a cleaner diagram-like look

This is a schematic view of embroidery data.

#### Realistic stitch preview

With `realistic=True`, `render_stitch_plan()` calls `color_block_to_realistic_stitches()`.

That mode creates stitch-shaped path elements and applies a filter generated by `generate_realistic_filter()`. It is slower and more decorative, but it looks more like thread.

This distinction matters because “preview” can mean either:

- a structurally useful stitch-path view
- a visually realistic stitched-thread view

### How commands and warnings appear in preview tooling

Preview tooling can also surface non-stitch events.

In [lib/svg/rendering.py](../lib/svg/rendering.py), `color_block_to_paths()` can add visual trim and stop commands when `visual_commands=True`. If command symbols are not requested, it can still write command-related Ink/Stitch attributes on the generated path preview objects.

In the simulator UI:

- `SimulatorSlider` marks trims, stops, jumps, and color changes
- `ViewPanel` lets the user toggle which markers are visible
- `DesignInfoDialog` in [lib/gui/simulator/design_info.py](../lib/gui/simulator/design_info.py) shows counts for stitches, jumps, trims, stops, and color changes

And in the params dialog specifically, `WarningPanel` from [lib/gui/warnings.py](../lib/gui/warnings.py) is shown when preview generation raises an `InkstitchException` or another rendering-time error. That warning panel is about *preview generation failures*, not about every possible embroidery warning in the system.

### The simulator is a view, not the source of truth

This point is worth stating explicitly.

The simulator window, drawing panel, and preview layer are all **views over embroidery data**.

They are not the source of truth for:

- parameter values
- document storage
- stitch algorithms

The source of truth remains the SVG-backed settings and the core code that turns those settings into stitch groups and stitch plans.

## 5. Warnings, inspection, and troubleshooting tools

Ink/Stitch has several user-facing helper interfaces besides the main params dialog.

Some are wxPython dialogs. Some are SVG-output tools. Together they make the system easier to inspect and debug without moving core logic into the UI layer.

### Warning panel in the params dialog

[lib/gui/warnings.py](../lib/gui/warnings.py) defines `WarningPanel`, which is embedded by `SettingsPanel` in [lib/extensions/params.py](../lib/extensions/params.py).

Its role is narrow and important:

- if live preview generation fails, the panel displays the error text
- if preview generation succeeds, the panel is hidden again

This gives users immediate feedback when a parameter change leads to a preview-generation problem.

### Troubleshoot extension

The broader troubleshooting interface lives in [lib/extensions/troubleshoot.py](../lib/extensions/troubleshoot.py).

This is not a typical popup dialog. Instead, it creates a dedicated troubleshooting layer in the SVG and inserts pointers and descriptions for validation problems.

That tool works by:

- asking elements for validation errors and warnings
- inserting markers at problem locations
- grouping those markers into a structured troubleshooting layer

Architecturally, that makes sense: the validation logic stays with the elements, while the troubleshooting tool decides how to present it to the user.

### Element info / inspection UI

[lib/extensions/element_info.py](../lib/extensions/element_info.py) and [lib/gui/element_info.py](../lib/gui/element_info.py) form another useful inspection tool.

This extension computes real stitch groups and a `StitchPlan` for selected elements, then shows metrics such as:

- design dimensions
- stitch count
- jumps
- min and max stitch length
- method names for fill, stroke, or satin behavior

This is a good example of inspection-oriented UI: it does not change the embroidery model, but it helps the user understand what the model currently produces.

### Simple message and confirmation dialogs

[lib/gui/abort_message.py](../lib/gui/abort_message.py) and [lib/gui/dialogs.py](../lib/gui/dialogs.py) provide small helper interfaces for cases where the program needs to:

- explain why an operation cannot continue
- point the user to documentation
- ask for simple confirmation

These are intentionally thin convenience layers, not the place where embroidery behavior is decided.

### Version and migration prompts

[lib/gui/request_update_svg_version.py](../lib/gui/request_update_svg_version.py) is another small but important helper interface.

When [lib/update.py](../lib/update.py) detects an unversioned or outdated Ink/Stitch document, it can ask the user whether to update it.

That prompt is a good reminder that user-facing tooling in Ink/Stitch includes not just parameter editing, but also compatibility and document-health workflows.

## 6. Presets and user-facing convenience layers

Not all UI in Ink/Stitch is about editing core parameters directly. Some of it exists to make repeated work easier.

### Presets

The presets UI lives in [lib/gui/presets.py](../lib/gui/presets.py).

`PresetsPanel` is intentionally generic. It expects its parent to provide methods such as:

- `get_preset_data()`
- `apply_preset_data()`
- optionally `get_preset_suite_name()`

In the params dialog, `SettingsPanel` implements those hooks.

That means presets are layered on top of the normal UI rather than replacing it:

- the current UI state is serialized as preset data
- loading a preset pushes values back into the UI controls
- the preview is then regenerated from those values

Presets are stored as JSON files in the user directory, not in the embroidery algorithms.

Two details are especially useful to know:

- hidden preset names wrapped like `__NAME__` are reserved for internal use
- the params dialog stores `__LAST__`, which powers the `Use Last Settings` button

### Simulator preferences and remembered UI state

Some convenience behavior is backed by global settings rather than per-document embroidery parameters.

For example, [lib/gui/simulator/simulator_preferences.py](../lib/gui/simulator/simulator_preferences.py) edits values from [lib/utils/settings.py](../lib/utils/settings.py), including:

- adaptive simulator speed
- line width for the simulator drawing
- needle penetration point size
- whether the simulator should pop out into a separate window
- remembered toggle states such as whether jumps or page outlines are shown

These are convenience settings for the UI environment. They are different from the per-element embroidery parameters stored in SVG.

### Detachable simulator and info dialogs

The simulator subsystem also includes convenience features that make the same data easier to inspect:

- `SplitSimulatorWindow` can detach the simulator into its own window
- `DesignInfoDialog` shows high-level counts and dimensions
- `SimulatorPreferenceDialog` adjusts visualization preferences

These are usability features built around the same underlying `StitchPlan` data.

## 7. Practical advice for contributors editing the UI

If you are changing user-facing behavior, the main question is whether your change is already expressible through parameter metadata or whether it needs hand-written UI code.

### When adding a new parameter, where should you start?

Usually start with the embroidery element class, not with the dialog.

Typical steps are:

1. add or update the property on the relevant element class in [lib/elements/](../lib/elements/)
2. decorate it with `@param(...)`
3. choose the right metadata: `type`, `default`, `group`, `sort_index`, `unit`, `options`, `select_items`, `enables`, and tooltip
4. make sure the runtime code actually reads and uses the parameter
5. only then check whether the autogenerated UI behaves the way you want

If you use an existing parameter type and the desired behavior is covered by existing metadata, the params dialog often needs **no custom UI code at all**.

### What UI behavior is automatic?

The following behavior is largely automatic once the metadata is correct:

- basic field creation
- units and labels
- tab grouping by `group`
- sort order by `sort_index`
- show/hide logic through `select_items`
- enable/disable logic through `enables`
- top-level tab toggles via `type='toggle'`
- paired inverse toggles such as stroke versus satin interpretation
- preset load/save participation

This is why it is usually a mistake to add special-case widget code before checking whether the metadata system already supports the behavior.

### What kinds of changes usually require hand-written UI work?

You usually need manual UI changes when you are introducing something like:

- a brand-new widget type that `ParamsTab.__do_layout()` does not know how to build
- a custom visualization or simulator feature
- a new helper dialog or workflow outside the params dialog
- preset behavior that cannot be expressed as normal parameter state
- a new preview/export mode in [lib/svg/rendering.py](../lib/svg/rendering.py) or in a preview/export extension

### What kinds of changes require both model-level and UI-level thinking?

Many changes touch both layers, even when the UI is autogenerated.

Examples:

- renaming a parameter affects storage, runtime behavior, autogenerated UI, and possibly upgrade logic
- changing a parameter from a free text field to an enumerated set affects both the algorithm expectations and the widget type
- changing defaults can affect the UI, preview results, document migrations, and old files
- adding a new fill or satin method may need a new `ParamOption`, new algorithm logic, and new conditional UI sections

So when you change a setting, think in four questions:

1. How is it stored?
2. How is it shown?
3. How is it used by stitch generation?
4. Does an old document need migration logic?

### Where to look for common tasks

If you want to...

- **add a new editable setting**: start in the relevant file under [lib/elements/](../lib/elements/) and then inspect [lib/extensions/params.py](../lib/extensions/params.py)
- **change tab structure or widget behavior**: inspect [lib/extensions/params.py](../lib/extensions/params.py)
- **change preset behavior**: inspect [lib/gui/presets.py](../lib/gui/presets.py)
- **change simulator playback or markers**: inspect [lib/gui/simulator/control_panel.py](../lib/gui/simulator/control_panel.py), [lib/gui/simulator/view_panel.py](../lib/gui/simulator/view_panel.py), and [lib/gui/simulator/drawing_panel.py](../lib/gui/simulator/drawing_panel.py)
- **change SVG preview output**: inspect [lib/svg/rendering.py](../lib/svg/rendering.py) and preview/export extensions such as [lib/extensions/stitch_plan_preview.py](../lib/extensions/stitch_plan_preview.py)
- **change troubleshooting or inspection interfaces**: inspect [lib/extensions/troubleshoot.py](../lib/extensions/troubleshoot.py), [lib/extensions/element_info.py](../lib/extensions/element_info.py), and the corresponding files in [lib/gui/](../lib/gui/)

### Common confusion points, explicitly clarified

- Much of the params UI is metadata-driven. It is **not** hand-authored field-by-field.
- The UI is **not** where the core stitch algorithms live.
- Changing a parameter often requires both model-level and UI-level thinking, even if the widget is autogenerated.
- Simulator and preview tools are **views over embroidery data**, not the source of truth.

### A final rule of thumb

If a UI change feels like it is forcing business logic into wxPython code, stop and check whether that logic belongs instead in:

- an element property
- parameter metadata
- stitch-generation code
- validation code
- document upgrade logic

The best UI changes in Ink/Stitch usually make the metadata-driven path stronger, not weaker.
