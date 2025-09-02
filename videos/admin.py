# videos/admin.py
from django.contrib import admin
from .models import Video, Player, VideoPlayer
import datetime

# Helper to format timestamps nicely
def format_timestamp(seconds):
    return str(datetime.timedelta(seconds=int(seconds)))

# Inline for VideoPlayer objects inside Video admin
class VideoPlayerInline(admin.TabularInline):
    model = VideoPlayer
    extra = 0  # no empty extra rows
    readonly_fields = ('player', 'formatted_timestamp')
    can_delete = False  # optional: prevent deletion from inline

    # Display formatted timestamp
    def formatted_timestamp(self, obj):
        return format_timestamp(obj.timestamp)
    formatted_timestamp.short_description = "Timestamp"

# Video admin: show one row per video
@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'uploaded_at')
    inlines = [VideoPlayerInline]

# Player admin: just show player name
@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('name',)

# Optionally, do NOT register VideoPlayer separately
# @admin.register(VideoPlayer)
# class VideoPlayerAdmin(admin.ModelAdmin):
#     list_display = ('video', 'player', 'timestamp')
#     list_filter = ('video', 'player')
