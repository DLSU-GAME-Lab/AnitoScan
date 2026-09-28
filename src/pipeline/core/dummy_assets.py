"""Dependency-free cube fixtures for the dummy pipeline's OBJ and GLB exports."""

import json
import struct

from asset_export import export_asset
from cancellation import check_cancelled


CUBE_OBJ = """# Dummy backend cube
v -0.5 -0.5 -0.5
v 0.5 -0.5 -0.5
v 0.5 0.5 -0.5
v -0.5 0.5 -0.5
v -0.5 -0.5 0.5
v 0.5 -0.5 0.5
v 0.5 0.5 0.5
v -0.5 0.5 0.5
f 1 2 3 4
f 5 8 7 6
f 1 5 6 2
f 2 6 7 3
f 3 7 8 4
f 5 1 4 8
"""


def _write_cube_glb(source, output, textures, cancel_event):
    check_cancelled(cancel_event)
    if source.read_text(encoding="utf-8") != CUBE_OBJ or textures:
        raise ValueError("Dummy GLB export only supports the dummy cube; use the pipeline backend for real assets")

    # Both formats use the same fixture geometry; this is not a general OBJ converter.
    vertices = []
    indices = []
    for line in CUBE_OBJ.splitlines():
        fields = line.split()
        if fields[0] == "v":
            vertices.extend(float(value) for value in fields[1:])
        elif fields[0] == "f":
            face = [int(value) - 1 for value in fields[1:]]
            indices.extend((face[0], face[1], face[2], face[0], face[2], face[3]))
    positions = struct.pack(f"<{len(vertices)}f", *vertices)
    triangles = struct.pack(f"<{len(indices)}H", *indices)
    binary = positions + triangles
    document = {
        "asset": {"version": "2.0", "generator": "AnitoScan dummy backend"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "Dummy cube"}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0}, "indices": 1, "material": 0, "mode": 4,
        }]}],
        "materials": [{
            "name": "Dummy material", "doubleSided": True,
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.7, 0.7, 0.7, 1.0],
                "metallicFactor": 0.0, "roughnessFactor": 1.0,
            },
        }],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions), "byteLength": len(triangles), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(vertices) // 3,
             "type": "VEC3", "min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]},
            {"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
    }
    # GLB 2.0 requires four-byte-aligned JSON and binary chunks.
    metadata = json.dumps(document, separators=(",", ":")).encode("utf-8")
    metadata += b" " * (-len(metadata) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    total_length = 12 + 8 + len(metadata) + 8 + len(binary)
    payload = (
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<I4s", len(metadata), b"JSON") + metadata
        + struct.pack("<I4s", len(binary), b"BIN\x00") + binary
    )
    check_cancelled(cancel_event)
    output.write_bytes(payload)


def _cube_preview(output, cache, cancel_event):
    """The mock GLB and preview deliberately share the same fixed cube fixture."""
    check_cancelled(cancel_event)
    preview = cache / "preview.obj"
    with preview.open("x", encoding="utf-8") as stream:
        stream.write(CUBE_OBJ)
    return preview


def export_dummy_asset(cmd, cancel_event=None):
    return export_asset(
        cmd, cancel_event,
        glb_converter=_write_cube_glb,
        glb_previewer=_cube_preview,
    )
