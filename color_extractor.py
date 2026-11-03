from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import Qt

def extract_dominant_color(thumb_bytes: bytes) -> QColor:
    if not thumb_bytes:
        return QColor(255, 255, 255)
    
    img = QImage()
    if not img.loadFromData(thumb_bytes) or img.isNull():
        return QColor(255, 255, 255)
    
    # Scale down to 24x24 for instant, zero-lag sampling
    small = img.scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    
    max_sat = 0
    best_color = QColor(255, 255, 255)
    r_sum, g_sum, b_sum = 0.0, 0.0, 0.0
    total_w = 0.0
    
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            r, g, b = c.red(), c.green(), c.blue()
            
            brightness = (r + g + b) / 3.0
            if brightness < 25:
                continue
                
            sat = max(r, g, b) - min(r, g, b)
            weight = (sat + 1.0) * (1.0 + brightness / 255.0)
            
            if sat > max_sat and 35 < brightness < 235:
                max_sat = sat
                best_color = c
                
            r_sum += r * weight
            g_sum += g * weight
            b_sum += b * weight
            total_w += weight

    if max_sat > 30:
        # Boost luminance to produce a bright glowing edge light
        h, s, v, _ = best_color.getHsv()
        v = max(v, 220)
        s = min(s, 210)
        return QColor.fromHsv(h, s, v)
    elif total_w > 0:
        avg_r = int(r_sum / total_w)
        avg_g = int(g_sum / total_w)
        avg_b = int(b_sum / total_w)
        return QColor(avg_r, avg_g, avg_b)
    
    return QColor(255, 255, 255)
