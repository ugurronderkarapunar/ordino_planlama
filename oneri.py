"""Akıllı öneri algoritması: izin boşluğunu dolduracak 5 yağcı adayı."""
from datetime import timedelta
import pandas as pd
from db import q, tr_upper


def kapsam(gunler, tip) -> set:
    """Vardiyaların kapladığı günler. Tip B: ertesi gün çıkış günü (boşta) -> o gün de dolu."""
    s = set()
    for d in gunler or []:
        s.add(d)
        if tip == "B":
            s.add(d + timedelta(days=1))
    return s


def adaylar(gemi: dict, gun, tip: str, haric_id: int, gevset: bool = False, n: int = 5) -> pd.DataFrame:
    c = q("SELECT id, sorunlu_yagcilar FROM carkcilar WHERE isim_soyisim=:a", a=gemi.get("carkci_adi") or "").to_dict("records")
    cid, c_sorunlu = (int(c[0]["id"]), set(c[0]["sorunlu_yagcilar"])) if c else (None, set())
    hedef = kapsam([gun], tip)
    izinli = set(q("SELECT personel_id FROM izinler WHERE baslangic_tarihi<=:b AND bitis_tarihi>=:a",
                   a=gun, b=max(hedef))["personel_id"].tolist())
    mak, out = tr_upper(gemi.get("makine_tipi")), []

    for p in q("SELECT * FROM personeller WHERE id<>:h", h=haric_id).to_dict("records"):
        if p["id"] in izinli or gun.weekday() == p["hafta_izni_gunu"]:               # Kriter 2: hafta izni / izinde
            continue
        if kapsam(p["vardiya_gunleri"], p["vardiya_tipi"]) & hedef:                  # Kriter 2: vardiya çakışması
            continue
        if (cid is not None and cid in p["sorunlu_kisiler"]) or p["id"] in c_sorunlu:  # Kriter 3: çarkçı sorunu
            continue
        bilir, calisti = mak in p["makine_bilgisi"], gemi["id"] in p["gecmis_gemiler"]  # Kriter 1: makine tecrübesi
        skor = 2 * bilir + calisti
        if skor or gevset:
            out.append(dict(id=int(p["id"]), isim=p["isim_soyisim"], tip=p["vardiya_tipi"], skor=skor,
                            neden=" · ".join(filter(None, ["Makineyi biliyor" if bilir else "", "Bu gemide çalışmış" if calisti else ""])) or "—"))
    cols = ["id", "isim", "tip", "skor", "neden"]
    return pd.DataFrame(out, columns=cols).sort_values("skor", ascending=False).head(n).reset_index(drop=True)
