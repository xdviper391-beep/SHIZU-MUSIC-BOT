import math
import os
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

SRC_IMG_PATH = r"C:/Users/xdvip/.gemini/antigravity/brain/3e6f2f5a-df32-48e3-80b1-a7d799cb3f77/.user_uploaded/media_1792614282566_e9322d08.png"
FONT_BOLD = r"C:/Users/xdvip/Downloads/shizumusic-host/data/fonts/Poppins-Bold.ttf"
FONT_REGULAR = r"C:/Users/xdvip/Downloads/shizumusic-host/data/fonts/Poppins-Medium.ttf"

def create_circular_mask(size):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size[0], size[1]), fill=255)
    return mask

def generate_avatar():
    print("Generating animated avatar GIF...")
    dog_orig = Image.open(SRC_IMG_PATH).convert("RGBA")
    
    W, H = 400, 400
    TOTAL_FRAMES = 30
    frames = []

    # Center coordinates
    cx, cy = W // 2, H // 2
    base_radius = 115

    for frame_idx in range(TOTAL_FRAMES):
        progress = frame_idx / TOTAL_FRAMES
        angle_prog = progress * 2 * math.pi

        # Create dark background
        img = Image.new("RGBA", (W, H), (10, 8, 22, 255))
        draw = ImageDraw.Draw(img)

        # Ambient radial glow in background
        pulse = 0.5 + 0.5 * math.sin(angle_prog)
        glow_radius = int(base_radius + 50 + 20 * pulse)
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_draw.ellipse(
            (cx - glow_radius, cy - glow_radius, cx + glow_radius, cy + glow_radius),
            fill=(140, 40, 220, int(60 + 35 * pulse))
        )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(35))
        img = Image.alpha_composite(img, glow_layer)
        draw = ImageDraw.Draw(img)

        # Equalizer bars radiating outwards
        num_bars = 40
        for i in range(num_bars):
            bar_angle = (i / num_bars) * 2 * math.pi
            # Sound wave oscillation
            wave1 = math.sin(bar_angle * 3 + angle_prog * 2)
            wave2 = math.cos(bar_angle * 5 - angle_prog * 3)
            wave3 = math.sin(bar_angle * 2 + angle_prog)
            bar_height = 12 + 22 * abs(wave1 * 0.5 + wave2 * 0.3 + wave3 * 0.2)
            
            # Start and end points
            r1 = base_radius + 6
            r2 = r1 + bar_height
            
            x1 = cx + r1 * math.cos(bar_angle)
            y1 = cy + r1 * math.sin(bar_angle)
            x2 = cx + r2 * math.cos(bar_angle)
            y2 = cy + r2 * math.sin(bar_angle)

            # Color cycle (cyan -> magenta -> purple)
            hue_prog = (i / num_bars + progress) % 1.0
            if hue_prog < 0.33:
                r = int(0 + 255 * (hue_prog / 0.33))
                g = int(240 - 100 * (hue_prog / 0.33))
                b = 255
            elif hue_prog < 0.66:
                t = (hue_prog - 0.33) / 0.33
                r = 255
                g = int(140 * (1 - t))
                b = int(255 - 50 * t)
            else:
                t = (hue_prog - 0.66) / 0.34
                r = int(255 - 255 * t)
                g = int(0 + 240 * t)
                b = 255
            
            draw.line([(x1, y1), (x2, y2)], fill=(r, g, b, 230), width=3)

        # Concentric neon border ring
        ring_r = base_radius + 4
        draw.ellipse(
            (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
            outline=(255, 60, 180, 255), width=3
        )
        ring_r2 = base_radius + 2
        draw.ellipse(
            (cx - ring_r2, cy - ring_r2, cx + ring_r2, cy + ring_r2),
            outline=(0, 245, 255, 255), width=2
        )

        # Scale dog subtly with breathing motion
        dog_scale = 1.0 + 0.03 * math.sin(angle_prog)
        cur_dog_size = int(base_radius * 2 * dog_scale)
        # Ensure even size
        cur_dog_size = cur_dog_size + (cur_dog_size % 2)
        dog_resized = dog_orig.resize((cur_dog_size, cur_dog_size), Image.Resampling.LANCZOS)
        
        # Mask into circle
        mask = Image.new("L", (cur_dog_size, cur_dog_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, cur_dog_size, cur_dog_size), fill=255)
        
        dog_x = cx - cur_dog_size // 2
        dog_y = cy - cur_dog_size // 2
        img.paste(dog_resized, (dog_x, dog_y), mask)

        # Floating music particles
        for p in range(8):
            p_angle = (p / 8) * 2 * math.pi + angle_prog * (0.8 if p % 2 == 0 else -0.8)
            p_dist = base_radius + 50 + 15 * math.sin(angle_prog + p)
            px = int(cx + p_dist * math.cos(p_angle))
            py = int(cy + p_dist * math.sin(p_angle))
            p_alpha = int(140 + 100 * math.sin(angle_prog * 2 + p))
            p_color = (0, 245, 255, p_alpha) if p % 2 == 0 else (255, 100, 220, p_alpha)
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=p_color)

        frames.append(img.convert("P", palette=Image.Palette.ADAPTIVE))

    out_path = r"C:/Users/xdvip/Downloads/shizumusic-host/avatar.gif"
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=50,  # 50ms per frame = 20 fps
        loop=0,
        optimize=True
    )
    print(f"Avatar saved: {out_path} ({os.path.getsize(out_path)} bytes)")

