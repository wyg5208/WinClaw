"""WinClaw LOGO 生成脚本 - 生成三个不同风格的应用图标"""

from PIL import Image, ImageDraw, ImageFont
import math
import os

# 确保输出目录存在
os.makedirs('resources/icons', exist_ok=True)


def create_gradient_background(size, color1, color2, direction='diagonal'):
    """创建渐变背景"""
    img = Image.new('RGB', size)
    draw = ImageDraw.Draw(img)
    w, h = size
    
    for y in range(h):
        for x in range(w):
            if direction == 'diagonal':
                ratio = (x + y) / (w + h)
            elif direction == 'vertical':
                ratio = y / h
            else:
                ratio = x / w
            
            r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
            g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
            b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
            draw.point((x, y), fill=(r, g, b))
    
    return img


def add_rounded_corners(img, radius):
    """添加圆角"""
    circle = Image.new('L', (radius * 2, radius * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, radius * 2, radius * 2), fill=255)
    
    alpha = Image.new('L', img.size, 255)
    w, h = img.size
    
    # 四个角
    alpha.paste(circle.crop((0, 0, radius, radius)), (0, 0))
    alpha.paste(circle.crop((radius, 0, radius * 2, radius)), (w - radius, 0))
    alpha.paste(circle.crop((0, radius, radius, radius * 2)), (0, h - radius))
    alpha.paste(circle.crop((radius, radius, radius * 2, radius * 2)), (w - radius, h - radius))
    
    img.putalpha(alpha)
    return img


# ========== LOGO 1: 厚重W字母 - 力量风格 ==========
def create_logo1():
    """厚重W字母 - 粗犷力量感"""
    size = 512
    img = create_gradient_background((size, size), (0, 100, 200), (0, 60, 130), 'diagonal')
    draw = ImageDraw.Draw(img)
    
    center_x, center_y = size // 2, size // 2
    
    # 超粗W字母 - 使用多边形绘制厚重感
    line_width = 75  # 加粗线条
    color = (255, 255, 255)
    
    # W的主体 - 使用填充多边形而非线条
    w_points = [
        # 左侧外轮廓
        (center_x - 160, center_y - 140),  # 左上外
        (center_x - 85, center_y - 140),   # 左上内
        (center_x - 50, center_y - 20),    # 左中内
        (center_x - 15, center_y - 140),   # 中左内
        (center_x + 15, center_y - 140),   # 中右内
        (center_x + 50, center_y - 20),    # 右中内
        (center_x + 85, center_y - 140),   # 右上内
        (center_x + 160, center_y - 140),  # 右上外
        (center_x + 110, center_y + 140),  # 右下外
        (center_x + 50, center_y + 140),   # 右下内
        (center_x, center_y + 20),         # 中底
        (center_x - 50, center_y + 140),   # 左下内
        (center_x - 110, center_y + 140),  # 左下外
    ]
    
    draw.polygon(w_points, fill=color)
    
    # 添加粗边框强调
    border_points = [
        (center_x - 165, center_y - 145),
        (center_x - 115, center_y + 145),
        (center_x - 45, center_y + 145),
        (center_x, center_y + 30),
        (center_x + 45, center_y + 145),
        (center_x + 115, center_y + 145),
        (center_x + 165, center_y - 145),
    ]
    
    # 中心AI核心 - 粗圆环
    core_radius = 55
    draw.ellipse(
        (center_x - core_radius, center_y - core_radius - 10,
         center_x + core_radius, center_y + core_radius - 10),
        fill=(0, 100, 200)
    )
    # 内圆
    inner_r = 30
    draw.ellipse(
        (center_x - inner_r, center_y - inner_r - 10,
         center_x + inner_r, center_y + inner_r - 10),
        fill=(100, 180, 255)
    )
    
    img = add_rounded_corners(img, 80)
    img.save('resources/icons/logo1_bold_w.png')
    print('Logo 1 已生成: 厚重W字母 - 力量风格')


