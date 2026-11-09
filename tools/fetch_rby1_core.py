# rby1-sim-isaac 공식 Docker 이미지에서 rby1 core(app_main)와 udp_protocol 모듈만 Docker 없이 추출하는 스크립트
"""Download only the small rby1 layers of rainbowroboticsofficial/rby1-sim-isaac and extract /opt/rby1-sim-isaac.

Skips the ~10 GB Isaac Sim base layer. Stdlib only, run inside WSL:
    python3 -I tools/fetch_rby1_core.py --tag 0.11.0-a_v1.2-isaac6.2.0 --out ~/rby1-core
"""
import argparse
import io
import json
import os
import tarfile
import urllib.request

REPO = "rainbowroboticsofficial/rby1-sim-isaac"
REGISTRY = "https://registry-1.docker.io/v2/" + REPO
MAX_LAYER = 200 * 1024 * 1024  # shortcut: skips any layer >200 MB (the Isaac Sim base), upgrade if rby1 files move there
PREFIX = "opt/rby1-sim-isaac/"


def get(url, token, accept=None):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    if accept:
        req.add_header("Accept", accept)
    return urllib.request.urlopen(req, timeout=120)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="0.11.0-a_v1.2-isaac6.2.0")
    ap.add_argument("--out", default=os.path.expanduser("~/rby1-core"))
    args = ap.parse_args()
    out = os.path.abspath(os.path.expanduser(args.out))

    token = json.load(urllib.request.urlopen(
        "https://auth.docker.io/token?service=registry.docker.io&scope=repository:%s:pull" % REPO))["token"]
    index = json.load(get(REGISTRY + "/manifests/" + args.tag, token,
                          "application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json"))
    digest = next(m["digest"] for m in index["manifests"] if m["platform"]["architecture"] == "amd64")
    manifest = json.load(get(REGISTRY + "/manifests/" + digest, token,
                             "application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json"))
    config = json.load(get(REGISTRY + "/blobs/" + manifest["config"]["digest"], token))

    os.makedirs(out, exist_ok=True)
    extracted = 0
    for layer in manifest["layers"]:
        if layer["size"] > MAX_LAYER:
            print("skip  %6.0f MB %s" % (layer["size"] / 1e6, layer["digest"][:19]))
            continue
        data = get(REGISTRY + "/blobs/" + layer["digest"], token).read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
            members = [m for m in tar.getmembers()
                       if m.name.startswith(PREFIX) and not os.path.basename(m.name).startswith(".wh.")]
            for m in members:
                m.name = m.name[len(PREFIX):]
                if not m.name or m.issym() or m.islnk():
                    continue
                tar.extract(m, out, filter="data")  # "data" filter blocks absolute paths and ../ escapes
                extracted += 1
        print("layer %6.2f MB %s -> %d files" % (layer["size"] / 1e6, layer["digest"][:19], len(members)))

    with open(os.path.join(out, "image_env.json"), "w") as f:
        json.dump({"tag": args.tag, "env": config["config"].get("Env", []),
                   "entrypoint": config["config"].get("Entrypoint")}, f, indent=2)
    print("extracted %d entries into %s" % (extracted, out))
    assert extracted > 0, "no /opt/rby1-sim-isaac files found in the small layers"


if __name__ == "__main__":
    main()
