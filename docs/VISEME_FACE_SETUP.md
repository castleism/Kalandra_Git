# Expressive Talking Orb — Viseme Sprite Setup (Phase 1: overlay)

This makes the Divine Orb's mouth move with real, phoneme-accurate lip-sync,
using your Meshy 3D model rendered to a small set of flat images (sprites). The
overlay swaps these in time with the speech. (Phase 2 — a live 3D head in the
dashboard — comes later; the assets you make here are reused there.)

## The pipeline (already built in the app)

1. The orb speaks (TTS → a .wav).
2. **Rhubarb Lip Sync** analyzes that .wav and outputs a timed list of mouth
   shapes (A–H, plus X for rest).
3. The overlay shows the matching mouth sprite for each shape, on the dot.

You provide two things: **Rhubarb** (a tiny free tool) and **9 mouth PNGs**
rendered from your rigged model.

## Step 1 — Install Rhubarb

Download from https://github.com/DanielSWolf/rhubarb-lip-sync/releases and either:
- put `rhubarb.exe` on your PATH, or
- drop it at `tools/rhubarb/rhubarb.exe` in the project, or
- set an env var `RHUBARB_PATH` to its full path.

If Rhubarb isn't found, the orb still talks with a generic mouth-flap — you just
won't get phoneme-accurate shapes.

## Step 2 — Rig the face with Faceit (Blender)

In Blender with the Faceit addon on your Meshy head:
1. Set up and **bake the ARKit blendshape set** (Faceit → Shapes).
2. You'll then pose the mouth by combining a few ARKit shapes and render one
   image per Rhubarb shape below.

## Step 3 — Render the 9 mouth sprites

Render your model **once per shape**, identical camera/framing/lighting, on a
**transparent background** (PNG with alpha), square is easiest (e.g. 1024×1024).
Pose each using these ARKit blendshapes (approximate slider targets):

| File          | Rhubarb shape | Sound        | ARKit pose (dominant shapes) |
|---------------|---------------|--------------|------------------------------|
| `mouth_X.png` | X (rest)      | silence      | neutral, lips together |
| `mouth_A.png` | A             | M, B, P      | lips fully closed (mouthClose 1) |
| `mouth_B.png` | B             | K, S, T, EE  | jawOpen ~0.12, mouthStretch ~0.3 |
| `mouth_C.png` | C             | EH, AH       | jawOpen ~0.30 |
| `mouth_D.png` | D             | AA (wide)    | jawOpen ~0.6, mouthOpen |
| `mouth_E.png` | E             | OH, UH       | jawOpen ~0.25, mouthFunnel ~0.3 |
| `mouth_F.png` | F             | OO, W        | mouthPucker ~0.7, jawOpen ~0.12 |
| `mouth_G.png` | G             | F, V         | lower lip to upper teeth (mouthRollLower ~0.5) |
| `mouth_H.png` | H             | L            | jawOpen ~0.3, tongue up (or just open if no tongue) |

Save them all to:

```
gui_overlay/assets/visemes/
```

The app auto-detects them on launch. **Minimum viable:** even just
`mouth_X, mouth_A, mouth_C, mouth_D, mouth_F` gives convincing motion — missing
shapes fall back to the rest face, so you can start with 5 and add the rest.

## Tips for a clean result

- Keep the **head perfectly still** between renders — only the mouth changes — so
  sprites don't jitter when swapped. Lock the camera and lighting.
- Match the framing to the current orb so it drops in seamlessly (roughly the
  face filling a centered square).
- Export at one resolution; the app scales them into the orb area.
- Want a blink? Add `mouth_X` variants later; for now we focus on the mouth.

## Phase 2 (later): live 3D head in the dashboard

The same Faceit/ARKit blendshapes drive a real-time 3D head (QtQuick3D or
three.js) in the dashboard, with Rhubarb (or a viseme stream) setting morph-target
weights per frame. Nothing here is wasted — the rig and shapes carry over.
