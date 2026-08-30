import pytest
from app.services.playlist import detect_platform, MultiPlatformAnalyzerService
from app.models.job import Platform

def test_detect_platform():
    assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == Platform.YOUTUBE
    assert detect_platform("https://youtu.be/dQw4w9WgXcQ") == Platform.YOUTUBE
    assert detect_platform("https://www.instagram.com/reel/C89abcdefgh/") == Platform.INSTAGRAM
    assert detect_platform("https://x.com/user/status/123456789") == Platform.TWITTER
    assert detect_platform("https://twitter.com/user/status/123456789") == Platform.TWITTER
    assert detect_platform("https://www.facebook.com/watch/?v=123456789") == Platform.FACEBOOK
    assert detect_platform("https://example.com/video.mp4") == Platform.GENERIC
