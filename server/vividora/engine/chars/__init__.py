"""Character Studio (2D): parametric SVG rigs, a 200-profile library, pose animation, lip-sync,
2D scene environments and storyboard → explainer video. Everything is procedural vector art built
in-repo (no external image/video APIs, no downloads); frames are rasterised by ffmpeg's librsvg.

  catalog   options (skin, hair, outfits, props…) + the profile library
  rig       params + pose → SVG
  anim      pose clips (idle, talk, walk…) and pose_at(t)
  lipsync   text + timing (+ audio loudness) → mouth visemes
  render    SVG frames → preview PNG / alpha webm (cached)
  scenes2d  environments (classroom, clinic, shop…) → SVG / PNG
  storyboard scenes + dialogue → the explainer job and the project timeline
"""
