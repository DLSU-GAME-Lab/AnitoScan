"""User-directed asset export, independent of reconstruction run state."""


import importlib.util
import json

import os
from pathlib import Path, PureWindowsPath
import re
import shlex
import shutil

import tempfile

from cancellation import check_cancelled
from manifest import _save_manifest, load_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_TEXTURE_OPTIONS = {
    "-blendu": 1, "-blendv": 1, "-boost": 1, "-mm": 2,
    "-texres": 1, "-clamp": 1, "-bm": 1, "-imfchan": 1,
    "-type": 1, "-colorspace": 1, "-cc": 1,
}


def export_formats():
    return ["obj", "glb"] if importlib.util.find_spec("trimesh") is not None else ["obj"]


def validate_request(cmd):
    for field in ("request_id", "run_id", "source_model_path", "destination_directory", "asset_name"):
        if not isinstance(cmd.get(field), str) or not cmd[field].strip():
            raise ValueError(f"export_asset requires a non-empty string {field}")
    for field in ("source_model_path", "destination_directory"):
        if "\x00" in cmd[field] or not Path(cmd[field]).is_absolute():
            raise ValueError(f"{field} must be an absolute path")
    name = cmd["asset_name"]
    if (name in {".", ".."} or name.endswith((".", " ")) or _UNSAFE_NAME.search(name)
            or name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}):
        raise ValueError("asset_name must be a safe single folder name")
    if cmd.get("format", "obj") not in ("obj", "glb"):
        raise ValueError("format must be obj or glb")
    if not isinstance(cmd.get("create_destination_directory", False), bool):
        raise ValueError("create_destination_directory must be a boolean")


def _source_for_run(cmd, cancel_event):
    source = Path(cmd["source_model_path"])
    if source.suffix.lower() != ".obj" or not source.is_file():
        raise ValueError("source_model_path must name an existing OBJ file")
    source = source.resolve(strict=True)
    runs = (PROJECT_ROOT / "data" / "runs").resolve()
    matches = []
    for path in runs.rglob("manifest.json"):
        check_cancelled(cancel_event)
        if not path.resolve().is_relative_to(runs):
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(manifest, dict) and manifest.get("run_id", path.parent.name) == cmd["run_id"]:
            matches.append((path.resolve(), manifest))
    if len(matches) != 1:
        raise ValueError("run_id must match exactly one run manifest")
    manifest_path, manifest = matches[0]
    paths = manifest.get("paths")
    export = paths.get("export") if isinstance(paths, dict) else None
    if not isinstance(export, str) or not Path(export).is_absolute():
        raise ValueError("run manifest has no absolute paths.export")
    export = Path(export).resolve(strict=True)
    if (source.parent != export or source.suffix.lower() != ".obj"
            or Path(cmd["source_model_path"]).parent.resolve() != export):
        raise ValueError("source must be a direct OBJ file in the run's paths.export directory")
    return source, manifest_path


def _records(path, cancel_event):
    with path.open(encoding="utf-8-sig") as stream:
        pending = ""
        for line in stream:
            check_cancelled(cancel_event)
            line = line.rstrip()
            if line.endswith("\\"):
                pending += line[:-1] + " "
                continue
            lexer = shlex.shlex(pending + line, posix=True)
            lexer.whitespace_split = True
            # Keep Windows separators visible so they can be rejected, not silently removed.
            lexer.escape = ""
            tokens = list(lexer)
            pending = ""
            if tokens:
                yield tokens[0].lower(), tokens[1:]
        if pending:
            raise ValueError(f"Unterminated continuation in {path.name}")


def _dependency(root, parent, reference):
    relative = Path(reference)
    if (not reference or "\\" in reference or "\x00" in reference
            or relative.is_absolute() or PureWindowsPath(reference).drive):
        raise ValueError(f"Unsafe dependency path: {reference!r}")
    # Keep lexical names for copying, but validate both lexical and symlink targets.
    path = Path(os.path.abspath(parent / relative))
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
        raise ValueError(f"Dependency escapes source folder: {reference}")
    if not path.is_file():
        raise ValueError(f"Missing referenced material or texture: {reference}")
    return path


