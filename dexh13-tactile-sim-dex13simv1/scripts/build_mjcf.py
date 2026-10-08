#!/usr/bin/env python
from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


DEFAULT_SOURCE = Path("assets/dexh13_raw/dexh13_hand_right_description/mjcf_base.xml")
DEFAULT_SENSORS = Path("configs/sensors.yaml")
DEFAULT_OUT = Path("assets/dexh13_mjcf/hand.xml")
DEFAULT_SCENE = Path("assets/dexh13_mjcf/test_press_scene.xml")
DEFAULT_INTERACTIVE_SCENE = Path("assets/dexh13_mjcf/interactive_press_scene.xml")
DEFAULT_FREE_OBJECT_SCENE = Path("assets/dexh13_mjcf/free_object_scene.xml")


FINGER_NAMES = ("index", "middle", "ring")

# Finger phalanx tactile meshes own the sensor-side contact surface. Extra
# capsules on those links can block objects before tactile contact is reached.
EXTERNAL_COLLISION_PRIMITIVES = [
    {
        "body": "right_palm_link",
        "name": "right_palm_link_external_collision_geom",
        "type": "box",
        "pos": "0.075 0 0.008",
        "size": "0.055 0.052 0.014",
    },
]

for finger in FINGER_NAMES:
    EXTERNAL_COLLISION_PRIMITIVES.extend(
        [
            {
                "body": f"right_{finger}_link_0",
                "name": f"right_{finger}_link_0_external_collision_geom",
                "type": "box",
                "pos": "0.010 0 0",
                "size": "0.012 0.011 0.010",
            },
        ]
    )

EXTERNAL_COLLISION_PRIMITIVES.extend(
    [
        {
            "body": "right_thumb_link_0",
            "name": "right_thumb_link_0_external_collision_geom",
            "type": "box",
            "pos": "0.010 0 0",
            "size": "0.012 0.011 0.010",
        },
    ]
)


def ensure_child(parent: ET.Element, tag: str) -> ET.Element:
    child = parent.find(tag)
    if child is None:
        child = ET.SubElement(parent, tag)
    return child


def remove_sensor_plugins(root: ET.Element) -> None:
    for child in list(root):
        if child.tag in {"sensor", "extension"}:
            root.remove(child)


def remove_all_sites(root: ET.Element) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "site":
                parent.remove(child)


def remove_empty_sensor_frame_bodies(root: ET.Element) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "body" and child.get("name", "").endswith("_sensor_frame"):
                parent.remove(child)


def add_defaults(root: ET.Element) -> None:
    default = ensure_child(root, "default")
    tactile = ET.SubElement(default, "default", {"class": "dexh13_tactile"})
    ET.SubElement(
        tactile,
        "geom",
        {
            "friction": "1.2 0.02 0.002",
            "solref": "0.015 1",
            "solimp": "0.92 0.985 0.003",
            "condim": "4",
            "contype": "1",
            "conaffinity": "1",
        },
    )
    collision = ET.SubElement(default, "default", {"class": "dexh13_collision"})
    ET.SubElement(
        collision,
        "geom",
        {
            "friction": "0.8 0.02 0.001",
            "solref": "0.01 1",
            "solimp": "0.90 0.98 0.002",
            "condim": "4",
            "contype": "0",
            "conaffinity": "0",
        },
    )
    external_collision = ET.SubElement(default, "default", {"class": "dexh13_external_collision"})
    ET.SubElement(
        external_collision,
        "geom",
        {
            "friction": "0.9 0.02 0.001",
            "solref": "0.012 1",
            "solimp": "0.90 0.98 0.002",
            "condim": "4",
            "contype": "2",
            "conaffinity": "0",
            "group": "4",
            "rgba": "0.1 0.7 0.25 0.18",
        },
    )


def configure_compiler_and_option(root: ET.Element) -> None:
    compiler = ensure_child(root, "compiler")
    compiler.set("angle", "radian")
    compiler.set("meshdir", "../dexh13_raw/dexh13_hand_right_description/meshes")

    option = ensure_child(root, "option")
    option.set("timestep", "0.0005")
    option.set("integrator", "implicitfast")


def _remove_named_children(parent: ET.Element, tag: str, name: str) -> None:
    for child in list(parent):
        if child.tag == tag and child.get("name") == name:
            parent.remove(child)


