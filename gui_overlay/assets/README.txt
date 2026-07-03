KALANDRA — ASSETS GO HERE  (gui_overlay/assets/)

The overlay looks for these image files by EXACT name:

  gui_overlay/assets/mirror_of_kalandra.png
      The Mirror of Kalandra frame. A SQUARE (e.g. 1024x1024) PNG with
      transparency, holding the landscape oval mirror. The 5 medallion
      hotspots are positioned as fractions of this square, so keep the art
      centered in a square canvas.

  gui_overlay/assets/divine_orb.png
      The Divine Orb core that sits at the center and "talks". Square PNG
      with transparency. If absent, the overlay draws a procedural glowing orb.

OPTIONAL — talking-orb viseme sprites (lip-sync mouth shapes):

  gui_overlay/assets/visemes/mouth_A.png
  gui_overlay/assets/visemes/mouth_B.png
  ... through ...
  gui_overlay/assets/visemes/mouth_H.png
  gui_overlay/assets/visemes/mouth_X.png   (closed/rest mouth)

These are the Rhubarb Lip Sync shapes (A-H plus X for rest). If present, the
orb swaps them while speaking; if absent, it falls back to a procedural
jaw-drop animation. Same square, transparent PNGs, aligned to the orb.

Nothing here is required to LAUNCH — the app runs with a procedural mirror/orb
if these are missing. Drop your real art in with these names to use it.
