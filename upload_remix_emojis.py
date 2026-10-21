import asyncio
import base64
import io
import math
import aiohttp
from PIL import Image, ImageDraw
from utils import config

def create_gif(frames, duration=60):
    buf = io.BytesIO()
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

def render_fx_remix():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        # Background badge
        d.ellipse((6, 6, 58, 58), fill=(28, 20, 48, 220), outline=(160, 60, 255, 230), width=2)
        # 3 DJ Fader sliders
        xs = [20, 32, 44]
        # Slider tracks
        for x in xs:
            d.line([(x, 16), (x, 48)], fill=(80, 70, 110, 255), width=3)
        # Moving slider knobs
        knob_y = [
            int(22 + 20 * (0.5 + 0.5 * math.sin(i / N * 2 * math.pi))),
            int(22 + 20 * (0.5 + 0.5 * math.sin(i / N * 2 * math.pi + 2.0))),
            int(22 + 20 * (0.5 + 0.5 * math.sin(i / N * 2 * math.pi + 4.0))),
        ]
        colors = [(0, 245, 255, 255), (255, 70, 200, 255), (0, 245, 255, 255)]
        for x, y, col in zip(xs, knob_y, colors):
            d.rounded_rectangle([x - 5, y - 3, x + 5, y + 3], radius=2, fill=col)
        frames.append(im)
    return create_gif(frames)

def render_fx_bass():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        # Subwoofer speaker cabinet
        d.rounded_rectangle([12, 10, 52, 54], radius=6, fill=(24, 20, 36, 255), outline=(255, 60, 100, 230), width=2)
        # Pumping woofer cone
        cr = int(12 + 4 * pulse)
        d.ellipse((32 - cr - 2, 34 - cr - 2, 32 + cr + 2, 34 + cr + 2), fill=(255, 50, 100, int(80 + 100 * pulse)))
        d.ellipse((32 - cr, 34 - cr, 32 + cr, 34 + cr), fill=(255, 60, 120, 255))
        d.ellipse((29, 31, 35, 37), fill=(255, 255, 255, 255))
        # Top tweeter
        d.ellipse((30, 15, 34, 19), fill=(0, 240, 255, 255))
        frames.append(im)
    return create_gif(frames)

def render_fx_vol():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        # Megaphone / Speaker cone
        d.polygon([(14, 25), (24, 25), (36, 15), (36, 49), (24, 39), (14, 39)], fill=(0, 245, 255, 255))
        # Sound waves radiating out
        w1_alpha = int(255 * (0.5 + 0.5 * math.sin(i / N * 2 * math.pi)))
        w2_alpha = int(255 * (0.5 + 0.5 * math.sin(i / N * 2 * math.pi + 1.5)))
        w3_alpha = int(255 * (0.5 + 0.5 * math.sin(i / N * 2 * math.pi + 3.0)))
        d.arc((32, 22, 44, 42), start=300, end=60, fill=(255, 70, 200, w1_alpha), width=3)
        d.arc((36, 16, 52, 48), start=300, end=60, fill=(255, 70, 200, w2_alpha), width=3)
        d.arc((40, 10, 60, 54), start=300, end=60, fill=(255, 70, 200, w3_alpha), width=3)
        frames.append(im)
    return create_gif(frames)

def render_fx_clear():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        angle = (i / N) * 2 * math.pi
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        # Background badge
        d.ellipse((6, 6, 58, 58), fill=(25, 25, 40, 220), outline=(255, 180, 50, 220), width=2)
        # Central glowing sparkle star
        s = int(12 + 3 * pulse)
        pts = [
            (32, 32 - s), (35, 28), (32 + s, 32), (35, 36),
            (32, 32 + s), (29, 36), (32 - s, 32), (29, 28)
        ]
        d.polygon(pts, fill=(255, 215, 60, 255))
        # Floating mini sparkle dots
        for sp in range(4):
            spa = angle + sp * (math.pi / 2)
            sx = int(32 + 18 * math.cos(spa))
            sy = int(32 + 18 * math.sin(spa))
            d.ellipse((sx - 2, sy - 2, sx + 2, sy + 2), fill=(0, 245, 255, 230))
        frames.append(im)
    return create_gif(frames)

def render_fx_crystal():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        # Glowing Diamond
        top = [(18, 24), (46, 24), (54, 32), (10, 32)]
        bot = [(10, 32), (54, 32), (32, 54)]
        # Shimmering facet colors
        r = int(140 + 60 * pulse)
        d.polygon(top, fill=(60, 180, 255, 255), outline=(200, 245, 255, 255), width=2)
        d.polygon(bot, fill=(30, 120, 230, 255), outline=(200, 245, 255, 255), width=2)
        # Inner facet lines
        d.line([(24, 24), (20, 32), (32, 54)], fill=(180, 235, 255, 240), width=1)
        d.line([(40, 24), (44, 32), (32, 54)], fill=(180, 235, 255, 240), width=1)
        # Top sparkle
        if i % 8 < 4:
            d.ellipse((42, 16, 48, 22), fill=(255, 255, 255, 255))
        frames.append(im)
    return create_gif(frames)

