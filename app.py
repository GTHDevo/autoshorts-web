import os
import uuid
import yt_dlp
import subprocess
from flask import Flask, request, send_file, jsonify
from faster_whisper import WhisperModel
from moviepy.editor import VideoFileClip, concatenate_videoclips
import numpy as np

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
OUTPUT_FOLDER = "outputs"

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# -----------------------
# VIDEO DOWNLOAD
# -----------------------
def download_video(url):
    filename = str(uuid.uuid4()) + ".mp4"
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    ydl_opts = {
        "format": "best[height<=720]",
        "outtmpl": filepath,
        "quiet": True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return filepath

# -----------------------
# SILENCE CUT
# -----------------------
def cut_silence(video_path):
    video = VideoFileClip(video_path)
    audio = video.audio

    threshold = 0.03
    window = 0.1
    intervals = []

    speaking = False
    start = 0

    for t in np.arange(0, audio.duration, window):
        sub = audio.subclip(t, min(t + window, audio.duration))
        if sub.max_volume() > threshold:
            if not speaking:
                speaking = True
                start = t
        else:
            if speaking:
                speaking = False
                intervals.append((start, t))

    if speaking:
        intervals.append((start, audio.duration))

    clips = [video.subclip(s, e) for s, e in intervals]
    final = concatenate_videoclips(clips)

    output_path = os.path.join(OUTPUT_FOLDER, str(uuid.uuid4()) + "_cut.mp4")
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")

    video.close()
    return output_path

# -----------------------
# AUTO SUBTITLE
# -----------------------
def add_subtitles(video_path):
    model = WhisperModel("base", compute_type="int8")
    segments, _ = model.transcribe(video_path)

    srt_path = video_path.replace(".mp4", ".srt")

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments):
            f.write(f"{i+1}\n")
            f.write(f"{format_time(segment.start)} --> {format_time(segment.end)}\n")
            f.write(segment.text + "\n\n")

    output_path = video_path.replace(".mp4", "_sub.mp4")

    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vf", "subtitles=" + srt_path,
        output_path
    ])

    return output_path

def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:06.3f}".replace('.', ',')

# -----------------------
# 9:16 FORMAT
# -----------------------
def make_vertical(video_path):
    output_path = video_path.replace(".mp4", "_vertical.mp4")

    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-preset", "ultrafast",
        output_path
    ])

    return output_path

# -----------------------
# ROUTE
# -----------------------
@app.route("/generate", methods=["POST"])
def generate():
    url = request.json.get("url")

    if not url:
        return jsonify({"error": "URL gerekli"}), 400

    video = download_video(url)
    cut = cut_silence(video)
    sub = add_subtitles(cut)
    vertical = make_vertical(sub)

    return send_file(vertical, as_attachment=True)

@app.route("/")
def home():
    return """
    <h2>AutoShorts Generator</h2>
    <form method="post" action="/generate" onsubmit="event.preventDefault(); send();">
    <input id="url" placeholder="YouTube Link" style="width:300px"/>
    <button type="submit">Generate</button>
    </form>
    <script>
    async function send(){
        let url = document.getElementById('url').value;
        let res = await fetch('/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url:url})
        });
        let blob = await res.blob();
        let a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = "short.mp4";
        a.click();
    }
    </script>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
