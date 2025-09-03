from celery import shared_task
from .models import Video, Player, VideoPlayer
from faster_whisper import WhisperModel
import subprocess
import os
import datetime
import tempfile
import shutil
import re

# Helper functions
def format_time(seconds):
    return str(datetime.timedelta(seconds=int(seconds)))

def get_video_duration(video_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    return float(result.stdout)

@shared_task(bind=True)
def process_video_task(self, video_id, players_text):
    print("Form is valid. Saving video...", flush=True)
    video = Video.objects.get(id=video_id)
    print(f"Video saved: {video.file.path}", flush=True)

    # Parse players
    player_names = [p.strip() for p in players_text.split(',')]
    player_name_map = {
        name.lower(): Player.objects.get_or_create(name=name)[0]
        for name in player_names
    }

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

        # Mark as ready
        video.status = 'ready'
        video.save()

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print(f"Temporary audio folder deleted: {tmpdir}", flush=True)
        print("Processing completed.", flush=True)  