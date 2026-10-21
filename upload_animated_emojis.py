import asyncio
import base64
import io
import math
import aiohttp
from PIL import Image, ImageDraw
from utils import config

def create_gif(frames, duration=60):
    buf = io.BytesIO()
    # Save as transparent animated GIF
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        disposal=2
    )
    return "data:image/gif;base64," + base64.b64encode(buf.getvalue()).decode()

def render_tick():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        r = int(24 + 3 * pulse)
        # Glow
        d.ellipse((32 - r - 2, 32 - r - 2, 32 + r + 2, 32 + r + 2), fill=(30, 215, 96, 90))
        d.ellipse((32 - r, 32 - r, 32 + r, 32 + r), fill=(30, 215, 96, 255))
        # White checkmark
        d.line([(21, 32), (28, 41), (43, 23)], fill=(255, 255, 255, 255), width=5)
        frames.append(im)
    return create_gif(frames)

def render_warning():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        # Glowing triangle
        alpha = int(180 + 75 * pulse)
        pts = [(32, 6), (7, 54), (57, 54)]
        d.polygon(pts, fill=(255, 170, 0, alpha), outline=(255, 220, 50, 255))
        # Inner exclamation mark
        d.line([(32, 22), (32, 38)], fill=(0, 0, 0, 255), width=4)
        d.ellipse((30, 44, 34, 48), fill=(0, 0, 0, 255))
        frames.append(im)
    return create_gif(frames)

def render_denied():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        r = int(24 + 3 * pulse)
        d.ellipse((32 - r - 2, 32 - r - 2, 32 + r + 2, 32 + r + 2), fill=(240, 50, 50, 80))
        d.ellipse((32 - r, 32 - r, 32 + r, 32 + r), fill=(235, 45, 60, 255))
        # Cross X
        d.line([(22, 22), (42, 42)], fill=(255, 255, 255, 255), width=5)
        d.line([(22, 42), (42, 22)], fill=(255, 255, 255, 255), width=5)
        frames.append(im)
    return create_gif(frames)

def render_add():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        angle = (i / N) * math.pi * 0.5
        # Circle background
        d.ellipse((6, 6, 58, 58), fill=(30, 30, 45, 220), outline=(0, 240, 255, 230), width=3)
        # Rotating Plus
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        L = 14
        dx1, dy1 = L * cos_a, L * sin_a
        dx2, dy2 = -L * sin_a, L * cos_a
        d.line([(32 - dx1, 32 - dy1), (32 + dx1, 32 + dy1)], fill=(0, 245, 255, 255), width=5)
        d.line([(32 - dx2, 32 - dy2), (32 + dx2, 32 + dy2)], fill=(0, 245, 255, 255), width=5)
        frames.append(im)
    return create_gif(frames)

