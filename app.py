import os
import uuid
import yt_dlp
import subprocess
import numpy as np

from flask import Flask, request, jsonify, send_file
from moviepy.editor import VideoFileClip
from faster_whisper import WhisperModel

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
OUTPUT_FOLDER = "outputs"

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# -----------------------------------
# HOOK WORDS (viral scoring için)
# -----------------------------------
HOOK_WORDS = [
    "şok", "inanılmaz", "kimse", "asla",
    "gerçek", "inanamıyorum", "nasıl",
    "neden", "beklenmedik", "tarihi"
]

# -----------------------------------
# VIDEO DOWNLOAD
# -----------------------------------
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

# -----------------------------------
# VIRAL 45 SECOND FINDER
# -----------------------------------
def find_viral_segment(segments, window=45):
    best_score = 0
    best_start = 0

    for i in range(len(segments)):
        start_time = segments[i].start
        end_time = start_time + window

        score = 0

        for seg in segments:
            if seg.start >= start_time and seg.end <= end_time:
                text = seg.text.lower()

                if "!" in text:
                    score += 2
                if "?" in text:
                    score += 2

                for word in HOOK_WORDS:
                    if word in text:
                        score += 3

                score += len(text.split()) * 0.05

        if score > best_score:
            best_score = score
            best_start = start_time

    return best_start, best_start + window

# -----------------------------------
# TITLE GENERATOR
# -----------------------------------
def generate_title(full_text):
    sentences = full_text.split(".")
    longest = max(sentences, key=len).strip()

    title = longest.capitalize()

    if len(title) > 80:
        title = title[:77] + "..."

    return title

# -----------------------------------
# SRT TIME FORMAT
# -----------------------------------
def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:06.3f}".replace('.', ',')

# -----------------------------------
# MAIN ROUTE
# -----------------------------------
@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL gerekli"}), 400

    try:
        # 1️⃣ Download
        video_path = download_video(url)

        # 2️⃣ Whisper transcript
        model = WhisperModel("base", compute_type="int8")
        segments, _ = model.transcribe(video_path)
        segments = list(segments)

        if not segments:
            return jsonify({"error": "Transcript alınamadı"}), 500

        # 3️⃣ Viral segment seç
        start, end = find_viral_segment(segments)

        clip = VideoFileClip(video_path).subclip(start, end)

        viral_path = os.path.join(
            OUTPUT_FOLDER,
            str(uuid.uuid4()) + "_viral.mp4"
        )

        clip.write_videofile(
            viral_path,
            codec="libx264",
            audio_codec="aac"
        )

        # 4️⃣ Altyazı oluştur
        srt_path = viral_path.replace(".mp4", ".srt")

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments):
                if seg.start >= start and seg.end <= end:
                    f.write(f"{i+1}\n")
                    f.write(
                        f"{format_time(seg.start-start)} --> "
                        f"{format_time(seg.end-start)}\n"
                    )
                    f.write(seg.text + "\n\n")

        subtitled_path = viral_path.replace(".mp4", "_sub.mp4")

        subprocess.run([
            "ffmpeg",
            "-i", viral_path,
            "-vf", f"subtitles={srt_path}",
            subtitled_path
        ])

        # 5️⃣ 9:16 format
        vertical_path = subtitled_path.replace(".mp4", "_vertical.mp4")

        subprocess.run([
            "ffmpeg",
            "-i", subtitled_path,
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920",
            "-preset", "ultrafast",
            vertical_path
        ])

        # 6️⃣ Başlık üret
        full_text = " ".join([seg.text for seg in segments])
        title = generate_title(full_text)

        return jsonify({
            "title": title,
            "download_url": "/download/" + os.path.basename(vertical_path)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -----------------------------------
# DOWNLOAD ROUTE
# -----------------------------------
@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    return send_file(path, as_attachment=True)

# -----------------------------------
# SIMPLE HOME UI
# -----------------------------------
@app.route("/")
def home():
    return """
    <h2>AutoShorts AI Generator</h2>
    <input id='url' placeholder='YouTube Link' style='width:300px'/>
    <button onclick='generate()'>Generate</button>
    <p id='result'></p>
    <script>
    async function generate(){
        let url = document.getElementById('url').value;
        let res = await fetch('/generate', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({url:url})
        });
        let data = await res.json();

        if(data.error){
            document.getElementById('result').innerText = data.error;
        }else{
            document.getElementById('result').innerHTML =
            "<b>Title:</b> "+data.title+
            "<br><a href='"+data.download_url+"'>Download Video</a>";
        }
    }
    </script>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
