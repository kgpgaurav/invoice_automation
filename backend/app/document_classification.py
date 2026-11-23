"""Conservative scan review detection, including raster pages with an OCR overlay."""

import pymupdf


def scan_pages(pdf):
    result = []
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        for index, page in enumerate(document, 1):
            bounds = page.rect
            rectangles = [pymupdf.Rect(info["bbox"]) & bounds for info in page.get_image_info()]
            rectangles = [r for r in rectangles if not r.is_empty]
            if not rectangles:
                continue
            if not page.get_text().strip() or len(rectangles) > 256:
                result.append(index)
                continue
            # Union area rather than adding overlapping logos/duplicate images.
            xs = sorted({r.x0 for r in rectangles} | {r.x1 for r in rectangles})
            area = 0
            for left, right in zip(xs, xs[1:]):
                intervals = sorted((r.y0, r.y1) for r in rectangles if r.x0 < right and r.x1 > left)
                end = -1
                height = 0
                for low, high in intervals:
                    height += max(0, high - max(low, end))
                    end = max(end, high)
                area += (right - left) * height
            if bounds.get_area() and area / bounds.get_area() >= 0.5:
                result.append(index)
    return tuple(result)