def _texture_reference(tokens):
    tokens = list(tokens)
    while tokens and tokens[0].startswith("-"):
        option = tokens.pop(0).lower()
        if option in {"-o", "-s", "-t"}:
            count = 0
            while tokens and count < 3:
                try:
                    float(tokens[0])
                except ValueError:
                    break
                tokens.pop(0)
                count += 1
            if not count:
                raise ValueError(f"Missing values for texture option {option}")
        else:
            count = _TEXTURE_OPTIONS.get(option)
            if count is None or len(tokens) < count + 1:
                raise ValueError(f"Unsupported or malformed texture option {option}")
            del tokens[:count]
    if not tokens:
        raise ValueError("Missing texture filename")
    return " ".join(tokens)


def _dependency_closure(source, cancel_event):
    root = source.parent
    files = {source}
    materials = set()
    used_materials = set()
    defined_materials = set()
    has_vertices = False
    has_faces = False
    for kind, values in _records(source, cancel_event):
        if kind == "mtllib":
            if not values:
                raise ValueError("OBJ contains an empty mtllib reference")
            for reference in values:
                materials.add(_dependency(root, root, reference))
        elif kind == "usemtl":
            if not values:
                raise ValueError("OBJ contains an empty usemtl")
            used_materials.add(" ".join(values))
        elif kind == "v":
            has_vertices = has_vertices or len(values) >= 3
        elif kind == "f":
            has_faces = has_faces or len(values) >= 3
        elif kind in {"call", "csh"}:
            raise ValueError(f"Unsupported external OBJ directive: {kind}")
    if not has_vertices or not has_faces:
        raise ValueError("OBJ contains no mesh")
    textures = set()
    for material in materials:
        for kind, values in _records(material, cancel_event):
            if kind == "newmtl":
                if not values:
                    raise ValueError("MTL contains an empty material name")
                defined_materials.add(" ".join(values))
            elif kind.startswith("map_") or kind in {"bump", "disp", "decal", "refl", "norm"}:
                textures.add(_dependency(root, material.parent, _texture_reference(values)))
    if used_materials - defined_materials:
        raise ValueError("OBJ references undefined materials: " + ", ".join(sorted(used_materials - defined_materials)))
    files.update(materials)
    files.update(textures)
    return files, textures


def _copy_file(source, destination, cancel_event):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, destination.open("xb") as writer:
        while True:
            check_cancelled(cancel_event)
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            writer.write(chunk)


def _convert_glb(source, output, textures, cancel_event):
    import trimesh
    from PIL import Image
    from trimesh.visual.material import MultiMaterial, SimpleMaterial

    # trimesh may silently ignore unreadable images; fail explicitly instead.
    for texture in textures:
        check_cancelled(cancel_event)
        with Image.open(texture) as image:
            image.verify()
    # Supply only validated local resources. OBJ loaders commonly resolve all
    # images from the OBJ root, rather than from each MTL's directory.
    resolver = {}
    diffuse_materials = set()

    def resource(reference, path):
        check_cancelled(cancel_event)
        payload = path.read_bytes()
        if reference in resolver and resolver[reference] != payload:
            raise ValueError(f"Ambiguous GLB texture reference: {reference}")
        resolver[reference] = payload

    for kind, values in _records(source, cancel_event):
        if kind != "mtllib":
            continue
        for reference in values:
            material_path = _dependency(source.parent, source.parent, reference)
            resource(reference, material_path)
            material_name = None
            for directive, arguments in _records(material_path, cancel_event):
                if directive == "newmtl":
                    material_name = " ".join(arguments)
                elif directive.startswith("map_") or directive in {"bump", "disp", "decal", "refl", "norm"}:
                    texture_reference = _texture_reference(arguments)
                    resource(texture_reference, _dependency(source.parent, material_path.parent, texture_reference))
                    if directive == "map_kd":
                        diffuse_materials.add(material_name)
    check_cancelled(cancel_event)
    scene = trimesh.load(source, file_type="obj", force="scene", process=False, resolver=resolver)
    if not scene.geometry:
        raise ValueError("OBJ contains no convertible geometry")

    def pbr(material):
        if isinstance(material, SimpleMaterial):
            if material.name in diffuse_materials and material.image is None:
                raise ValueError(f"GLB loader could not preserve the texture for material {material.name}")
            converted = material.to_pbr()
            converted.metallicFactor = 0.0
            converted.roughnessFactor = 1.0
            return converted
        if isinstance(material, MultiMaterial):
            material.materials = [pbr(item) for item in material.materials]
        return material

    for geometry in scene.geometry.values():
        check_cancelled(cancel_event)
        if hasattr(geometry.visual, "material"):
            geometry.visual.material = pbr(geometry.visual.material)
    payload = scene.export(file_type="glb", include_normals=True)
    check_cancelled(cancel_event)
    output.write_bytes(payload)


