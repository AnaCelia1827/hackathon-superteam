"""Record the English LoopRail dashboard demo; start apps/dashboard/server.py first."""

from __future__ import annotations

import json
import subprocess
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SCENES = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
OUTPUT = HERE / "looprail-demo-en.mp4"


def audio_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        return source.getnframes() / source.getframerate()


def combine_audio(paths: list[Path], output: Path) -> None:
    with wave.open(str(paths[0]), "rb") as first:
        params = first.getparams()
    with wave.open(str(output), "wb") as result:
        result.setparams(params)
        for path in paths:
            with wave.open(str(path), "rb") as source:
                if source.getparams()[:3] != params[:3]:
                    raise ValueError("Narration WAV formats do not match")
                result.writeframes(source.readframes(source.getnframes()))
            result.writeframes(b"\0" * int(params.framerate * params.nchannels * params.sampwidth * 0.5))


def show_card(page, scene: dict, full: bool = False) -> None:
    page.evaluate(
        """({title, caption, full}) => {
          let card = document.getElementById('demo-card');
          if (!card) {
            card = document.createElement('div');
            card.id = 'demo-card';
            document.body.append(card);
          }
          card.style.cssText = full
            ? 'position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;justify-content:center;padding:11%;background:rgba(12,25,19,.94);color:white;font-family:Segoe UI,Arial,sans-serif;pointer-events:none'
            : 'position:fixed;left:36px;right:36px;bottom:26px;z-index:9999;padding:17px 22px;border-radius:12px;background:rgba(12,25,19,.91);color:white;font-family:Segoe UI,Arial,sans-serif;box-shadow:0 12px 35px #0007;pointer-events:none';
          card.replaceChildren();
          const heading = document.createElement('strong');
          heading.textContent = title;
          heading.style.cssText = full ? 'font-size:52px;letter-spacing:-.04em' : 'font-size:19px';
          const detail = document.createElement('span');
          detail.textContent = caption;
          detail.style.cssText = full ? 'margin-top:16px;font-size:25px;color:#b5ff35' : 'display:block;margin-top:5px;font-size:15px;color:#b5ff35';
          card.append(heading, detail);
        }""",
        {"title": scene["title"], "caption": scene["caption"], "full": full},
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="looprail-video-") as temp_name:
        temp = Path(temp_name)
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(HERE / "narrate.ps1"), "-SceneFile", str(HERE / "narration.json"),
             "-OutputDirectory", str(temp)],
            check=True, capture_output=True, text=True,
        )
        voices = [temp / f"scene-{index:02}.wav" for index in range(len(SCENES))]
        durations = [audio_duration(path) + 0.5 for path in voices]
        combine_audio(voices, temp / "narration.wav")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                record_video_dir=str(temp),
                record_video_size={"width": 1280, "height": 800},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.goto("http://127.0.0.1:8000", wait_until="networkidle")
            page.wait_for_selector("#step-count")

            show_card(page, SCENES[0], full=True)
            page.wait_for_timeout(durations[0] * 1000)
            show_card(page, SCENES[1])
            page.wait_for_timeout(durations[1] * 1000)

            page.get_by_role("button", name="Run replay").click()
            show_card(page, SCENES[2])
            page.wait_for_timeout(durations[2] * 1000)
            page.evaluate("window.scrollTo({top: 470, behavior: 'smooth'})")
            show_card(page, SCENES[3])
            page.wait_for_timeout(durations[3] * 1000)

            page.get_by_role("button", name="View on-chain run").click()
            page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
            show_card(page, SCENES[4])
            page.wait_for_timeout(durations[4] * 1000)
            page.locator("#settlement-panel").scroll_into_view_if_needed()
            show_card(page, SCENES[5])
            page.wait_for_timeout(durations[5] * 1000)

            show_card(page, SCENES[6], full=True)
            page.wait_for_timeout(durations[6] * 1000)
            page.wait_for_timeout(700)
            video = page.video
            context.close()
            capture = Path(video.path())
            browser.close()

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, "-y", "-i", str(capture), "-i", str(temp / "narration.wav"),
             "-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest", str(OUTPUT)],
            check=True, capture_output=True, text=True,
        )
    print(f"Recorded {OUTPUT} ({OUTPUT.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    main()
