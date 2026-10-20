#!/usr/bin/env python3
"""Put the freshly generated ads into an environment, rendering only what changed.

Run it straight after ``gen_velocity.py <env>``::

    python gen_velocity.py development
    python sync_ads.py    development

The SVGs are deterministic -- the same manifest always generates the same bytes --
so they are the signal for what actually changed. JPEG rendering is *not*: headless
Chromium loads the webfonts a little differently each time, so re-rendering an
untouched ad yields a JPG that differs by a fraction of a percent. Re-rendering
everything therefore rewrote all 15 JPGs on every manifest edit, which meant churn
commits from CI and binary merge conflicts when a local run raced one.

So: an ad whose generated SVG matches the committed one is left completely alone --
not rendered, not copied, byte-for-byte the file that is already in git. Only the
ads that differ (or that are missing their JPG) are rendered and copied, and ads
whose item has left the manifests are deleted.

Stdlib only, like build.py, so CI needs nothing beyond the renderer itself."""
import os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(HERE, "output")


def keys_in(folder, ext):
    """The ad names (``santafe_phone``) of every ``.<ext>`` file in a folder."""
    if not os.path.isdir(folder):
        return set()
    return {f[: -len(ext) - 1] for f in os.listdir(folder) if f.endswith("." + ext)}


def same_bytes(a, b):
    if not (os.path.isfile(a) and os.path.isfile(b)):
        return False
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def plan(env):
    """Split the generated ads into the ones to render and the ones to leave be.

    An ad is re-rendered when its SVG differs from the committed one, and also when
    its JPG is simply missing -- an unchanged SVG is no use if the image it stands
    for was never committed."""
    out_svg = os.path.join(OUT, "svg")
    generated = sorted(keys_in(out_svg, "svg"))
    if not generated:
        raise SystemExit(f"nothing in {out_svg}: run gen_velocity.py {env} first")

    dest = os.path.join(REPO, env, "ads")
    render, keep = [], []
    for key in generated:
        changed = not same_bytes(
            os.path.join(out_svg, key + ".svg"), os.path.join(dest, "svg", key + ".svg")
        )
        missing = not os.path.isfile(os.path.join(dest, "jpg", key + ".jpg"))
        (render if (changed or missing) else keep).append(key)

    # Anything left in the environment that this run did not generate belongs to an
    # item that is gone from the manifests (sold, unpublished, deleted), so its ads go.
    live = set(generated)
    stale = sorted(
        (ext, key)
        for ext in ("jpg", "svg")
        for key in keys_in(os.path.join(dest, ext), ext) - live
    )
    return render, keep, stale


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: sync_ads.py <environment>")
    env = sys.argv[1]
    dest = os.path.join(REPO, env, "ads")
    if not (os.path.isdir(os.path.join(dest, "jpg")) and os.path.isdir(os.path.join(dest, "svg"))):
        raise SystemExit(f"no such environment: {env} (expected {dest}/jpg and {dest}/svg)")

    render, keep, stale = plan(env)

    if render:
        # Same interpreter, so a venv run stays inside its venv.
        subprocess.run([sys.executable, os.path.join(HERE, "render_jpgs.py"), *render], check=True)

    for key in render:
        for ext in ("svg", "jpg"):
            src = os.path.join(OUT, ext, key + "." + ext)
            if not os.path.isfile(src):
                raise SystemExit(f"{key}: expected {src} after rendering")
            shutil.copyfile(src, os.path.join(dest, ext, key + "." + ext))

    for ext, key in stale:
        os.remove(os.path.join(dest, ext, key + "." + ext))

    # Keep output/ a faithful picture of this environment, so a hand-rolled
    # `cp output/jpg/*.jpg` cannot pick up a JPG from an earlier run or another env.
    for key in keys_in(os.path.join(OUT, "jpg"), "jpg") - set(render) - set(keep):
        os.remove(os.path.join(OUT, "jpg", key + ".jpg"))

    print(
        f"{env}: {len(render)} rendered, {len(keep)} unchanged"
        + (f", {len(stale)} removed" if stale else "")
    )
    for key in render:
        print("  +", key)
    for ext, key in stale:
        print("  -", f"{key}.{ext}")


if __name__ == "__main__":
    main()
