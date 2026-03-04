"""
K-Robot 机内系统控件：屏幕处理
"""
import base64
from typing import Dict
import mss

class ScreenWatcher:
    """视觉感知器，负责极速捕获屏幕状态，以供大模型进行视觉决策"""
    
    def __init__(self):
        self.sct = mss.mss()
        
    def capture_screen_base64(self, monitor_index: int = 1) -> str:
        """
        截取指定显示器的全屏画面，并转换为 JPEG 格式的 Base64 编码字符串。
        :param monitor_index: 显示器索引，1 表示主显示器，0 表示所有显示器横跨
        :return: Base64 编码的图像字符串，适用于直接作为 data URI 传入大模型
        """
        monitor = self.sct.monitors[monitor_index]
        sct_img = self.sct.grab(monitor)
        
        # 将 mss 原始 BGRA 像素数据利用 mss.tools 或通过 PIL 转换，这里我们直接将其保存为 PNG 在内存中并转 Base64
        import io
        from PIL import Image
        
        # 将 sct_img (BGRA) 转为 PIL Image (RGB)，减小体积可以保存为 JPEG
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        # ======== 新增: 绘制辅助坐标网格 (Set-of-Mark) ========
        # VLM 很难在极大的画面中凭空精确定位像素，画上网格线和刻度能极大提升坐标输出准确率
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        width, height = img.size
        grid_size = 100 # 每 100 像素画一条线
        
        # 为了不遮挡太多内容，使用红色细线
        line_color = (255, 0, 0, 128)
        text_color = (255, 255, 0) # 黄色文字高亮
        
        # 尝试加载默认字体，如果没有则使用基础字体
        try:
            # 尝试在 Windows 下加载稍微大一点的字体以保证缩放后可见
            font = ImageFont.truetype("arial.ttf", 15)
        except IOError:
            font = ImageFont.load_default()

        # 画垂直线和 X 坐标标尺 (在顶部和中间)
        for x in range(0, width, grid_size):
            draw.line([(x, 0), (x, height)], fill=line_color, width=1)
            draw.text((x + 2, 2), str(x), fill=text_color, font=font)
            # 在屏幕中间也标记一下，防止长条形控件遮挡
            draw.text((x + 2, height // 2), str(x), fill=text_color, font=font)

        # 画水平线和 Y 坐标标尺 (在左侧和中间)
        for y in range(0, height, grid_size):
            draw.line([(0, y), (width, y)], fill=line_color, width=1)
            # 避免和 X=0 的字体重叠，Y刻度稍微往下挪一点
            if y != 0: 
                draw.text((2, y + 2), str(y), fill=text_color, font=font)
            # 在中间也打个标签
            draw.text((width // 2, y + 2), str(y), fill=text_color, font=font)
        # =======================================================
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return img_base64

    def get_screen_size(self, monitor_index: int = 1) -> Dict[str, int]:
        """
        获取屏幕分辨率大小，后续帮助大模型在归一化坐标(如 0~1000)和真实坐标间换算时提供参考。
        """
        monitor = self.sct.monitors[monitor_index]
        return {
            "width": monitor["width"],
            "height": monitor["height"]
        }
