import base64
import json
from playwright.sync_api import sync_playwright

mockUser = {
  "id": "1",
  "email": "test@example.com",
  "name": "Test User",
  "profile_picture": "https://example.com/avatar.jpg",
  "session_id": "123",
}

mockVideos = {
  "videos": [
    {
      "id": "1",
      "title": "Test Video",
      "description": "Test Description",
      "thumbnail": "https://example.com/thumbnail.jpg",
      "duration_seconds": 120,
      "channel_id": "channel1",
      "channel_title": "Test Channel",
      "channel_thumbnail": "https://example.com/channel.jpg",
      "published_at": "2023-01-01T00:00:00Z",
      "view_count": 1000
    }
  ]
}

mockChannels = {
    "channels": [
        {
            "youtube_id": "channel1",
            "title": "Test Channel",
            "thumbnail_url": "https://example.com/channel.jpg",
             "description": "Test Channel Description",
            "custom_url": "@testchannel",
            "published_at": "2023-01-01T00:00:00Z",
             "best_thumbnail_url": "https://example.com/channel.jpg",
              "banner_url": "https://example.com/banner.jpg",
               "country": "US",
              "view_count": 10000,
              "subscriber_count": 500,
              "video_count": 10,
              "upload_playlist_id": "playlist1",
              "best_thumbnail_width": 800,
              "best_thumbnail_height": 800,
              "raw_json": "{}"
        }
    ]
}

def verify_hover_effect():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Route requests
        page.route("**/api/session", lambda route: route.fulfill(json={"id": "123", "user": mockUser}))
        page.route("**/api/youtube/videos/random*", lambda route: route.fulfill(json=mockVideos))
        page.route("**/api/youtube/channels", lambda route: route.fulfill(json=mockChannels))
        page.route("**/api/youtube/channel/*", lambda route: route.fulfill(json=mockChannels["channels"][0]))

        red_pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        page.route("**/*.jpg", lambda route: route.fulfill(body=red_pixel, content_type="image/png"))

        page.goto("http://localhost:3000")

        print("Waiting for video link...")
        try:
            page.wait_for_selector('a[href^="/video/"]', timeout=5000)
            print("Video link found.")
        except Exception as e:
            print("Video link NOT found.")
            browser.close()
            return

        # Get the video card using a more specific locator strategy
        # Find the link, then go up two levels to the card container
        print("Finding video card via link...")
        video_link = page.locator('a[href^="/video/"]').first
        video_card = video_link.locator("xpath=../..")

        # Check if the bg div exists
        print("Checking for background div...")
        bg_div = video_card.locator("div.bg-blue-50")

        if bg_div.count() == 0:
             print("Background div not found inside video card.")
             print(video_card.inner_html())
        else:
            print("Background div found.")

            # Hover
            print("Hovering...")
            video_card.hover()
            page.wait_for_timeout(500)

            # Screenshot
            print("Taking screenshot...")
            page.screenshot(path="/home/jules/verification/hover_effect_v4.png")
            print("Screenshot taken.")

        browser.close()

if __name__ == "__main__":
    verify_hover_effect()