def render_fx_lofi():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        angle = (i / N) * 2 * math.pi
        # Cassette tape body
        d.rounded_rectangle([10, 16, 54, 48], radius=4, fill=(45, 30, 50, 255), outline=(255, 120, 180, 240), width=2)
        # Label window
        d.rectangle([18, 22, 46, 42], fill=(220, 180, 140, 255))
        # Cassette reels spinning
        r1_x, r2_x = 26, 38
        ry = 32
        d.ellipse((r1_x - 5, ry - 5, r1_x + 5, ry + 5), fill=(40, 30, 45, 255))
        d.ellipse((r2_x - 5, ry - 5, r2_x + 5, ry + 5), fill=(40, 30, 45, 255))
        # Reel spokes
        dx, dy = int(4 * math.cos(angle)), int(4 * math.sin(angle))
        d.line([(r1_x - dx, ry - dy), (r1_x + dx, ry + dy)], fill=(255, 255, 255, 255), width=1)
        d.line([(r2_x - dx, ry - dy), (r2_x + dx, ry + dy)], fill=(255, 255, 255, 255), width=1)
        frames.append(im)
    return create_gif(frames)

def render_fx_8d():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        angle = (i / N) * 2 * math.pi
        d.ellipse((6, 6, 58, 58), fill=(20, 20, 40, 220), outline=(0, 245, 255, 220), width=2)
        # Orbiting audio spheres circling around
        for orb in range(3):
            oa = angle + orb * (2 * math.pi / 3)
            ox = int(32 + 18 * math.cos(oa))
            oy = int(32 + 18 * math.sin(oa))
            d.ellipse((ox - 4, oy - 4, ox + 4, oy + 4), fill=(255, 60, 200, 255))
        # Center head / icon
        d.ellipse((27, 27, 37, 37), fill=(0, 245, 255, 255))
        frames.append(im)
    return create_gif(frames)

def render_fx_karaoke():
    frames = []
    N = 16
    for i in range(N):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pulse = 0.5 + 0.5 * math.sin(i / N * 2 * math.pi)
        # Microphone handle
        d.line([(24, 40), (14, 52)], fill=(120, 110, 150, 255), width=5)
        # Mic capsule
        d.ellipse((20, 16, 42, 38), fill=(255, 60, 160, int(180 + 75 * pulse)), outline=(255, 255, 255, 255), width=2)
        # Soundwaves floating from mic
        na = (i / N) * 2 * math.pi
        nx = int(44 + 4 * math.sin(na))
        ny = int(18 + 4 * math.cos(na))
        d.ellipse((nx - 2, ny - 2, nx + 2, ny + 2), fill=(0, 245, 255, 255))
        frames.append(im)
    return create_gif(frames)

REMIX_RENDERERS = {
    "REMIX_BTN": ("anim_fx_remix", render_fx_remix),
    "REMIX_BASS": ("anim_fx_bass", render_fx_bass),
    "REMIX_VOL": ("anim_fx_vol", render_fx_vol),
    "REMIX_CLEAR": ("anim_fx_clear", render_fx_clear),
    "REMIX_CRYSTAL": ("anim_fx_crystal", render_fx_crystal),
    "REMIX_LOFI": ("anim_fx_lofi", render_fx_lofi),
    "REMIX_8D": ("anim_fx_8d", render_fx_8d),
    "REMIX_KARAOKE": ("anim_fx_karaoke", render_fx_karaoke),
}

async def upload_remix():
    headers = {"Authorization": f"Bot {config.TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.get("https://discord.com/api/v10/users/@me", headers=headers) as r:
            app_id = (await r.json())["id"]
        
        results = {}
        print(f"Uploading {len(REMIX_RENDERERS)} animated remix emojis...")
        for const_name, (emoji_name, render_func) in REMIX_RENDERERS.items():
            b64_data = render_func()
            async with s.post(
                f"https://discord.com/api/v10/applications/{app_id}/emojis",
                headers=headers,
                json={"name": emoji_name, "image": b64_data}
            ) as r:
                if r.status in (200, 201):
                    data = await r.json()
                    anim_tag = f"<a:{emoji_name}:{data['id']}>"
                    results[const_name] = anim_tag
                    print(f"  [OK] Created {emoji_name} -> {anim_tag}")
                else:
                    err = await r.text()
                    print(f"  [FAIL] Failed {emoji_name}: {err}")
            await asyncio.sleep(0.4)

        print("\nAppending to utils/emojis.py...")
        with open(r"C:/Users/xdvip/Downloads/shizumusic-host/utils/emojis.py", "a", encoding="utf-8") as f:
            f.write("\n# Remix Console Emojis\n")
            for k, v in results.items():
                f.write(f'{k} = "{v}"\n')
        print("Done!")

if __name__ == "__main__":
    asyncio.run(upload_remix())