def render_voice():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        # 4 bouncing equalizer bars
        bars = [
            int(10 + 20 * abs(math.sin(i / N * 2 * math.pi))),
            int(14 + 28 * abs(math.sin(i / N * 2 * math.pi + 1.2))),
            int(8 + 24 * abs(math.sin(i / N * 2 * math.pi + 2.5))),
            int(12 + 18 * abs(math.sin(i / N * 2 * math.pi + 3.8))),
        ]
        xs = [14, 26, 38, 50]
        for idx, (bx, bh) in enumerate(zip(xs, bars)):
            col = (0, 245, 255, 255) if idx % 2 == 0 else (200, 80, 255, 255)
            d.rounded_rectangle([bx - 3, 32 - bh // 2, bx + 3, 32 + bh // 2], radius=3, fill=col)
        frames.append(im)
    return create_gif(frames)

def render_music():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        angle = (i / N) * 2 * math.pi
        # Spinning vinyl disc
        d.ellipse((6, 6, 58, 58), fill=(20, 20, 26, 255), outline=(140, 80, 255, 230), width=2)
        # Grooves
        d.ellipse((14, 14, 50, 50), outline=(50, 45, 75, 220), width=1)
        d.ellipse((20, 20, 44, 44), outline=(70, 65, 100, 220), width=1)
        # Center label
        d.ellipse((23, 23, 41, 41), fill=(0, 240, 255, 255))
        # Center hole
        d.ellipse((30, 30, 34, 34), fill=(10, 10, 16, 255))
        # Light shimmer dot
        sx = 32 + 18 * math.cos(angle)
        sy = 32 + 18 * math.sin(angle)
        d.ellipse((sx - 3, sy - 3, sx + 3, sy + 3), fill=(255, 255, 255, 240))
        frames.append(im)
    return create_gif(frames)

def render_loading():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        start_deg = (i / N) * 360
        # Spinning arc
        d.arc((8, 8, 56, 56), start=start_deg, end=start_deg + 280, fill=(0, 245, 255, 255), width=5)
        # Tip dot
        rad = math.radians(start_deg + 280)
        tx = 32 + 24 * math.cos(rad)
        ty = 32 + 24 * math.sin(rad)
        d.ellipse((tx - 3, ty - 3, tx + 3, ty + 3), fill=(255, 80, 220, 255))
        frames.append(im)
    return create_gif(frames)

def render_spotify():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        d.ellipse((6, 6, 58, 58), fill=(30, 215, 96, 255))
        # 3 Sound wave arcs
        w = int(3 + pulse)
        d.arc((16, 12, 48, 44), start=210, end=330, fill=(0, 0, 0, 240), width=4)
        d.arc((18, 19, 46, 47), start=210, end=330, fill=(0, 0, 0, 240), width=4)
        d.arc((20, 26, 44, 50), start=210, end=330, fill=(0, 0, 0, 240), width=4)
        frames.append(im)
    return create_gif(frames)

def render_youtube():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        # Red rounded rect
        d.rounded_rectangle([6, 13, 58, 51], radius=14, fill=(255, 0, 0, 255), outline=(255, 100, 100, int(150 + 80 * pulse)), width=2)
        # White play triangle
        d.polygon([(26, 22), (26, 42), (43, 32)], fill=(255, 255, 255, 255))
        frames.append(im)
    return create_gif(frames)

def render_soundcloud():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        d.ellipse((6, 6, 58, 58), fill=(255, 85, 0, 255))
        # White cloud shape
        d.ellipse((14, 22, 34, 42), fill=(255, 255, 255, 255))
        d.ellipse((26, 16, 50, 40), fill=(255, 255, 255, 255))
        d.rectangle([20, 30, 48, 44], fill=(255, 255, 255, 255))
        frames.append(im)
    return create_gif(frames)

def render_jiosaavn():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((6, 6, 58, 58), fill=(0, 215, 140, 255))
        # Note
        shift = int(2 * math.sin(i / N * 2 * math.pi))
        d.ellipse((18 + shift, 34, 30 + shift, 46), fill=(255, 255, 255, 255))
        d.rectangle([26 + shift, 18, 30 + shift, 40], fill=(255, 255, 255, 255))
        d.polygon([(26 + shift, 18), (42 + shift, 14), (42 + shift, 22), (26 + shift, 26)], fill=(255, 255, 255, 255))
        frames.append(im)
    return create_gif(frames)

def render_autoplay():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        d.ellipse((6, 6, 58, 58), fill=(25, 20, 45, 220), outline=(0, 240, 255, 220), width=2)
        # Infinity ∞
        d.ellipse((14, 24, 32, 40), outline=(0, 245, 255, 255), width=3)
        d.ellipse((32, 24, 50, 40), outline=(255, 80, 220, 255), width=3)
        frames.append(im)
    return create_gif(frames)

def render_previous():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        shift = int(2 * math.sin(i / N * 2 * math.pi))
        d.ellipse((6, 6, 58, 58), fill=(30, 25, 50, 220), outline=(180, 80, 255, 220), width=2)
        # Bar |
        d.rectangle([17 + shift, 20, 21 + shift, 44], fill=(255, 255, 255, 255))
        # Arrow 1
        d.polygon([(34 + shift, 20), (34 + shift, 44), (22 + shift, 32)], fill=(255, 255, 255, 255))
        # Arrow 2
        d.polygon([(46 + shift, 20), (46 + shift, 44), (34 + shift, 32)], fill=(255, 255, 255, 255))
        frames.append(im)
    return create_gif(frames)

def render_pause():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        d.ellipse((6, 6, 58, 58), fill=(35, 30, 15, 220), outline=(255, 200, 50, 220), width=2)
        # Two bars ||
        alpha = int(200 + 55 * pulse)
        d.rounded_rectangle([20, 18, 28, 46], radius=3, fill=(255, 215, 60, alpha))
        d.rounded_rectangle([36, 18, 44, 46], radius=3, fill=(255, 215, 60, alpha))
        frames.append(im)
    return create_gif(frames)

def render_resume():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        d.ellipse((6, 6, 58, 58), fill=(20, 35, 25, 220), outline=(30, 230, 100, 220), width=2)
        # Play triangle ▶
        d.polygon([(23, 17), (23, 47), (49, 32)], fill=(30, 235, 110, 255))
        frames.append(im)
    return create_gif(frames)

def render_skip():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        shift = int(2 * math.sin(i / N * 2 * math.pi))
        d.ellipse((6, 6, 58, 58), fill=(30, 25, 50, 220), outline=(180, 80, 255, 220), width=2)
        # Arrow 1
        d.polygon([(18 + shift, 20), (18 + shift, 44), (30 + shift, 32)], fill=(255, 255, 255, 255))
        # Arrow 2
        d.polygon([(30 + shift, 20), (30 + shift, 44), (42 + shift, 32)], fill=(255, 255, 255, 255))
        # Bar |
        d.rectangle([43 + shift, 20, 47 + shift, 44], fill=(255, 255, 255, 255))
        frames.append(im)
    return create_gif(frames)

def render_loop():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        angle = (i / N) * 360
        d.ellipse((6, 6, 58, 58), fill=(20, 30, 45, 220), outline=(0, 220, 255, 220), width=2)
        # Circular loop arrows
        d.arc((16, 16, 48, 48), start=angle, end=angle + 140, fill=(0, 245, 255, 255), width=4)
        d.arc((16, 16, 48, 48), start=angle + 180, end=angle + 320, fill=(0, 245, 255, 255), width=4)
        frames.append(im)
    return create_gif(frames)

def render_shuffle():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        d.ellipse((6, 6, 58, 58), fill=(35, 20, 40, 220), outline=(240, 90, 220, 220), width=2)
        # Crossing arrows
        d.line([(16, 22), (28, 22), (38, 42), (48, 42)], fill=(255, 100, 230, 255), width=4)
        d.line([(16, 42), (28, 42), (38, 22), (48, 22)], fill=(255, 100, 230, 255), width=4)
        # Arrowheads
        d.polygon([(44, 18), (50, 22), (44, 26)], fill=(255, 100, 230, 255))
        d.polygon([(44, 38), (50, 42), (44, 46)], fill=(255, 100, 230, 255))
        frames.append(im)
    return create_gif(frames)

def render_rewind():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        angle = -(i / N) * 360
        d.ellipse((6, 6, 58, 58), fill=(25, 25, 45, 220), outline=(120, 160, 255, 220), width=2)
        d.arc((16, 16, 48, 48), start=angle, end=angle + 270, fill=(130, 180, 255, 255), width=4)
        frames.append(im)
    return create_gif(frames)

def render_stop():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        d.ellipse((6, 6, 58, 58), fill=(40, 15, 20, 220), outline=(255, 50, 70, 220), width=2)
        # Stop square ■
        s = int(12 + pulse)
        d.rounded_rectangle([32 - s, 32 - s, 32 + s, 32 + s], radius=3, fill=(255, 50, 70, 255))
        frames.append(im)
    return create_gif(frames)

def render_forward():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        angle = (i / N) * 360
        d.ellipse((6, 6, 58, 58), fill=(25, 25, 45, 220), outline=(120, 160, 255, 220), width=2)
        d.arc((16, 16, 48, 48), start=angle, end=angle + 270, fill=(130, 180, 255, 255), width=4)
        frames.append(im)
    return create_gif(frames)

def render_replay():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        angle = (i / N) * 360
        d.ellipse((6, 6, 58, 58), fill=(35, 20, 45, 220), outline=(220, 80, 255, 220), width=2)
        d.arc((16, 16, 48, 48), start=angle, end=angle + 290, fill=(225, 90, 255, 255), width=4)
        frames.append(im)
    return create_gif(frames)

RENDERERS = {
    "WARNING": ("anim_warning", render_warning),
    "TICK": ("anim_tick", render_tick),
    "ADD": ("anim_add", render_add),
    "VOICE": ("anim_voice", render_voice),
    "MUSIC": ("anim_music", render_music),
    "LOADING": ("anim_loading", render_loading),
    "DENIED": ("anim_denied", render_denied),
    "SPOTIFY": ("anim_spotify", render_spotify),
    "JIOSAAVN": ("anim_jiosaavn", render_jiosaavn),
    "SOUNDCLOUD": ("anim_soundcloud", render_soundcloud),
    "YOUTUBE": ("anim_youtube", render_youtube),
    "BTN_AUTOPLAY": ("anim_autoplay", render_autoplay),
    "BTN_PREVIOUS": ("anim_previous", render_previous),
    "BTN_PAUSE": ("anim_pause", render_pause),
    "BTN_RESUME": ("anim_resume", render_resume),
    "BTN_SKIP": ("anim_skip", render_skip),
    "BTN_LOOP": ("anim_loop", render_loop),
    "BTN_SHUFFLE": ("anim_shuffle", render_shuffle),
    "BTN_REWIND": ("anim_rewind", render_rewind),
    "BTN_STOP": ("anim_stop", render_stop),
    "BTN_FORWARD": ("anim_forward", render_forward),
    "BTN_REPLAY": ("anim_replay", render_replay),
}

async def main():
    headers = {"Authorization": f"Bot {config.TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.get("https://discord.com/api/v10/users/@me", headers=headers) as r:
            app_id = (await r.json())["id"]
        
        results = {}
        print(f"Uploading {len(RENDERERS)} animated application emojis to Discord...")
        for const_name, (emoji_name, render_func) in RENDERERS.items():
            b64_data = render_func()
            async with s.post(
                f"https://discord.com/api/v10/applications/{app_id}/emojis",
                headers=headers,
                json={"name": emoji_name, "image": b64_data}
            ) as r:
                if r.status in (200, 201):
                    data = await r.json()
                    eid = data["id"]
                    anim_tag = f"<a:{emoji_name}:{eid}>"
                    results[const_name] = anim_tag
                    print(f"  [OK] Created {emoji_name} -> {anim_tag}")
                else:
                    err = await r.text()
                    print(f"  [FAIL] Failed {emoji_name}: {err}")
            await asyncio.sleep(0.4)  # respect rate limits

        print("\nUpdating utils/emojis.py with animated emojis...")
        emojis_content = '"""Emoji used in embeds and buttons (All Animated Application Emojis)."""\n\n'
        for k, v in results.items():
            emojis_content += f'{k} = "{v}"\n'
        
        with open(r"C:/Users/xdvip/Downloads/shizumusic-host/utils/emojis.py", "w", encoding="utf-8") as f:
            f.write(emojis_content)
        print("utils/emojis.py updated successfully!")

if __name__ == "__main__":
    asyncio.run(main())