def configure_visuals(root: ET.Element) -> None:
    visual = ensure_child(root, "visual")

    headlight = visual.find("headlight")
    if headlight is None:
        headlight = ET.SubElement(visual, "headlight")
    headlight.set("diffuse", "0.65 0.65 0.70")
    headlight.set("ambient", "0.28 0.30 0.34")
    headlight.set("specular", "0.18 0.18 0.20")

    rgba = visual.find("rgba")
    if rgba is None:
        rgba = ET.SubElement(visual, "rgba")
    rgba.set("haze", "0.58 0.70 0.84 1")

    global_view = visual.find("global")
    if global_view is None:
        global_view = ET.SubElement(visual, "global")
    global_view.set("azimuth", "120")
    global_view.set("elevation", "-20")

    asset = ensure_child(root, "asset")
    for tag, name in (
        ("texture", "skybox"),
        ("texture", "tex_floor"),
        ("material", "mat_floor"),
    ):
        _remove_named_children(asset, tag, name)

    ET.SubElement(
        asset,
        "texture",
        {
            "name": "skybox",
            "type": "skybox",
            "builtin": "gradient",
            "rgb1": "0.78 0.88 1.00",
            "rgb2": "0.34 0.46 0.62",
            "width": "512",
            "height": "512",
        },
    )
    ET.SubElement(
        asset,
        "texture",
        {
            "name": "tex_floor",
            "type": "2d",
            "builtin": "checker",
            "rgb1": "0.56 0.68 0.80",
            "rgb2": "0.38 0.50 0.66",
            "width": "512",
            "height": "512",
            "mark": "edge",
            "markrgb": "0.90 0.95 1.00",
        },
    )
    ET.SubElement(
        asset,
        "material",
        {
            "name": "mat_floor",
            "texture": "tex_floor",
            "texuniform": "true",
            "texrepeat": "6 6",
            "reflectance": "0.12",
            "rgba": "0.72 0.82 0.92 1",
        },
    )


def body_by_name(root: ET.Element) -> dict[str, ET.Element]:
    return {body.get("name", ""): body for body in root.findall(".//body")}


def configure_geoms(root: ET.Element, sensors: list[dict[str, object]]) -> None:
    tactile_by_body = {str(item["parent_body"]): str(item["parent_geom"]) for item in sensors}
    for geom in root.findall(".//geom"):
        geom_mesh = geom.get("mesh")
        if not geom_mesh:
            continue
        geom.set("name", f"{geom_mesh}_collision_geom")
        geom.set("class", "dexh13_collision")

    bodies = body_by_name(root)
    for body_name, geom_name in tactile_by_body.items():
        body = bodies[body_name]
        geoms = [child for child in body if child.tag == "geom"]
        if len(geoms) != 1:
            raise ValueError(f"{body_name} expected exactly one tactile geom, found {len(geoms)}")
        geoms[0].set("name", geom_name)
        geoms[0].set("class", "dexh13_tactile")


def add_sensor_frame_sites(root: ET.Element, sensors: list[dict[str, object]]) -> None:
    bodies = body_by_name(root)
    for item in sensors:
        body = bodies[str(item["parent_body"])]
        ET.SubElement(
            body,
            "site",
            {
                "name": str(item["site_name"]),
                "pos": "0 0 0",
                "quat": "1 0 0 0",
                "size": "0.001",
                "group": "3",
                "rgba": "0.9 0.2 0.2 0.65",
            },
        )


def insert_body_child_before_nested_bodies(body: ET.Element, child: ET.Element) -> None:
    for index, existing in enumerate(list(body)):
        if existing.tag == "body":
            body.insert(index, child)
            return
    body.append(child)


def add_external_collision_primitives(root: ET.Element) -> None:
    bodies = body_by_name(root)
    for spec in EXTERNAL_COLLISION_PRIMITIVES:
        body_name = str(spec["body"])
        if body_name not in bodies:
            raise ValueError(f"missing body for external collision primitive: {body_name}")
        attrs = {
            "name": str(spec["name"]),
            "class": "dexh13_external_collision",
            "type": str(spec["type"]),
            "size": str(spec["size"]),
        }
        if "pos" in spec:
            attrs["pos"] = str(spec["pos"])
        if "fromto" in spec:
            attrs["fromto"] = str(spec["fromto"])
        insert_body_child_before_nested_bodies(bodies[body_name], ET.Element("geom", attrs))


def add_floor(worldbody: ET.Element) -> None:
    ET.SubElement(
        worldbody,
        "geom",
        {
            "name": "floor",
            "type": "plane",
            "size": "0.5 0.5 0.01",
            "pos": "0 0 -0.05",
            "material": "mat_floor",
        },
    )


def write_press_scene(hand_xml: Path, scene_xml: Path) -> None:
    scene_xml.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("mujoco", {"model": "dexh13_press_test"})
    ET.SubElement(root, "include", {"file": hand_xml.name})
    worldbody = ET.SubElement(root, "worldbody")
    add_floor(worldbody)
    body = ET.SubElement(worldbody, "body", {"name": "press_sphere", "pos": "0.219 -0.0315 0.02"})
    ET.SubElement(body, "joint", {"name": "press_z", "type": "slide", "axis": "0 0 1", "damping": "1"})
    ET.SubElement(
        body,
        "geom",
        {
            "name": "press_sphere_geom",
            "type": "sphere",
            "size": "0.006",
            "mass": "0.02",
            "contype": "0",
            "conaffinity": "1",
        },
    )
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(scene_xml, encoding="utf-8", xml_declaration=True)


