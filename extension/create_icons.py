#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成浏览器扩展图标
"""
from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size, filename):
    """创建图标"""
    # 创建蓝色背景图标
    img = Image.new('RGBA', (size, size), (52, 152, 219, 255))
    draw = ImageDraw.Draw(img)

    # 添加文字
    text = 'T'
    try:
        # 尝试使用系统字体
        font_size = size // 2
        font = ImageFont.truetype('arial.ttf', font_size)
    except:
        font = ImageFont.load_default()

    # 居中文字
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (size - bbox[2]) // 2
    y = (size - bbox[3]) // 2 - size // 8
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    # 保存
    img.save(filename)
    print(f"Created: {filename}")

def main():
    # 创建图标目录
    chrome_icons = 'chrome/icons'
    edge_icons = 'edge/icons'

    # Chrome icons
    os.makedirs(chrome_icons, exist_ok=True)
    create_icon(16, os.path.join(chrome_icons, 'icon16.png'))
    create_icon(48, os.path.join(chrome_icons, 'icon48.png'))
    create_icon(128, os.path.join(chrome_icons, 'icon128.png'))

    # Edge icons (复制Chrome的)
    os.makedirs(edge_icons, exist_ok=True)
    for name in ['icon16.png', 'icon48.png', 'icon128.png']:
        src = os.path.join(chrome_icons, name)
        dst = os.path.join(edge_icons, name)
        if os.path.exists(src):
            import shutil
            shutil.copy(src, dst)
            print(f"Copied: {dst}")

if __name__ == '__main__':
    main()