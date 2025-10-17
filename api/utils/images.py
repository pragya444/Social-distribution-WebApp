# api/utils/images.py
import base64
from io import BytesIO
from PIL import Image, UnidentifiedImageError, ImageOps

ALLOWED_FORMATS = {
    "PNG": "image/png;base64",
    "JPEG": "image/jpeg;base64",
    "JPG": "image/jpeg;base64",
}

def handle_uploaded_image(file_obj):
    """
    Validate an uploaded image, optionally transcode it, and return (content_type, base64_str).

    Rules:
    - Accept only PNG or JPEG outputs (content types are "image/png;base64" or "image/jpeg;base64").
    - If the source format isn't one of {PNG, JPEG, JPG}, transcode to PNG.
    - Bytes are base64-encoded (ASCII string) for transport.

    Raises:
    - ValueError if the file is not a valid image.
    """
    # try to rewind in case the caller already read some bytes
    try:
        file_obj.seek(0)
    except Exception:
        # not all file-like objects support seek; that's fine
        pass

    try:
        with Image.open(file_obj) as im:
            # fully decode now so we fail fast on broken/corrupt files
            im.load()

            # fix common camera rotations via exif (no effect if there’s no exif)
            im = ImageOps.exif_transpose(im)

            # pillow’s best guess of original format, e.g. "PNG", "JPEG"
            fmt = (im.format or "").upper()

            if fmt not in ALLOWED_FORMATS:
                # not png or jpeg? we standardize by converting to png
                target_fmt = "PNG"

                # if the image isn't already carrying alpha (transparency
                # get it into a plain rgb layout to avoid palette/bit-depth weirdness
                if im.mode not in ("RGBA", "LA") and (im.mode == "P" or "A" not in im.getbands()):
                    im = im.convert("RGB")

                # render the image into a memory buffer as png
                buf = BytesIO()
                # optimize is safe for png and gives smaller files
                im.save(buf, format=target_fmt, optimize=True)
                raw = buf.getvalue()
                content_type = ALLOWED_FORMATS[target_fmt]
            else:
                # already png or jpeg — just send the original bytes
                # (rewind again because Image.open advanced the stream)
                try:
                    file_obj.seek(0)
                except Exception:
                    # if we can't seek, read() will start wherever we are; most uploads are seekable
                    pass
                raw = file_obj.read()
                content_type = ALLOWED_FORMATS[fmt]

    except UnidentifiedImageError as e:
        # pillow couldn't recognize it as an image at all
        raise ValueError("Uploaded file is not a valid image.") from e

    # base64-encode the raw bytes so we can store/ship them as text
    b64 = base64.b64encode(raw).decode("ascii")

    # callers get a mime-ish content type with ;base64 and the ascii payload
    return content_type, b64