def write_interactive_press_scene(hand_xml: Path, scene_xml: Path) -> None:
    scene_xml.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("mujoco", {"model": "dexh13_interactive_press"})
    ET.SubElement(root, "include", {"file": hand_xml.name})
    worldbody = ET.SubElement(root, "worldbody")
    add_floor(worldbody)
    body = ET.SubElement(worldbody, "body", {"name": "press_probe", "pos": "0.219 -0.0315 0.026"})
    ET.SubElement(
        body,
        "joint",
        {
            "name": "press_z",
            "type": "slide",
            "axis": "0 0 1",
            "range": "-0.040 0.015",
            "limited": "true",
            "damping": "2.0",
            "stiffness": "8.0",
            "springref": "-0.026",
        },
    )
    ET.SubElement(
        body,
        "geom",
        {
            "name": "press_probe_geom",
            "type": "sphere",
            "size": "0.006",
            "mass": "0.05",
            "rgba": "0.1 0.45 1 1",
            "friction": "1.0 0.02 0.002",
            "solref": "0.01 1",
            "solimp": "0.90 0.98 0.002",
            "contype": "0",
            "conaffinity": "1",
        },
    )
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(scene_xml, encoding="utf-8", xml_declaration=True)


def write_free_object_scene(hand_xml: Path, scene_xml: Path) -> None:
    scene_xml.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("mujoco", {"model": "dexh13_free_object"})
    ET.SubElement(root, "include", {"file": hand_xml.name})
    worldbody = ET.SubElement(root, "worldbody")
    add_floor(worldbody)
    target = ET.SubElement(worldbody, "body", {"name": "free_sphere_target", "mocap": "true", "pos": "0.219 -0.0315 0.026"})
    ET.SubElement(
        target,
        "geom",
        {
            "name": "free_sphere_target_geom",
            "type": "sphere",
            "size": "0.003",
            "rgba": "1.0 0.8 0.1 0.45",
            "contype": "0",
            "conaffinity": "0",
        },
    )
    body = ET.SubElement(worldbody, "body", {"name": "free_sphere", "pos": "0.219 -0.0315 0.026"})
    ET.SubElement(body, "freejoint", {"name": "free_sphere_joint"})
    ET.SubElement(
        body,
        "geom",
        {
            "name": "free_sphere_geom",
            "type": "sphere",
            "size": "0.006",
            "mass": "0.05",
            "rgba": "0.1 0.45 1 1",
            "friction": "1.0 0.02 0.002",
            "solref": "0.01 1",
            "solimp": "0.90 0.98 0.002",
            "contype": "0",
            "conaffinity": "3",
        },
    )
    equality = ET.SubElement(root, "equality")
    ET.SubElement(
        equality,
        "weld",
        {
            "name": "free_sphere_physical_drag",
            "body1": "free_sphere",
            "body2": "free_sphere_target",
            "solref": "0.08 1",
            "solimp": "0.80 0.95 0.001",
            "torquescale": "0.02",
        },
    )
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(scene_xml, encoding="utf-8", xml_declaration=True)


def build(source: Path, sensors_yaml: Path, out: Path, scene: Path, interactive_scene: Path, free_object_scene: Path) -> None:
    tree = ET.parse(source)
    root = tree.getroot()
    with sensors_yaml.open(encoding="utf-8") as handle:
        sensors = yaml.safe_load(handle)["instances"]

    remove_sensor_plugins(root)
    remove_all_sites(root)
    remove_empty_sensor_frame_bodies(root)
    configure_compiler_and_option(root)
    configure_visuals(root)
    add_defaults(root)
    configure_geoms(root, sensors)
    add_sensor_frame_sites(root, sensors)
    add_external_collision_primitives(root)

    out.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    write_press_scene(out, scene)
    write_interactive_press_scene(out, interactive_scene)
    write_free_object_scene(out, free_object_scene)
    print(f"wrote {out}")
    print(f"wrote {scene}")
    print(f"wrote {interactive_scene}")
    print(f"wrote {free_object_scene}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the cleaned DexH13 tactile MuJoCo model.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--sensors", type=Path, default=DEFAULT_SENSORS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--interactive-scene", type=Path, default=DEFAULT_INTERACTIVE_SCENE)
    parser.add_argument("--free-object-scene", type=Path, default=DEFAULT_FREE_OBJECT_SCENE)
    args = parser.parse_args()
    build(args.source, args.sensors, args.out, args.scene, args.interactive_scene, args.free_object_scene)


if __name__ == "__main__":
    main()
