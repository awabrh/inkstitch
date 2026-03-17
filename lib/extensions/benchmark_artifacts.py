# Authors: see git history
#
# Copyright (c) 2026 Authors
# Licensed under the GNU GPL version 3.0 or later.  See the file LICENSE for details.

import json
import os
import sys
import tempfile
from copy import deepcopy
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import inkex
from inkex import Boolean
from lxml import etree

from ..output import write_embroidery_file
from ..stitch_plan import stitch_groups_to_stitch_plan
from ..svg import PIXELS_PER_MM, render_stitch_plan
from ..threads import ThreadCatalog
from .base import InkstitchExtension


class BenchmarkArtifacts(InkstitchExtension):
    DEVELOPMENT_ONLY = True

    def __init__(self, *args, **kwargs):
        InkstitchExtension.__init__(self, *args, **kwargs)

        self.arg_parser.add_argument('--notebook')
        self.arg_parser.add_argument('--custom-file-name', type=str, default='', dest='custom_file_name')
        self.arg_parser.add_argument('--float-precision', type=int, default=4, dest='float_precision')
        self.arg_parser.add_argument('--include-source-svg', type=Boolean, default=True, dest='include_source_svg')
        self.arg_parser.add_argument('--include-preview-svg', type=Boolean, default=True, dest='include_preview_svg')
        self.arg_parser.add_argument('--include-validation-json', type=Boolean, default=True, dest='include_validation_json')
        self.arg_parser.add_argument('--include-trace-csv', type=Boolean, default=False, dest='include_trace_csv')

    def effect(self):
        if not self.get_elements():
            return

        self.metadata = self.get_inkstitch_metadata()
        collapse_len = self.metadata['collapse_len_mm']
        min_stitch_len = self.metadata['min_stitch_len_mm']
        stitch_groups = self.elements_to_stitch_groups(self.elements)
        stitch_plan = stitch_groups_to_stitch_plan(
            stitch_groups,
            collapse_len=collapse_len,
            min_stitch_len=min_stitch_len
        )
        ThreadCatalog().match_and_apply_palette(stitch_plan, self.metadata['thread-palette'])

        base_file_name = self._get_file_name()
        artifact_files = self.generate_artifact_files(stitch_plan, base_file_name)

        temp_file = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        temp_file.close()

        with ZipFile(temp_file.name, "w") as zip_file:
            for artifact_name, contents in sorted(artifact_files.items()):
                info = ZipInfo(artifact_name)
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = ZIP_DEFLATED
                zip_file.writestr(info, contents)

        with open(temp_file.name, 'rb') as output_file:
            sys.stdout.buffer.write(output_file.read())

        os.remove(temp_file.name)

        # don't let inkex output the SVG!
        sys.exit(0)

    def _get_file_name(self):
        if self.options.custom_file_name:
            return self.options.custom_file_name
        return self.get_base_file_name()

    def generate_artifact_files(self, stitch_plan, base_file_name):
        artifact_files = {
            f"{base_file_name}.metadata.json": self._json_artifact(self._build_metadata_summary()),
            f"{base_file_name}.stats.json": self._json_artifact(self._build_stats(stitch_plan)),
            f"{base_file_name}.stitch_plan.json": self._json_artifact(stitch_plan),
            f"{base_file_name}.threads.json": self._json_artifact(self._build_thread_summary(stitch_plan)),
        }

        if self.options.include_source_svg:
            artifact_files[f"{base_file_name}.source.svg"] = self._serialize_svg(self.document.getroot())

        if self.options.include_preview_svg:
            artifact_files[f"{base_file_name}.preview.svg"] = self._build_preview_svg(stitch_plan)

        if self.options.include_validation_json:
            artifact_files[f"{base_file_name}.validation.json"] = self._json_artifact(self._build_validation_summary())

        if self.options.include_trace_csv:
            artifact_files[f"{base_file_name}.trace.csv"] = self._build_trace_csv(stitch_plan)

        manifest_name = f"{base_file_name}.manifest.json"
        artifact_files[manifest_name] = self._json_artifact(
            self._build_manifest(base_file_name, sorted([*artifact_files.keys(), manifest_name]))
        )

        return artifact_files

    def _build_manifest(self, base_file_name, artifact_names):
        return {
            "base_file_name": base_file_name,
            "document_name": self.document.getroot().get(inkex.addNS('docname', 'sodipodi'), "embroidery.svg"),
            "selection_ids": [node.get_id() for node in self.svg.selection] if self.svg.selection else [],
            "artifact_files": artifact_names,
            "options": {
                "float_precision": self.options.float_precision,
                "include_source_svg": self.options.include_source_svg,
                "include_preview_svg": self.options.include_preview_svg,
                "include_trace_csv": self.options.include_trace_csv,
                "include_validation_json": self.options.include_validation_json,
            },
        }

    def _build_metadata_summary(self):
        return {
            "document_metadata": dict(self.metadata),
            "selection_ids": [node.get_id() for node in self.svg.selection] if self.svg.selection else [],
        }

    def _build_stats(self, stitch_plan):
        minx, miny, maxx, maxy = stitch_plan.bounding_box
        width_px, height_px = stitch_plan.dimensions
        width_mm, height_mm = stitch_plan.dimensions_mm

        return {
            "num_colors": stitch_plan.num_colors,
            "num_color_blocks": stitch_plan.num_color_blocks,
            "num_stops": stitch_plan.num_stops,
            "num_trims": stitch_plan.num_trims,
            "num_stitches": stitch_plan.num_stitches,
            "num_jumps": stitch_plan.num_jumps,
            "estimated_thread_m": stitch_plan.estimated_thread,
            "bounding_box": {
                "min_x": minx,
                "min_y": miny,
                "max_x": maxx,
                "max_y": maxy,
            },
            "dimensions_px": {
                "width": width_px,
                "height": height_px,
            },
            "dimensions_mm": {
                "width": width_mm,
                "height": height_mm,
            },
            "color_blocks": [
                {
                    "index": index,
                    "color": color_block.color,
                    "num_stitches": color_block.num_stitches,
                    "num_stops": color_block.num_stops,
                    "num_trims": color_block.num_trims,
                    "num_jumps": color_block.num_jumps,
                    "estimated_thread_m": round(color_block.estimated_thread / PIXELS_PER_MM / 1000, 4),
                    "bounding_box": {
                        "min_x": color_block.bounding_box[0],
                        "min_y": color_block.bounding_box[1],
                        "max_x": color_block.bounding_box[2],
                        "max_y": color_block.bounding_box[3],
                    },
                }
                for index, color_block in enumerate(stitch_plan)
            ]
        }

    def _build_thread_summary(self, stitch_plan):
        unique_threads = []
        seen_threads = set()

        for color_block in stitch_plan:
            if color_block.color not in seen_threads:
                unique_threads.append(color_block.color)
                seen_threads.add(color_block.color)

        return {
            "unique_threads": unique_threads,
            "color_blocks": [
                {
                    "index": index,
                    "thread": color_block.color,
                    "num_stitches": color_block.num_stitches,
                }
                for index, color_block in enumerate(stitch_plan)
            ]
        }

    def _build_validation_summary(self):
        elements = []
        total_errors = 0
        total_warnings = 0

        for index, element in enumerate(self.elements):
            errors = [self._serialize_validation_message(message) for message in element.validation_errors()]
            warnings = [self._serialize_validation_message(message) for message in element.validation_warnings()]

            total_errors += len(errors)
            total_warnings += len(warnings)

            elements.append({
                "index": index,
                "id": element.node.get_id(),
                "label": element.node.label,
                "type": element.element_name,
                "class_name": element.__class__.__name__,
                "errors": errors,
                "warnings": warnings,
            })

        return {
            "error_count": total_errors,
            "warning_count": total_warnings,
            "elements": elements,
        }

    def _serialize_validation_message(self, message):
        return {
            "type": type(message).__name__,
            "name": message.name,
            "description": message.description,
            "label": message.label,
            "position": {
                "x": message.position.x,
                "y": message.position.y,
            },
            "steps_to_solve": list(message.steps_to_solve),
        }

    def _build_preview_svg(self, stitch_plan):
        svg = deepcopy(self.document).getroot()
        render_stitch_plan(svg, stitch_plan, realistic=False, visual_commands=False, render_jumps=False)

        stitch_plan_layer = svg.findone(".//*[@id='__inkstitch_stitch_plan__']")
        if stitch_plan_layer is not None:
            stitch_plan_layer.attrib.pop('transform', None)

        svg.set('style', 'overflow:visible;')

        layers_and_groups = svg.xpath("./g|./path|./circle|./ellipse|./rect|./text")
        for layer in layers_and_groups:
            if layer is not stitch_plan_layer:
                layer.delete()

        return self._serialize_svg(svg)

    def _build_trace_csv(self, stitch_plan):
        with tempfile.TemporaryDirectory() as tempdir:
            output_file = os.path.join(tempdir, "trace.csv")
            write_embroidery_file(output_file, stitch_plan, self.document.getroot(), settings={"date": ""})

            with open(output_file, 'rb') as csv_file:
                return csv_file.read()

    def _serialize_svg(self, svg):
        return etree.tostring(svg, encoding='utf-8', xml_declaration=True)

    def _json_artifact(self, data):
        serialized = self._canonicalize(data)
        return (json.dumps(serialized, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode('utf-8')

    def _canonicalize(self, value):
        if hasattr(value, '__json__'):
            value = value.__json__()

        if isinstance(value, dict):
            return {str(key): self._canonicalize(val) for key, val in value.items()}

        if isinstance(value, (list, tuple)):
            return [self._canonicalize(item) for item in value]

        if isinstance(value, set):
            return [self._canonicalize(item) for item in sorted(value, key=repr)]

        if isinstance(value, float):
            return round(value, self.options.float_precision)

        return value