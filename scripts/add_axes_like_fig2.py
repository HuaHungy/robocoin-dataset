#!/usr/bin/env python3
import argparse
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from copy import deepcopy


def parse_xml(path: Path) -> ET.ElementTree:
    return ET.parse(str(path))


def get_or_create(root: ET.Element, tag: str) -> ET.Element:
    el = root.find(tag)
    if el is None:
        el = ET.Element(tag)
        root.append(el)
    return el


def extract_axes_style(ref_root: ET.Element) -> dict:
    """从参考文件提取 world_axes 的样式（半径、rgba），若未找到则给默认值。"""
    style = {"radius": 0.02, "rgba": "1 1 0 0.7", "z_base": 0.01}
    ref_world = ref_root.find("worldbody")
    if ref_world is None:
        return style
    ref_axes = None
    for b in ref_world.findall("body"):
        if b.attrib.get("name") == "world_axes":
            ref_axes = b
            break
    if ref_axes is None:
        return style

    # 取其中一个轴的 size 第一个值作为半径，rgba 作为颜色
    for g in ref_axes.findall("geom"):
        size = g.attrib.get("size", "").split()
        rgba = g.attrib.get("rgba", style["rgba"])
        if len(size) >= 2:
            try:
                style["radius"] = float(size[0])
            except ValueError:
                pass
        style["rgba"] = rgba
        break
    return style


def remove_existing_axes(worldbody: ET.Element):
    # 移除已有 world_axes（避免重复）
    for child in list(worldbody):
        if child.tag == "body" and child.attrib.get("name") == "world_axes":
            worldbody.remove(child)


def add_axes(worldbody: ET.Element, radius: float, rgba: str, xlen: float, ylen: float, zlen: float, z_base: float = 0.01):
    axes = ET.SubElement(worldbody, "body", {"name": "world_axes", "pos": "0 0 0"})
    # Z 轴（最长，竖直）
    ET.SubElement(axes, "geom", {
        "name": "axis_z",
        "type": "cylinder",
        "size": f"{radius} {zlen}",
        "pos": f"0 0 {zlen/2}",
        "rgba": rgba
    })
    # X 轴（最短，沿 X，绕 Y 旋转 90 度）
    ET.SubElement(axes, "geom", {
        "name": "axis_x",
        "type": "cylinder",
        "size": f"{radius} {xlen}",
        "pos": f"{xlen/2} 0 {z_base}",
        "euler": "0 1.57 0",
        "rgba": rgba
    })
    # Y 轴（次长，沿 Y，绕 X 旋转 -90 度）
    ET.SubElement(axes, "geom", {
        "name": "axis_y",
        "type": "cylinder",
        "size": f"{radius} {ylen}",
        "pos": f"0 {ylen/2} {z_base}",
        "euler": "-1.57 0 0",
        "rgba": rgba
    })


def main():
    ap = argparse.ArgumentParser(description="参考 fig2 文件给目标 XML 添加坐标轴（x最短，y次之，z最长）")
    ap.add_argument("--target", required=True, help="目标 XML，例如 G1_roh_extracted_with_env.xml")
    ap.add_argument("--ref", required=True, help="参考 XML，例如 G1_roh_scene_fig2.xml")
    ap.add_argument("--xlen", type=float, default=1.0, help="x轴长度（最短）")
    ap.add_argument("--ylen", type=float, default=1.5, help="y轴长度（次长）")
    ap.add_argument("--zlen", type=float, default=2.0, help="z轴长度（最长）")
    ap.add_argument("--radius", type=float, default=None, help="轴半径（默认取自参考文件或 0.02）")
    ap.add_argument("--out", help="输出路径（默认覆盖 target）")
    args = ap.parse_args()

    target_path = Path(args.target).expanduser().resolve()
    ref_path = Path(args.ref).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve() if args.out else target_path

    target_tree = parse_xml(target_path)
    target_root = target_tree.getroot()

    ref_tree = parse_xml(ref_path)
    ref_root = ref_tree.getroot()

    # worldbody 必须存在
    worldbody = get_or_create(target_root, "worldbody")

    # 样式（半径/颜色）从参考提取
    style = extract_axes_style(ref_root)
    radius = args.radius if args.radius is not None else style["radius"]
    rgba = style["rgba"]
    z_base = style["z_base"]

    # 移除已有坐标轴并添加新的
    remove_existing_axes(worldbody)
    add_axes(worldbody, radius, rgba, args.xlen, args.ylen, args.zlen, z_base=z_base)

    # 写回
    target_tree.write(str(out_path), encoding="utf-8", xml_declaration=True)
    print(f"[OK] 已写入坐标轴到: {out_path}")


if __name__ == "__main__":
    main()