from django.db import models

class Player(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Video(models.Model):
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='videos/')
    uploaded_at = models.DateTimeField(auto_now_add=True)  # automatically set when saving


    def __str__(self):
        return self.title

class VideoPlayer(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    timestamp = models.CharField(max_length=20)  # e.g., "00:01:12"
