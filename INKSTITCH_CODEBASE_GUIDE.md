# Ink/Stitch Codebase Guide — Document Generation Specification

This file is not the final overview guide.

It is a content-generation specification for another agent/LLM that will later write the real overview document.

The future generated document should be the first document a new contributor reads. It must orient a technical reader who knows programming and software architecture, may know C#, but does not know embroidery, digitizing, SVG internals, Inkscape’s extension model, or Ink/Stitch’s terminology.

---

## Primary goal

The final document generated from this specification must give the reader a stable mental model of the entire system before they dive into subsystem-specific docs.

By the end of the overview, the reader should understand:

1. what machine embroidery software fundamentally does
2. why embroidery is not equivalent to drawing or normal vector export
3. how Ink/Stitch uses SVG as an authoring model
4. how Ink/Stitch fits into Inkscape’s extension system
5. the major architectural layers in the repository
6. the core abstractions that connect those layers
7. the end-to-end data flow from SVG to stitches to exported machine file
8. which files and follow-up docs to read next

---

## Audience and assumptions that must be explicit

The generated overview must explicitly say that it is written for a reader who:

- is technically strong
- can read source code comfortably
- understands general concepts like ASTs, scene graphs, IRs, pipelines, and serialization
- is new to embroidery and digitizing
- is new to Inkscape’s Python extension system
- is new to Ink/Stitch’s codebase and vocabulary

The document must not assume prior knowledge of:

- satin columns
- underlay
- jump stitches
- trims and stops
- Inkscape `.inx` manifests
- `inkex`
- SVG `viewBox`, transforms, or namespaces
- how one SVG node can map to multiple semantic embroidery objects

Any such term must be defined before it is relied on.

---

## Core framing that must be established early

The generated overview must explicitly establish all of the following mental models:

### 1. Ink/Stitch as a transformation pipeline
Explain that Ink/Stitch transforms:

- SVG document structure
- SVG geometry
- visual styling
- Ink/Stitch-specific per-element settings
- document-level metadata
- user intent embedded in command symbols and settings

into:

- embroidery semantics
- stitch sequences
- machine commands
- exportable embroidery files

### 2. Embroidery as constrained manufacturing
Explain that embroidery output is determined by machine and fabric constraints, not just visual geometry. The document must mention at least:

- stitch length constraints
- density and spacing
- thread travel
- fabric distortion
- pull compensation
- routing and order effects

### 3. SVG as authoring representation, not machine representation
Explain that SVG describes what something looks like, but embroidery software must decide how it will be sewn.

### 4. Abstraction ladder
The future overview must clearly present this ladder and use it consistently:

- SVG node
- semantic embroidery object (`EmbroideryElement` and subclasses)
- `StitchGroup`
- `ColorBlock`
- `StitchPlan`
- machine file output

---

## Required major sections in the future overview

The generated document must contain clearly separated sections covering all of the following.

### A. What machine embroidery is
Must explain:

- that an embroidery machine runs a sequence of commands
- that a design is not just an image
- the difference between a stitch and machine-control commands

### B. Essential embroidery vocabulary
Must define, at minimum:

- stitch
- running stitch
- bean stitch
- zigzag stitch
- satin stitch / satin column
- fill stitch
- underlay
- tie-in / tie-off / lock stitch
- jump stitch
- trim
- stop
- color change
- color block
- digitizing

### C. Essential SVG and Inkscape background
Must explain, at minimum:

- SVG DOM structure
- paths and basic shape elements
- fill vs stroke
- groups and layers
- transforms
- units and pixels-per-mm
- `viewBox`
- namespaces
- clones / `<use>`
- clip paths and masks at a high level

### D. Ink/Stitch codebase architecture
Must explain the responsibilities of the major layers:

- entrypoint and extension dispatch
- extension classes
- element layer
- algorithm layer
- stitch-plan layer
- output layer
- import/rendering layer

### E. Main abstractions and how they relate
Must explain:

- `EmbroideryElement`
- `Stitch`
- `StitchGroup`
- `ColorBlock`
- `StitchPlan`

### F. One end-to-end walkthrough
Must narrate a concrete example of a simple SVG object being turned into embroidery output.

### G. Reading order and next steps
Must recommend which files and which follow-up docs to read next.

---

## Required code references

The generated overview must explicitly reference and explain the role of these files or directories:

- [inkstitch.py](inkstitch.py)
- [lib/extensions/__init__.py](lib/extensions/__init__.py)
- [lib/extensions/base.py](lib/extensions/base.py)
- [lib/elements/utils/nodes.py](lib/elements/utils/nodes.py)
- [lib/elements/element.py](lib/elements/element.py)
- [lib/elements/stroke.py](lib/elements/stroke.py)
- [lib/elements/fill_stitch.py](lib/elements/fill_stitch.py)
- [lib/elements/satin_column.py](lib/elements/satin_column.py)
- [lib/stitch_plan/stitch.py](lib/stitch_plan/stitch.py)
- [lib/stitch_plan/stitch_group.py](lib/stitch_plan/stitch_group.py)
- [lib/stitch_plan/color_block.py](lib/stitch_plan/color_block.py)
- [lib/stitch_plan/stitch_plan.py](lib/stitch_plan/stitch_plan.py)
- [lib/output.py](lib/output.py)
- [lib/svg/tags.py](lib/svg/tags.py)
- [lib/svg/units.py](lib/svg/units.py)

The final overview must not merely list them. It must explain why each one matters and how the reader should think about it.

---

## Required explanatory techniques

The generated overview must:

- use C#-friendly analogies where helpful
- explicitly note where those analogies stop being accurate
- explain not only what each layer does, but why the separation exists
- include at least one pipeline diagram or equivalent structured flow explanation
- include an explicit “common misconceptions” section

The misconceptions section must include at least:

- SVG path does not equal final stitch path
- fill/stroke are not merely cosmetic in Ink/Stitch
- export is not just dumb file serialization
- commands are not just booleans; they are represented in document structure

---

## Things the overview must acknowledge but not fully deep-dive

The overview should briefly point toward, but not exhaustively cover:

- the exact Inkscape runtime contract for effect/input/output extensions
- detailed geometry and transform handling
- the parameter and metadata system
- document upgrades and backward compatibility
- stitch generation algorithms in depth
- stitch plan and file-format details in depth
- UI, simulator, and interactive tooling internals
- advanced subsystems such as commands, markers, patterns, lettering, tartan, and sew stack
- tests and contributor workflow

It should point readers to the numbered docs in [docs/](docs/).

---

## Style requirements for the future generated document

The final overview must:

- prefer clarity over brevity
- define domain terms before building on them
- use concrete examples often
- avoid hand-waving over crucial transitions
- be suitable for a technically serious reader
- read like an engineering orientation guide, not marketing copy

---

## What the future document must avoid

The generated overview must avoid:

- turning into a raw file inventory
- becoming embroidery-only without enough code architecture
- becoming code-only without enough domain explanation
- assuming the reader can infer domain concepts from filenames alone
- diving too deeply into advanced features before establishing the core pipeline

---

## Definition of done

The future overview is only good enough if, after reading it, a new contributor can explain:

1. what Ink/Stitch fundamentally does
2. why embroidery software needs geometric and manufacturing logic
3. how SVG nodes become semantic embroidery objects
4. how stitch groups and stitch plans differ
5. how the codebase is organized at a high level
6. which source files and follow-up docs they should read next
