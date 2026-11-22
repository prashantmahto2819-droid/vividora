"""Main video on its own background (transform.bg = image / video / gradient): full renders.
    cd server && python3 tests/test_main_bg_render.py"""
import sys, subprocess, tempfile, shutil, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vividora.engine import render
tmp = Path(tempfile.mkdtemp(prefix="bgr_"))
def ff(*a): subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",*a],check=True)
ff("-f","lavfi","-i","color=white:s=540x960:d=4:r=30","-f","lavfi","-i","sine=f=300:d=4","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(tmp/"main.mp4"))
ff("-f","lavfi","-i","color=0x404040:s=640x360","-frames:v","1",str(tmp/"bg.png"))
ff("-f","lavfi","-i","color=0x404040:s=640x360:d=1:r=25","-c:v","libx264","-pix_fmt","yuv420p",str(tmp/"bg.mp4"))
meta={"width":540,"height":960,"fps":30,"duration":4.0,"has_audio":True}
pre={"id":"t","label":"t","width":540,"height":960,"fit":"crop","burn_captions":False,"video":{"crf":23,"preset":"ultrafast","fps_max":60},"audio":{"loudness":-14,"true_peak":-1.5}}
half={"x":0,"y":0,"w":1,"h":0.5}
def go(name, tf, edl=None):
    t=time.time()
    r=render.render(video=tmp/"main.mp4",audio=None,meta=meta,edl=edl or {"duration":4.0,"cuts":[]},transcript=None,preset=pre,style=None,out_dir=tmp/"out",name=name,effects={"transform":tf},face_track="off",encoder_preset="ultrafast",burn_captions=False)
    f=Path(r["files"][0]["path"])
    d=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(f)],capture_output=True,text=True).stdout)
    raw=subprocess.run(["ffmpeg","-v","error","-ss","2","-i",str(f),"-frames:v","1","-f","rawvideo","-pix_fmt","gray","-"],capture_output=True).stdout
    at=lambda x,y: raw[int(y*959)*540+int(x*539)]
    print(f"{name}: {d:.2f}s in {time.time()-t:.0f}s  top={at(.5,.03)} mid={at(.5,.5)} bot={at(.5,.97)}")
    return d, at
d,at=go("img",{"bg":"image","bg_image_path":str(tmp/"bg.png"),"crop":half,"crop_fit":"fit"}); assert abs(d-4)<0.2 and at(.5,.5)>200 and 40<at(.5,.03)<90
d,at=go("vid",{"bg":"video","bg_video_path":str(tmp/"bg.mp4"),"crop":half,"crop_fit":"fit","scale":0.6,"y":-0.2}); assert abs(d-4)<0.2 and at(.5,.3)>200 and 40<at(.5,.9)<90
d,at=go("grad",{"bg":"gradient","bg_color":"#000000","bg_color2":"#000000","crop":half,"crop_fit":"fit"}); assert abs(d-4)<0.2 and at(.5,.5)>200 and at(.5,.03)<30
d,at=go("cut",{"bg":"image","bg_image_path":str(tmp/"bg.png"),"crop":half,"crop_fit":"fit"},{"duration":4.0,"cuts":[{"start":1.0,"end":2.0,"enabled":True,"reason":"silence"}]}); assert abs(d-3)<0.2 and at(.5,.5)>200, d
d,at=go("kf",{"bg":"image","bg_image_path":str(tmp/"bg.png"),"crop":half,"crop_fit":"fit","kf":{"scale":[{"t":0,"v":1},{"t":3,"v":0.6}]}}); assert abs(d-4)<0.2 and at(.5,.5)>200
d,at=go("plain",{"crop":half,"crop_fit":"fit","bg":"black"}); assert abs(d-4)<0.2 and at(.5,.03)<30 and at(.5,.5)>200
shutil.rmtree(tmp, ignore_errors=True); print("RENDER OK")
