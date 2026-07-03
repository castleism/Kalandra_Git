KALANDRA COMPANION ORBS
=======================
Drop your orb art here so players can pick which currency orb is their floating
companion (Settings -> Companion orb).

Folders:
  2d/   PNG sprites (square, transparent background, ideally 512x512).
        These render in the overlay today.
  3d/   Rigged 3D models (.glb/.gltf preferred) for the future 3D renderer.
        Not rendered yet — this is the home for them when that lands.

NAMING (must match exactly, lowercase):
  2d/<slug>.png      e.g. 2d/divine.png
  3d/<slug>.glb      e.g. 3d/divine.glb

SLUGS:
  divine         -> Divine Orb
  annulment      -> Orb of Annulment
  chaos          -> Chaos Orb
  regal          -> Regal Orb
  augmentation   -> Orb of Augmentation
  transmutation  -> Orb of Transmutation
  chance         -> Orb of Chance
  exalted        -> Exalted Orb
  vaal           -> Vaal Orb
  alchemy        -> Orb of Alchemy

If a selected orb's sprite is missing, Kalandra falls back to the bundled Divine
Orb art, then to a procedurally-drawn orb, so nothing breaks.