# ========== LOGO 2: 立体W字母 - 3D厚重感 ==========
def create_logo2():
    """立体W字母 - 3D厚重效果"""
    size = 512
    img = create_gradient_background((size, size), (120, 50, 180), (70, 20, 110), 'diagonal')
    draw = ImageDraw.Draw(img)
    
    center_x, center_y = size // 2, size // 2
    
    # 3D阴影层 - 先画阴影
    shadow_offset = 12
    shadow_color = (40, 10, 70)
    
    shadow_points = [
        (center_x - 150 + shadow_offset, center_y - 130 + shadow_offset),
        (center_x - 80 + shadow_offset, center_y - 130 + shadow_offset),
        (center_x - 45 + shadow_offset, center_y - 10 + shadow_offset),
        (center_x - 10 + shadow_offset, center_y - 130 + shadow_offset),
        (center_x + 10 + shadow_offset, center_y - 130 + shadow_offset),
        (center_x + 45 + shadow_offset, center_y - 10 + shadow_offset),
        (center_x + 80 + shadow_offset, center_y - 130 + shadow_offset),
        (center_x + 150 + shadow_offset, center_y - 130 + shadow_offset),
        (center_x + 100 + shadow_offset, center_y + 130 + shadow_offset),
        (center_x + 45 + shadow_offset, center_y + 130 + shadow_offset),
        (center_x + shadow_offset, center_y + 15 + shadow_offset),
        (center_x - 45 + shadow_offset, center_y + 130 + shadow_offset),
        (center_x - 100 + shadow_offset, center_y + 130 + shadow_offset),
    ]
    draw.polygon(shadow_points, fill=shadow_color)
    
    # 主W体 - 超厚重
    main_color = (255, 255, 255)
    highlight_color = (230, 230, 255)
    
    # 主体W
    w_points = [
        (center_x - 150, center_y - 130),
        (center_x - 80, center_y - 130),
        (center_x - 45, center_y - 10),
        (center_x - 10, center_y - 130),
        (center_x + 10, center_y - 130),
        (center_x + 45, center_y - 10),
        (center_x + 80, center_y - 130),
        (center_x + 150, center_y - 130),
        (center_x + 100, center_y + 130),
        (center_x + 45, center_y + 130),
        (center_x, center_y + 15),
        (center_x - 45, center_y + 130),
        (center_x - 100, center_y + 130),
    ]
    draw.polygon(w_points, fill=main_color)
    
    # 高光层 - 增加立体感
    highlight_points = [
        (center_x - 130, center_y - 110),
        (center_x - 90, center_y - 110),
        (center_x - 60, center_y - 20),
        (center_x - 25, center_y - 110),
        (center_x - 5, center_y - 110),
        (center_x + 25, center_y - 20),
        (center_x + 60, center_y - 110),
        (center_x + 100, center_y - 110),
        (center_x + 70, center_y + 80),
        (center_x + 35, center_y + 80),
        (center_x, center_y - 5),
        (center_x - 35, center_y + 80),
        (center_x - 70, center_y + 80),
    ]
    draw.polygon(highlight_points, fill=highlight_color)
    
    # 中心装饰 - 粗圆环
    ring_r = 50
    draw.ellipse(
        (center_x - ring_r, center_y - ring_r - 5,
         center_x + ring_r, center_y + ring_r - 5),
        outline=(120, 50, 180), width=10
    )
    
    img = add_rounded_corners(img, 80)
    img.save('resources/icons/logo2_3d_w.png')
    print('Logo 2 已生成: 立体W字母 - 3D厚重感')


# ========== LOGO 3: W字母 + 爪痕融合 ==========
def create_logo3():
    """W字母与爪痕融合 - 粗犷抓痕风格"""
    size = 512
    img = create_gradient_background((size, size), (180, 60, 40), (130, 35, 20), 'diagonal')
    draw = ImageDraw.Draw(img)
    
    center_x, center_y = size // 2, size // 2
    
    # 超厚重W主体 - 填充多边形
    w_color = (255, 255, 255)
    w_points = [
        (center_x - 170, center_y - 150),  # 左上外
        (center_x - 90, center_y - 150),   # 左上内
        (center_x - 55, center_y - 30),    # 左中内
        (center_x - 20, center_y - 150),   # 中左内
        (center_x + 20, center_y - 150),   # 中右内
        (center_x + 55, center_y - 30),    # 右中内
        (center_x + 90, center_y - 150),   # 右上内
        (center_x + 170, center_y - 150),  # 右上外
        (center_x + 115, center_y + 150),  # 右下外
        (center_x + 55, center_y + 150),   # 右下内
        (center_x, center_y + 30),         # 中底
        (center_x - 55, center_y + 150),   # 左下内
        (center_x - 115, center_y + 150),  # 左下外
    ]
    draw.polygon(w_points, fill=w_color)
    
    # 添加三道爪痕 - 斜向抓痕效果
    claw_color = (180, 60, 40)
    claw_width = 18
    
    # 左爪痕
    draw.polygon([
        (center_x - 80, center_y - 80),
        (center_x - 65, center_y - 80),
        (center_x - 35, center_y + 60),
        (center_x - 50, center_y + 60),
    ], fill=claw_color)
    
    # 中爪痕
    draw.polygon([
        (center_x - 10, center_y - 60),
        (center_x + 5, center_y - 60),
        (center_x + 25, center_y + 80),
        (center_x + 10, center_y + 80),
    ], fill=claw_color)
    
    # 右爪痕
    draw.polygon([
        (center_x + 50, center_y - 80),
        (center_x + 65, center_y - 80),
        (center_x + 95, center_y + 60),
        (center_x + 80, center_y + 60),
    ], fill=claw_color)
    
    # 底部装饰 - 粗边框圆环
    ring_r = 45
    draw.ellipse(
        (center_x - ring_r, center_y + 60,
         center_x + ring_r, center_y + 150),
        outline=claw_color, width=12
    )
    
    img = add_rounded_corners(img, 80)
    img.save('resources/icons/logo3_w_claw.png')
    print('Logo 3 已生成: W字母 + 爪痕融合')


if __name__ == "__main__":
    # 生成所有LOGO
    create_logo1()
    create_logo2()
    create_logo3()
    print('\n所有LOGO已生成到 resources/icons/ 目录')
