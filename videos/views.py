from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from .forms import RegistrationForm, LoginForm, VideoUploadForm
from .models import Video, Player, VideoPlayer
from faster_whisper import WhisperModel
from collections import defaultdict
import subprocess
import os
import datetime


# Helper function to format seconds into hh:mm:ss
def format_time(seconds):
    return str(datetime.timedelta(seconds=int(seconds)))


def upload_video(request):
    if request.method == "POST":
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            print("Form is valid. Saving video...")
            video = form.save()
            print(f"Video saved: {video.file.path}")

            # Parse player names from form (split by commas)
            players_text = form.cleaned_data['players']
            player_names = [p.strip() for p in players_text.split(',')]
            print(f"Players parsed: {player_names}")
            player_objs = []
            for name in player_names:
                player_obj, created = Player.objects.get_or_create(name=name)
                player_objs.append(player_obj)
                print(f"{'Created' if created else 'Fetched'} player: {player_obj.name}")

            # Extract audio from video if it doesn't exist
            video_path = video.file.path
            audio_path = os.path.join(os.path.dirname(video_path), "audio.mp3")
            if not os.path.exists(audio_path):
                print("Extracting audio from video...")
                subprocess.run(
                    ["ffmpeg", "-i", video_path, "-vn", "-acodec", "mp3", audio_path, "-y"],
                    check=True
                )
                print(f"Audio extracted: {audio_path}")
            else:
                print(f"Audio already exists: {audio_path}")

            # Transcribe audio using Whisper
            print("Starting transcription using Whisper...")
            model = WhisperModel("small", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(
                audio_path,
                beam_size=5,
                language="it",
                word_timestamps=True
            )
            print("Transcription completed!")


            # Match player names to words in transcription
            print("Matching player names to words in transcription...")
            for segment in segments:
                for word in segment.words:
                    for player_obj in player_objs:
                        if player_obj.name.lower() in word.word.lower():
                            ts = format_time(word.start)
                            VideoPlayer.objects.create(video=video, player=player_obj, timestamp=ts)
            print("Processing done for all players and timestamps.")
            return render(request, "videos/upload_video.html", {
                "form": form,
                "message": "Processing done!"
            })
    else:
        form = VideoUploadForm()
        print("Rendering empty form for GET request.")

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