def _glb_preview(output, cache, cancel_event):
    import trimesh
    from trimesh.exchange.obj import export_obj

    check_cancelled(cancel_event)
    scene = trimesh.load(output, file_type="glb", force="scene", process=False)
    if not scene.geometry:
        raise ValueError("Exported GLB contains no preview geometry")
    obj, resources = export_obj(scene, return_texture=True)
    preview = cache / "preview.obj"
    with preview.open("x", encoding="utf-8") as stream:
        stream.write(obj)
    for name, payload in (resources or {}).items():
        check_cancelled(cancel_event)
        relative = Path(name)
        if (relative.is_absolute() or PureWindowsPath(name).drive
                or "\\" in name or "\x00" in name
                or not (cache / relative).resolve().is_relative_to(cache)):
            raise ValueError(f"Unsafe preview resource path: {name!r}")
        resource = cache / relative
        resource.parent.mkdir(parents=True, exist_ok=True)
        with resource.open("xb") as stream:
            stream.write(payload.encode("utf-8") if isinstance(payload, str) else payload)
    _dependency_closure(preview, cancel_event)
    return preview


def _publish(stage, target, cancel_event):
    """Claim a new destination and clean up only the folder this export owns."""
    target.mkdir(exist_ok=False)
    try:
        for child in stage.iterdir():
            check_cancelled(cancel_event)
            shutil.move(str(child), str(target / child.name))
        check_cancelled(cancel_event)
    except BaseException:
        shutil.rmtree(target)
        raise


def export_asset(cmd, cancel_event=None, *, glb_converter=_convert_glb, glb_previewer=_glb_preview):
    validate_request(cmd)
    check_cancelled(cancel_event)
    source, manifest_path = _source_for_run(cmd, cancel_event)
    files, textures = _dependency_closure(source, cancel_event)
    format_name = cmd.get("format", "obj")
    if format_name == "glb" and glb_converter is _convert_glb and format_name not in export_formats():
        raise ValueError("GLB export requires trimesh in the backend environment")
    destination = Path(cmd["destination_directory"])
    if cmd.get("create_destination_directory", False):
        destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise ValueError("destination_directory must exist (or set create_destination_directory to true)")
    destination = destination.resolve(strict=True)
    target = destination / cmd["asset_name"]
    if os.path.lexists(target):
        raise FileExistsError(f"Export destination already exists: {target}")
    stage = Path(tempfile.mkdtemp(prefix=".anitoscan-export-", dir=destination))
    published = False
    cache = None
    try:
        if format_name == "obj":
            for path in sorted(files):
                _copy_file(path, stage / path.relative_to(source.parent), cancel_event)
            output_name = source.name
        else:
            output_name = cmd["asset_name"] + ".glb"
            glb_converter(source, stage / output_name, textures, cancel_event)
        check_cancelled(cancel_event)
        _publish(stage, target, cancel_event)
        published = True
        output = target / output_name
        preview = output
        if format_name == "glb":
            cache = Path(tempfile.mkdtemp(prefix=".export-preview-", dir=manifest_path.parent))
            preview = glb_previewer(output, cache, cancel_event)
        record = {"path": str(output), "format": format_name, "preview_path": str(preview)}
        _, manifest = load_manifest(manifest_path)
        manifest.setdefault("exports", []).append(record)
        manifest["export_pending"] = False
        check_cancelled(cancel_event)
        _save_manifest(manifest_path, manifest)
        return record
    except BaseException:
        if published:
            shutil.rmtree(target, ignore_errors=True)
        if cache is not None:
            shutil.rmtree(cache, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
