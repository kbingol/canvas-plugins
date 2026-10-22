#!/usr/bin/env python3
"""Validate the distribution against vendored upstream schemas and package boundaries."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key in {path.name}: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def contained_file(base: Path, relative: str) -> Path:
    if not relative.startswith("./") or "\\" in relative:
        raise ValueError(f"Expected a portable ./ path: {relative}")
    raw = base / relative[2:]
    if any(part == ".." for part in Path(relative).parts):
        raise ValueError(f"Parent traversal is not allowed: {relative}")
    resolved = raw.resolve(strict=True)
    if not resolved.is_relative_to(base.resolve()) or not resolved.is_file() or raw.is_symlink():
        raise ValueError(f"Resource escapes its package or is not a file: {relative}")
    return resolved


def validate(root: Path = ROOT) -> dict:
    catalog = load_json(root / ".agents/plugins/marketplace.json")
    if catalog.get("name") != "canvas-plugins" or not catalog.get("plugins"):
        raise ValueError("The marketplace must identify canvas-plugins and contain a plugin")
    names = set()
    packages = []
    for entry in catalog["plugins"]:
        name = entry["name"]
        if name in names:
            raise ValueError(f"Duplicate marketplace plugin: {name}")
        names.add(name)
        if entry["source"]["source"] != "local":
            raise ValueError("This catalog uses plugin folders within the same Git snapshot")
        manifest_path = contained_file(root, entry["source"]["path"] + "/plugin.json")
        package = manifest_path.parent
        if any(p.is_symlink() for p in package.rglob("*")):
            raise ValueError("Plugin archives must not include symlinks")
        manifest = load_json(manifest_path)
        mcp = load_json(package / "mcp.json")
        if (package / "LICENSE").read_bytes() != (root / "LICENSE").read_bytes():
            raise ValueError("The installed package must include the distribution's license notice")
        for document, schema_name in ((manifest, "plugin"), (mcp, "mcp")):
            schema = load_json(root / "schemas" / f"{schema_name}.schema.json")
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(document)
        if manifest["name"] != name or not re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]):
            raise ValueError("Package identity must match the catalog and have a release version")
        if entry["policy"] != {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}:
            raise ValueError("Unexpected installation or authentication policy")
        ext = manifest["extensions"]["com.openai"]
        if ext.get("requires_local_executor") is not True:
            raise ValueError("Canvas must require a local executor")
        if ext["interface"]["capabilities"] != ["Read"]:
            raise ValueError("The current Canvas integration is read-only")
        for field in ("composerIcon", "composerIconDark", "logo", "logoDark"):
            asset = contained_file(package, ext["interface"][field])
            if asset.suffix == ".svg":
                tree = ET.parse(asset)
                for element in tree.iter():
                    if element.tag.rsplit("}", 1)[-1] in ("script", "foreignObject", "image"):
                        raise ValueError("Icons must be self-contained vector artwork")
                    if any(k.startswith("on") or "href" in k for k in element.attrib):
                        raise ValueError("Icons cannot contain executable or external references")
        setup = contained_file(package, ext["onboardingSkill"])
        skills = list((package / "skills").glob("*/SKILL.md"))
        if setup not in [p.resolve() for p in skills]:
            raise ValueError("Onboarding must refer to a packaged skill")
        for skill in skills:
            content = skill.read_text(encoding="utf-8")
            if not content.startswith("---\n"):
                raise ValueError(f"Missing skill frontmatter: {skill}")
            metadata = yaml.safe_load(content.split("---", 2)[1])
            if not re.fullmatch(r"[a-z0-9-]{1,64}", metadata.get("name", "")):
                raise ValueError(f"Invalid skill name: {skill}")
            if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
                raise ValueError(f"Missing skill description: {skill}")
        if set(mcp["mcpServers"]) != {"canvas"}:
            raise ValueError("Expected one Canvas server")
        server = mcp["mcpServers"]["canvas"]
        endpoint = urlsplit(server["url"])
        if server["type"] != "streamable-http" or server["url"] != "http://127.0.0.1:47321/mcp":
            raise ValueError("The distributed connection must use Canvas's standard local HTTP endpoint")
        if endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or server.get("headers"):
            raise ValueError("Never ship credentials, private headers or URL capabilities")
        for path in package.rglob("*"):
            if path.is_file() and (path.name in ("auth.json", "config.toml") or "__pycache__" in path.parts):
                raise ValueError(f"Local runtime data must not be distributed: {path}")
        packages.append({"name": name, "version": manifest["version"], "skills": len(skills)})
    return {"marketplace": catalog["name"], "packages": packages}


if __name__ == "__main__":
    try:
        print(json.dumps(validate(), indent=2))
    except Exception as error:
        print(f"Package validation failed: {error}", file=sys.stderr)
        sys.exit(1)