generate_avatar()


def generate_banner():
    print("Generating animated banner GIF...")
    dog_orig = Image.open(SRC_IMG_PATH).convert("RGBA")
    
    W, H = 680, 240
    TOTAL_FRAMES = 30
    frames = []

    try:
        title_font = ImageFont.truetype(FONT_BOLD, 46)
        sub_font = ImageFont.truetype(FONT_REGULAR, 17)
        badge_font = ImageFont.truetype(FONT_BOLD, 12)
    except Exception:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
        badge_font = ImageFont.load_default()

    # Dog position on the left
    dog_cx, dog_cy = 125, H // 2
    dog_r = 72

    for frame_idx in range(TOTAL_FRAMES):
        progress = frame_idx / TOTAL_FRAMES
        angle_prog = progress * 2 * math.pi

        # Create dark background
        img = Image.new("RGBA", (W, H), (11, 9, 24, 255))
        draw = ImageDraw.Draw(img)

        # Ambient neon glow spots in background
        pulse = 0.5 + 0.5 * math.sin(angle_prog)
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        
        # Glow behind dog
        glow_draw.ellipse(
            (dog_cx - 100, dog_cy - 100, dog_cx + 100, dog_cy + 100),
            fill=(140, 30, 220, int(70 + 40 * pulse))
        )
        # Glow behind text
        glow_draw.ellipse(
            (350, 40, 580, 180),
            fill=(0, 180, 255, int(45 + 30 * pulse))
        )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(40))
        img = Image.alpha_composite(img, glow_layer)
        draw = ImageDraw.Draw(img)

        # Horizontal audio wave line in background
        wave_pts = []
        for x in range(0, W, 8):
            y = int(H * 0.72 + 8 * math.sin((x / 40.0) + angle_prog) + 4 * math.cos((x / 25.0) - angle_prog * 2))
            wave_pts.append((x, y))
        draw.line(wave_pts, fill=(90, 50, 160, 90), width=2)

        # Bottom audio visualizer spectrum bars
        num_bottom_bars = 48
        bar_w = 7
        bar_gap = 6
        start_x = 225
        for b in range(num_bottom_bars):
            bx = start_x + b * (bar_w + bar_gap)
            if bx + bar_w > W - 15:
                break
            # Natural music spectrum wave equation
            bh = int(10 + 26 * abs(
                math.sin(b * 0.45 + angle_prog * 2) * 0.5 +
                math.cos(b * 0.8 - angle_prog * 3) * 0.3 +
                math.sin(b * 1.2 + angle_prog) * 0.2
            ))
            by1 = H - 18 - bh
            by2 = H - 18
            
            # Gradient bar color (Cyan to Pink/Purple)
            t = b / num_bottom_bars
            r = int(0 + 255 * t)
            g = int(240 * (1 - t * 0.6))
            b_val = 255
            draw.rectangle([bx, by1, bx + bar_w, by2], fill=(r, g, b_val, 220))

        # Radial equalizer around the dog badge
        num_dog_bars = 28
        for i in range(num_dog_bars):
            bar_angle = (i / num_dog_bars) * 2 * math.pi
            bh = 6 + 14 * abs(math.sin(bar_angle * 4 + angle_prog * 2) * 0.7 + math.cos(bar_angle * 2 - angle_prog) * 0.3)
            r1 = dog_r + 4
            r2 = r1 + bh
            x1 = dog_cx + r1 * math.cos(bar_angle)
            y1 = dog_cy + r1 * math.sin(bar_angle)
            x2 = dog_cx + r2 * math.cos(bar_angle)
            y2 = dog_cy + r2 * math.sin(bar_angle)
            
            p_val = (i / num_dog_bars + progress) % 1.0
            col = (255, 60, 180, 230) if p_val < 0.5 else (0, 245, 255, 230)
            draw.line([(x1, y1), (x2, y2)], fill=col, width=2)

        # Concentric glowing rings
        draw.ellipse((dog_cx - dog_r - 3, dog_cy - dog_r - 3, dog_cx + dog_r + 3, dog_cy + dog_r + 3), outline=(255, 60, 180, 255), width=3)
        draw.ellipse((dog_cx - dog_r - 1, dog_cy - dog_r - 1, dog_cx + dog_r + 1, dog_cy + dog_r + 1), outline=(0, 245, 255, 255), width=2)

        # Scale dog subtly with breathing
        dog_scale = 1.0 + 0.025 * math.sin(angle_prog)
        cur_dog_size = int(dog_r * 2 * dog_scale)
        cur_dog_size = cur_dog_size + (cur_dog_size % 2)
        dog_resized = dog_orig.resize((cur_dog_size, cur_dog_size), Image.Resampling.LANCZOS)
        
        mask = Image.new("L", (cur_dog_size, cur_dog_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, cur_dog_size, cur_dog_size), fill=255)
        
        img.paste(dog_resized, (dog_cx - cur_dog_size // 2, dog_cy - cur_dog_size // 2), mask)

        # Badge pill above title
        badge_text = "OFFICIAL DISCORD BOT"
        draw.rounded_rectangle([232, 28, 385, 48], radius=6, fill=(40, 20, 70, 220), outline=(180, 80, 255, 180))
        draw.text((243, 31), badge_text, font=badge_font, fill=(230, 200, 255, 255))

        # Title: SHIZU MUSIC with neon glow / shimmer
        shimmer = int(255 * (0.85 + 0.15 * math.sin(angle_prog * 2)))
        # Shadow / glow
        draw.text((234, 53), "SHIZU MUSIC", font=title_font, fill=(180, 40, 255, 120))
        draw.text((232, 51), "SHIZU MUSIC", font=title_font, fill=(shimmer, 255, 255, 255))

        # Subtitle with animated music icon
        note_icon = "♪" if (frame_idx % 15 < 8) else "♫"
        sub_text = f"{note_icon} High-Fidelity 24/7 Discord Audio"
        draw.text((234, 114), sub_text, font=sub_font, fill=(200, 180, 240, 240))

        # Feature chips
        chip_y = 145
        chips = ["FFmpeg Engine", "Low Latency", "Audio FX", "Autoplay"]
        cur_chip_x = 234
        for chip in chips:
            bbox = draw.textbbox((0, 0), chip, font=badge_font)
            cw = bbox[2] - bbox[0] + 16
            draw.rounded_rectangle([cur_chip_x, chip_y, cur_chip_x + cw, chip_y + 20], radius=4, fill=(25, 20, 45, 200), outline=(80, 60, 140, 160))
            draw.text((cur_chip_x + 8, chip_y + 3), chip, font=badge_font, fill=(170, 160, 210, 220))
            cur_chip_x += cw + 8

        # Floating glowing sparks / particles across banner
        for sp in range(12):
            sp_x = (int((sp * 58) + progress * 60)) % W
            sp_y = int(40 + (sp * 17) % (H - 80) + 6 * math.sin(angle_prog + sp))
            sp_alpha = int(120 + 90 * math.sin(angle_prog * 3 + sp))
            col = (0, 245, 255, sp_alpha) if sp % 2 == 0 else (255, 120, 230, sp_alpha)
            draw.ellipse((sp_x - 2, sp_y - 2, sp_x + 2, sp_y + 2), fill=col)

        frames.append(img.convert("P", palette=Image.Palette.ADAPTIVE))

    out_path = r"C:/Users/xdvip/Downloads/shizumusic-host/banner.gif"
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=50,  # 50ms per frame = 20 fps
        loop=0,
        optimize=True
    )
    print(f"Banner saved: {out_path} ({os.path.getsize(out_path)} bytes)")

generate_banner()
