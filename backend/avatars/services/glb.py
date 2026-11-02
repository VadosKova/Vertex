import json
import struct

_BOX_CORNERS = [(-1, 0, -1), (1, 0, -1), (1, 1, -1), (-1, 1, -1), (-1, 0, 1), (1, 0, 1), (1, 1, 1), (-1, 1, 1)]
_BOX_INDICES = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5, 3, 7, 6, 3, 6, 2, 0, 1, 5, 0, 5, 4]


def build_placeholder_glb(height_m: float, width_m: float, depth_m: float, extras: dict | None = None) -> bytes:
    positions = [(x * width_m / 2, y * height_m, z * depth_m / 2) for x, y, z in _BOX_CORNERS]
    pos_bin = b"".join(struct.pack("<3f", *p) for p in positions)
    idx_bin = struct.pack(f"<{len(_BOX_INDICES)}H", *_BOX_INDICES)
    binary = pos_bin + idx_bin
    binary += b"\x00" * (-len(binary) % 4)
    doc = {
        "asset": {"version": "2.0", "generator": "vertex-backend-placeholder"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "avatar", "extras": extras or {}}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3",
             "min": [min(p[i] for p in positions) for i in range(3)],
             "max": [max(p[i] for p in positions) for i in range(3)]},
            {"bufferView": 1, "componentType": 5123, "count": len(_BOX_INDICES), "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_bin), "target": 34962},
            {"buffer": 0, "byteOffset": len(pos_bin), "byteLength": len(idx_bin), "target": 34963},
        ],
        "buffers": [{"byteLength": len(binary)}],
    }
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    return (struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<I4s", len(js), b"JSON") + js
            + struct.pack("<I4s", len(binary), b"BIN\x00") + binary)