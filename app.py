from flask import Flask, request, render_template_string, send_file
import subprocess, os, uuid, random
from faster_whisper import WhisperModel

app = Flask(__name__)

model = WhisperModel("tiny", compute_type="int8")

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>AI Shorts Generator</title>
</head>
<body style="font-family:Arial;text-align:center;margin-top:40px;">
<h2>📱 Upload → AI Shorts</h2>
<form method="POST" enctype="multipart/form-data">
<input type="file" name="video" required>
<br><br>
<button type="submit">Generate</button>
</form>
{% if ready %}
<hr>
<h3>🔥 Title:</h3>
<p>{{title}}</p>
<h3>🏷 Hashtags:</h3>
<p>{{hashtags}}</p>
<a href="/download/{{id}}">⬇ Download MP4</a>
{% endif %}
</body>
</html>
"""

def format_time(seconds):
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{hrs:02}:{mins:02}:{secs:02},{ms:03}"

def get_duration(path):
    cmd = ["ffprobe","-v","error","-show_entries",
           "format=duration","-of",
           "default=noprint_wrappers=1:nokey=1",path]
    r = subprocess.run(cmd, stdout=subprocess.PIPE)
    try:
        return float(r.stdout)
    except:
        return 60

def title():
    return random.choice([
        "Wait For It…",
        "This Is Insane",
        "Unreal Moment",
        "You Won’t Expect This",
        "This Changed Everything"
    ])

def hashtags():
    return "#shorts #viral #trending #fyp #explore"

def add_subtitles(video_path, output_path):
    segments, _ = model.transcribe(video_path)

    srt_path = video_path.replace(".mp4", ".srt")

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments):
            f.write(f"{i+1}\n")
            f.write(f"{format_time(segment.start)} --> {format_time(segment.end)}\n")
            f.write(segment.text.strip().upper() + "\n\n")

    # Shorts style altyazı (büyük beyaz ortalı stroke)
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf",
        f"subtitles={srt_path}:force_style='Fontsize=18,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=1,Outline=3,Shadow=0,Alignment=2'",
        "-preset","veryfast",
        "-crf","23",
        "-y",
        output_path
    ]

    subprocess.run(cmd)
    os.remove(srt_path)

@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        f = request.files["video"]
        uid = str(uuid.uuid4())
        inp = f"{uid}.mp4"
        cut = f"{uid}_cut.mp4"
        final = f"{uid}_final.mp4"

        f.save(inp)

        duration = get_duration(inp)
        start = duration * 0.35 if duration > 60 else 0

        # 45 sn kes + 9:16 crop
        cmd = [
            "ffmpeg",
            "-ss", str(start),
            "-i", inp,
            "-t", "45",
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-preset","veryfast",
            "-crf","23",
            "-y", cut
        ]

        subprocess.run(cmd)
        os.remove(inp)

        add_subtitles(cut, final)
        os.remove(cut)

        return render_template_string(
            HTML,
            ready=True,
            title=title(),
            hashtags=hashtags(),
            id=uid
        )

    return render_template_string(HTML, ready=False)

@app.route("/download/<id>")
def download(id):
    return send_file(f"{id}_final.mp4", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
