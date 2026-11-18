"""Photo pool for profile/photo warming: real-looking images with phone-style EXIF.

Sources, in order:
1. ``data/photo_pool/*.jpg|png`` already seeded locally (best - operator supplied real photos);
2. one-time download from loremflickr (CC photos by keyword) when the pool is empty.

Every use produces a NEW derived file (random crop / flip / rotation + re-encode) so
Yelp cannot match the uploaded hash against the source (2026-11-09), and a source photo
is never reused by another account (usage ledger in ``data/photo_pool/usage.json``).
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from obs.log import get_logger

log = get_logger("photo_pool")

POOL_DIR = Path("data") / "photo_pool"
DERIVED_DIR = POOL_DIR / "derived"
USAGE_FILE = POOL_DIR / "usage.json"
FETCH_URL = "https://loremflickr.com/{w}/{h}/{keyword}"
PHONES = [("samsung", "SM-G991B"), ("Google", "Pixel 7"), ("Apple", "iPhone 13"), ("samsung", "SM-A536B")]


def _load_usage() -> dict[str, list[str]]:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_usage(usage: dict[str, list[str]]) -> None:
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = USAGE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(usage, indent=1), encoding="utf-8")
    tmp.replace(USAGE_FILE)


def _normalise(path: Path) -> Path:
    """Resize + stamp EXIF once; keep the same file if pillow is missing."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return path
    try:
        img = Image.open(path)
        img = img.convert("RGB")
        side = max(img.size)
        if side > 1600:
            scale = 1600 / side
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
        exif = img.getexif()
        make, model = random.choice(PHONES)
        exif[0x010F] = make
        exif[0x0110] = model
        shot = datetime.now() - timedelta(days=random.randint(0, 40), minutes=random.randint(0, 600))
        exif[0x0132] = shot.strftime("%Y:%m:%d %H:%M:%S")
        out = path.with_suffix(".jpg")
        img.save(out, "JPEG", quality=88, exif=exif)
        if out != path:
            path.unlink(missing_ok=True)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("photo_normalise_failed", path=str(path), error=str(exc)[:120])
        return path


def _derive(source: Path, *, gps_lat: float | None = None, gps_lon: float | None = None) -> Path | None:
    """Per-use transform: crop + flip + slight rotation, re-encoded as a new file.

    Batch 2: adds GPS EXIF tags when lat/lon provided (geo-tagged photos = trust signal).
    """
    try:
        from PIL import Image, ImageEnhance
    except Exception:  # noqa: BLE001
        return source
    try:
        img = Image.open(source).convert("RGB")
        w, h = img.size
        crop_x = int(w * random.uniform(0.03, 0.10))
        crop_y = int(h * random.uniform(0.03, 0.10))
        img = img.crop((crop_x, crop_y, w - crop_x, h - crop_y))
        if random.random() < 0.5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        img = img.rotate(random.uniform(-3.0, 3.0), resample=Image.BICUBIC, expand=False)
        img = ImageEnhance.Brightness(img).enhance(random.uniform(0.94, 1.06))
        img = ImageEnhance.Contrast(img).enhance(random.uniform(0.95, 1.08))

        exif = img.getexif()
        make, model = random.choice(PHONES)
        exif[0x010F] = make
        exif[0x0110] = model
        shot = datetime.now() - timedelta(days=random.randint(0, 30), minutes=random.randint(0, 600))
        exif[0x0132] = shot.strftime("%Y:%m:%d %H:%M:%S")

        # batch 2: GPS EXIF (trust signal - geo-tagged photos)
        if gps_lat is not None and gps_lon is not None:
            gps_ifd = _build_gps_exif(gps_lat, gps_lon)
            if gps_ifd:
                exif[0x8825] = gps_ifd  # GPSInfo tag

        DERIVED_DIR.mkdir(parents=True, exist_ok=True)
        out = DERIVED_DIR / f"{uuid.uuid4().hex}.jpg"
        img.save(out, "JPEG", quality=random.randint(84, 92), exif=exif)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("photo_derive_failed", source=str(source), error=str(exc)[:150])
        return None


def _build_gps_exif(lat: float, lon: float) -> dict | None:
    """Build GPS EXIF IFD from lat/lon. Returns None if PIL cannot construct it."""
    try:
        from PIL.ExifTags import GPS

        def _to_dms(decimal: float) -> tuple[int, int, float]:
            d = int(abs(decimal))
            m = int((abs(decimal) - d) * 60)
            s = (abs(decimal) - d - m / 60) * 3600
            return d, m, round(s, 4)

        lat_ref = "N" if lat >= 0 else "S"
        lon_ref = "E" if lon >= 0 else "W"
        lat_dms = _to_dms(lat)
        lon_dms = _to_dms(lon)

        gps = {}
        gps[GPS.GPSLatitudeRef] = lat_ref
        gps[GPS.GPSLatitude] = lat_dms
        gps[GPS.GPSLongitudeRef] = lon_ref
        gps[GPS.GPSLongitude] = lon_dms
        return gps
    except Exception:  # noqa: BLE001
        return None


def _fetch(keyword: str) -> Path | None:
    try:
        import httpx

        POOL_DIR.mkdir(parents=True, exist_ok=True)
        target = POOL_DIR / f"{keyword.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.jpg"
        response = httpx.get(
            FETCH_URL.format(w=1080, h=1440, keyword=keyword), follow_redirects=True, timeout=30
        )
        if response.status_code >= 400 or not response.content:
            log.warning("photo_fetch_failed", keyword=keyword, status=response.status_code)
            return None
        target.write_bytes(response.content)
        return _normalise(target)
    except Exception as exc:  # noqa: BLE001
        log.warning("photo_fetch_error", keyword=keyword, error=str(exc)[:120])
        return None


def _local_sources() -> list[Path]:
    if not POOL_DIR.exists():
        return []
    return [p for p in POOL_DIR.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]


def pick_photo(
    keyword: str = "restaurant food",
    *,
    account_tag: str | None = None,
    fetch: bool = True,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
) -> Path | None:
    """Return a NEW derived photo path, never one already used by another account.

    Batch 2: gps_lat/gps_lon tags the derived photo with GPS EXIF (trust signal).
    """
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    usage = _load_usage()

    def used_by_other(path: Path) -> bool:
        users = usage.get(path.name, [])
        return bool(account_tag) and any(tag != account_tag for tag in users)

    sources = [p for p in _local_sources() if p.suffix.lower() != ".json"]
    candidates = [p for p in sources if not used_by_other(p)]
    if not candidates and fetch:
        for kw in [keyword, "restaurant interior", "coffee shop", "storefront"]:
            for _ in range(2):
                path = _fetch(kw)
                if path is not None:
                    candidates.append(path)
            if candidates:
                break
    if not candidates:
        return None

    # prefer photos nobody used yet
    fresh = [p for p in candidates if not usage.get(p.name)]
    source = random.choice(fresh or candidates)
    usage.setdefault(source.name, [])
    if account_tag and account_tag not in usage[source.name]:
        usage[source.name].append(account_tag)
    _save_usage(usage)

    derived = _derive(source, gps_lat=gps_lat, gps_lon=gps_lon)
    return derived or source


def pick_avatar(*, account_tag: str | None = None) -> Path | None:
    """Portrait-ish image for the profile avatar (same ledger rules)."""
    return pick_photo("portrait person", account_tag=account_tag)
