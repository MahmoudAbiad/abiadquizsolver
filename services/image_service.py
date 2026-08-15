import io
import os
from PIL import Image, ImageDraw, ImageFont
from services.ai_service import SolvedQuestion

# خط يدعم اللغة العربية (Noto Naskh Arabic)، لأن الخط الافتراضي بمكتبة PIL
# ما بيدعم رسم الحروف العربية أصلاً (كان عم يطلع رموز مشوّهة بدل النص).
_FONT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "assets", "fonts", "NotoNaskhArabic-Regular.ttf"
)
_WATERMARK_FONT = ImageFont.truetype(_FONT_PATH, 20, layout_engine=ImageFont.Layout.RAQM)


class ImageService:
    @staticmethod
    def annotate_image(image_bytes: bytes, solutions: list[SolvedQuestion]) -> bytes:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        width, height = img.size

        # نرسم التمييز على طبقة شفافة منفصلة (overlay)، مشان نقدر نلوّن خلفية
        # نص-شفافة فوق كامل سطر الإجابة بدون ما نغطي النص الأصلي بالكامل
        # زي الدائرة المملوءة يلي كانت تغطي الحرف/الفقاعة قبل هيك.
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # هامش بسيط حوالين الصندوق يلي رجعه الموديل، مشان التمييز ما يلزق
        # بالنص مباشرة ويعطي مساحة تنفس بصرية
        padding = 6

        for item in solutions:
            ymin, xmin, ymax, xmax = item.box_2d

            abs_ymin = int((ymin / 1000) * height) - padding
            abs_xmin = int((xmin / 1000) * width) - padding
            abs_ymax = int((ymax / 1000) * height) + padding
            abs_xmax = int((xmax / 1000) * width) + padding

            # نحصر الإحداثيات جوا حدود الصورة، مشان ما نطلع برا الصورة
            abs_xmin = max(0, abs_xmin)
            abs_ymin = max(0, abs_ymin)
            abs_xmax = min(width, abs_xmax)
            abs_ymax = min(height, abs_ymax)

            if abs_xmax <= abs_xmin or abs_ymax <= abs_ymin:
                continue

            # تمييز خلفية شبه شفاف (النص الأصلي يضل مقروء تحته بالكامل)
            # + حدّ خارجي واضح يبيّن بداية ونهاية سطر الإجابة الصحيحة
            overlay_draw.rounded_rectangle(
                [abs_xmin, abs_ymin, abs_xmax, abs_ymax],
                radius=6,
                fill=(46, 204, 113, 90),
                outline=(39, 174, 96, 255),
                width=2,
            )

        img = Image.alpha_composite(img, overlay)

        draw = ImageDraw.Draw(img)
        watermark_text = "تم الحل بالذكاء الاصطناعي، وقد يحتوي على أخطاء، راجع الإجابات"
        draw.text(
            (20, height - 34),
            watermark_text,
            fill=(90, 90, 90, 255),
            font=_WATERMARK_FONT,
        )

        img = img.convert("RGB")
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=85)
        return output_buffer.getvalue()
