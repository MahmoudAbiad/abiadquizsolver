import io
from PIL import Image, ImageDraw
from services.ai_service import SolvedQuestion

class ImageService:
    @staticmethod
    def annotate_image(image_bytes: bytes, solutions: list[SolvedQuestion]) -> bytes:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = img.size
        draw = ImageDraw.Draw(img)

        for item in solutions:
            ymin, xmin, ymax, xmax = item.box_2d
            
            abs_ymin = int((ymin / 1000) * height)
            abs_xmin = int((xmin / 1000) * width)
            abs_ymax = int((ymax / 1000) * height)
            abs_xmax = int((xmax / 1000) * width)

            center_x = (abs_xmin + abs_xmax) // 2
            center_y = (abs_ymin + abs_ymax) // 2
            radius = max(8, (abs_ymax - abs_ymin) // 3)

            # Draw green indicator
            draw.ellipse(
                [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
                fill=(46, 204, 113, 255),
                outline=(39, 174, 96, 255),
                width=2
            )

        watermark_text = "تم الحل بواسطة الذكاء الاصطناعي"
        draw.text((20, height - 35), watermark_text, fill=(120, 120, 120))

        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=95)
        return output_buffer.getvalue()
