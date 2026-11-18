import os, re, uuid, json, shutil, subprocess
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

BASE = Path(__file__).parent
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
OUTPUTS = DATA / "outputs"
for p in (UPLOADS, OUTPUTS): p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Viral Clipper")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUTS), name="outputs")

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "Command failed")[-1800:])
    return p.stdout.strip()

def probe(path):
    raw = run(["ffprobe","-v","error","-show_entries","format=duration:format_tags=title","-of","json",str(path)])
    d = json.loads(raw)
    return float(d.get("format",{}).get("duration",0)), d.get("format",{}).get("tags",{}).get("title","")

def safe_name(s):
    return re.sub(r"[^a-zA-Z0-9_-]+","-",s).strip("-")[:50] or "video"

def download_youtube(url, folder):
    if urlparse(url).netloc.lower() not in ("youtube.com","www.youtube.com","m.youtube.com","youtu.be","www.youtu.be"):
        raise HTTPException(400, "Please enter a valid YouTube URL.")
    opts = {"format":"bv*[height<=1080]+ba/b[height<=1080]/best","merge_output_format":"mp4",
            "outtmpl":str(folder/"source.%(ext)s"),"noplaylist":True,"quiet":True,
            "restrictfilenames":True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") or "YouTube video"
        candidates = list(folder.glob("source.*"))
        if not candidates: raise RuntimeError("Download did not produce a video file.")
        return candidates[0], title
    except Exception as e:
        raise HTTPException(400, "Could not access this video. Use a video you own or have permission to edit, or upload the file directly. Details: "+str(e)[:500])

def make_srt(video, output):
    # Optional transcription: install faster-whisper to generate burned-in subtitles.
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(os.getenv("WHISPER_MODEL","base"), device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(video), vad_filter=True)
        def stamp(t):
            ms=int((t-int(t))*1000); sec=int(t)%60; minute=(int(t)//60)%60; hour=int(t)//3600
            return f"{hour:02}:{minute:02}:{sec:02},{ms:03}"
        with open(output,"w",encoding="utf-8") as f:
            for i,s in enumerate(segments,1):
                f.write(f"{i}\n{stamp(s.start)} --> {stamp(s.end)}\n{s.text.strip()}\n\n")
        return True
    except Exception:
        return False

def hashtags(title):
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    stop = {"the","and","for","with","this","that","from","your","you","how","are","was","what","why","video"}
    tags = []
    for w in words:
        if len(w)>2 and w not in stop and w not in tags: tags.append(w)
    tags = ["#shorts","#youtubeshorts","#viral"] + ["#"+x for x in tags[:7]]
    return " ".join(tags)

@app.get("/")
def home(): return FileResponse(BASE/"static"/"index.html")

@app.post("/api/process")
async def process(url: str = Form(""), file: UploadFile|None = File(None),
                  clip_length: int = Form(30), clip_count: int = Form(3)):
    if not url.strip() and not file: raise HTTPException(400,"Paste a YouTube URL or upload a video.")
    clip_length = max(10,min(60,int(clip_length)))
    clip_count = max(1,min(10,int(clip_count)))
    job = uuid.uuid4().hex[:10]
    folder = OUTPUTS/job
    folder.mkdir(parents=True,exist_ok=True)
    try:
        if file and file.filename:
            ext = Path(file.filename).suffix.lower()
            if ext not in (".mp4",".mov",".mkv",".webm",".m4v"): raise HTTPException(400,"Upload MP4, MOV, MKV or WebM.")
            source = UPLOADS/f"{job}{ext}"
            with source.open("wb") as f: shutil.copyfileobj(file.file,f)
            title = Path(file.filename).stem
        else:
            source,title = download_youtube(url.strip(),folder)
        duration,_ = probe(source)
        if duration < 5: raise HTTPException(400,"Video is too short.")
        actual_len = min(clip_length, max(5,int(duration)))
        # Select evenly spaced segments, avoiding only the very beginning/end where possible.
        max_start = max(0, duration-actual_len)
        count = min(clip_count, max(1,int(duration//max(5,actual_len//2))))
        starts = [max_start*(i/(max(1,count-1))) for i in range(count)] if count>1 else [max_start/2]
        results=[]
        for i,start in enumerate(starts,1):
            out = folder/f"clip_{i:02}.mp4"
            # Vertical 9:16 center crop, scale to 1080x1920.
            run(["ffmpeg","-y","-ss",str(start),"-i",str(source),"-t",str(actual_len),
                 "-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                 "-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-b:a","128k","-movflags","+faststart",str(out)])
            results.append({"name":f"Clip {i}","url":f"/outputs/{job}/{out.name}","start":round(start,1),"duration":actual_len})
        thumb = folder/"thumbnail.jpg"
        run(["ffmpeg","-y","-ss",str(min(duration/2,starts[0]+2)),"-i",str(source),"-frames:v","1","-vf","scale=1280:-1","-q:v","3",str(thumb)])
        subtitle_ready = False
        if os.getenv("ENABLE_WHISPER","0") == "1":
            subtitle_ready = make_srt(source,folder/"captions.srt")
        return {"job_id":job,"title":title,"duration":round(duration,1),"clips":results,
                "thumbnail":f"/outputs/{job}/thumbnail.jpg","hashtags":hashtags(title),
                "subtitle_status":"Generated captions are available." if subtitle_ready else "Optional auto-captions are off. Enable Whisper in setup to generate them.",
                "captions":f"/outputs/{job}/captions.srt" if subtitle_ready else None}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(500,"Processing failed: "+str(e)[:1000])

@app.get("/api/health")
def health(): return {"ok":True}
