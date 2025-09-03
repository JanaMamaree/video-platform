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

from .tasks import process_video_task

def upload_video(request):
    if request.method == "POST":
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.status = 'processing'
            video.save()

            players_text = form.cleaned_data['players']
            process_video_task.delay(video.id, players_text)

            return render(request, "videos/upload_video.html", {
                "form": VideoUploadForm(),
                "message": "Your video is being processed, you will be able to see it when it's ready."
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
            video_dict = defaultdict(list)
            vps = VideoPlayer.objects.filter(player=selected_player, video__status='ready').order_by("timestamp")
            for vp in vps:
                video_dict[vp.video].append(vp.timestamp)
            for video, timestamps in video_dict.items():
                results.append({"video": video, "timestamps": timestamps})
        except Player.DoesNotExist:
            pass
    else:
        for video in Video.objects.filter(status='ready'):
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