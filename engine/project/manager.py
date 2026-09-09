"""Save/load a `Project` as a single portable `.dgz` file (a zip archive
containing `project.json` plus the original page raster images).

Bundling the source raster alongside the vector data means a saved
project can always re-show "original vs. digitized" side by side later,
even if the user has since deleted/moved the original PDF/scan.
"""

from __future__ import annotations

import json
import os
import zipfile

from engine.project.schema import Project

PROJECT_FILE_EXTENSION = ".dgz"


def save_project(project: Project, page_image_paths: dict[int, str], out_path: str) -> str:
    if not out_path.endswith(PROJECT_FILE_EXTENSION):
        out_path += PROJECT_FILE_EXTENSION

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(project.to_dict(), indent=2))
        for index, path in sorted(page_image_paths.items()):
            zf.write(path, arcname=f"pages/page_{index:04d}.png")

    return out_path


def load_project(path: str, extract_dir: str) -> tuple[Project, dict[int, str]]:
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(extract_dir)

    with open(os.path.join(extract_dir, "project.json"), encoding="utf-8") as f:
        data = json.load(f)
    project = Project.from_dict(data)

    image_paths: dict[int, str] = {}
    pages_dir = os.path.join(extract_dir, "pages")
    if os.path.isdir(pages_dir):
        for filename in sorted(os.listdir(pages_dir)):
            if not filename.startswith("page_") or not filename.endswith(".png"):
                continue
            index = int(filename[len("page_") : -len(".png")])
            image_paths[index] = os.path.join(pages_dir, filename)

    return project, image_paths
