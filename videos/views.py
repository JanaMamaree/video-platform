from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from .forms import RegistrationForm, LoginForm, VideoUploadForm
from .models import Video, Player, VideoPlayer
from faster_whisper import WhisperModel
from collections import defaultdict
import subprocess
import os
import datetime
import tempfile
import shutil
import re

# Helper function to format seconds into hh:mm:ss
def format_time(seconds):
    return str(datetime.timedelta(seconds=int(seconds)))

# Helper function to get video duration using ffprobe
def get_video_duration(video_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    return float(result.stdout)

def upload_video(request):
    if request.method == "POST":
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            print("Form is valid. Saving video...", flush=True)
            video = form.save()
            print(f"Video saved: {video.file.path}", flush=True)

            # Parse players
            players_text = form.cleaned_data['players']
            player_names = [p.strip() for p in players_text.split(',')]
            player_name_map = {name.lower(): Player.objects.get_or_create(name=name)[0] for name in player_names}

            # Extract audio
            print("[STEP 3] Extracting audio...", flush=True)
            tmpdir = tempfile.mkdtemp()
            try:
                audio_path = os.path.join(tmpdir, "audio.wav")
                video_path = video.file.path
                subprocess.run(
                    ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
                     "-ar", "16000", "-ac", "1", audio_path, "-y"],
                    check=True
                )
                print(f"✅ Audio extracted: {audio_path}", flush=True)

                total_seconds = get_video_duration(video_path)
                total_formatted = format_time(total_seconds)

                # Load Whisper
                print("Starting transcription using Whisper (CPU)...", flush=True)
                model = WhisperModel("tiny", device="cpu", compute_type="int8")
                segments, _ = model.transcribe(audio_path, beam_size=1, language="it", word_timestamps=True)
                print("Transcription completed!", flush=True)

                # Compile regex for all player names
                pattern = re.compile(r"\b(" + "|".join(map(re.escape, player_name_map.keys())) + r")\b", re.IGNORECASE)

                # Match players efficiently
                matches = []
                last_print_second = -1
                for segment in segments:
                    for word in segment.words:
                        current_second = int(word.start)
                        if current_second != last_print_second:
                            print(f"Processing word at {format_time(word.start)} / {total_formatted}", flush=True)
                            last_print_second = current_second

                        # Search for any player in this word
                        match = pattern.search(word.word)
                        if match:
                            pname_lower = match.group(0).lower()
                            player_obj = player_name_map[pname_lower]
                            ts = format_time(word.start)
                            matches.append(VideoPlayer(video=video, player=player_obj, timestamp=ts))
                            print(f"⏱ {ts} → Player matched: {player_obj.name}", flush=True)

                # Bulk save all matches
                if matches:
                    VideoPlayer.objects.bulk_create(matches)
                    print(f"✅ {len(matches)} timestamps saved for players.", flush=True)
                else:
                    print("No player mentions found.", flush=True)

            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
                print(f"Temporary audio folder deleted: {tmpdir}", flush=True)

            return render(request, "videos/upload_video.html", {
                "form": form,
                "message": "Processing done!"
            })

        else:
            print("Form invalid!", flush=True)

    else:
        form = VideoUploadForm()
        print("Rendering empty form for GET request.", flush=True)

    return render(request, "videos/upload_video.html", {"form": form})


def video_list(request):
    players = Player.objects.all()
    selected_player = None
    results = []

    if request.GET.get("player"):
        player_id = request.GET.get("player")
        try:
            selected_player = Player.objects.get(id=player_id)

            # Group timestamps by video
            video_dict = defaultdict(list)
            vps = VideoPlayer.objects.filter(player=selected_player).order_by("timestamp")
            for vp in vps:
                video_dict[vp.video].append(vp.timestamp)

            for video, timestamps in video_dict.items():
                results.append({"video": video, "timestamps": timestamps})
        except Player.DoesNotExist:
            pass
    else:
        # Show all videos with empty timestamps
        for video in Video.objects.all():
            results.append({"video": video, "timestamps": []})

    return render(request, "videos/video_list.html", {
        "players": players,
        "results": results,
        "selected_player": selected_player,
    })


def register_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            return redirect('login')
    else:
        form = RegistrationForm()
    return render(request, "videos/register.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                return redirect('dashboard')
            else:
                return render(request, "videos/login.html", {"form": form, "error": "Invalid credentials"})
    else:
        form = LoginForm()
    return render(request, "videos/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect('login')


def dashboard_view(request):
    return render(request, "videos/dashboard.html")


import os
from django.http import FileResponse, HttpResponse, HttpResponseNotFound
from django.conf import settings

def stream_video(request, path):
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.exists(file_path):
        return HttpResponseNotFound()

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("Range", "").strip()
    if range_header:
        # Example: "bytes=1000-"
        range_match = range_header.split("=")[-1]
        start, end = range_match.split("-")
        start = int(start) if start else 0
        end = int(end) if end else file_size - 1
        length = end - start + 1

        with open(file_path, "rb") as f:
            f.seek(start)
            data = f.read(length)

        resp = HttpResponse(data, status=206, content_type="video/mp4")
        resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        resp["Accept-Ranges"] = "bytes"
        resp["Content-Length"] = str(length)
        return resp

    # fallback (no Range header → send full file)
    response = FileResponse(open(file_path, "rb"), content_type="video/mp4")
    response["Content-Length"] = str(file_size)
    return response