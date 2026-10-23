"""Ordino Yönetim — Streamlit + Neon PostgreSQL."""
from datetime import date, timedelta
from math import ceil
import pandas as pd
import streamlit as st
from db import init_db, q, run, tx, tr_upper
from oneri import adaylar

st.set_page_config(page_title="Ordino Yönetim", page_icon="⚓", layout="wide")
st.markdown("<style>[data-testid='stVerticalBlockBorderWrapper']{border-radius:14px}</style>", unsafe_allow_html=True)

GUN = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
TIP = {"A": "Tip A · 08:00–17:00", "B": "Tip B · Tam vardiya (08:00→08:00)"}
GEMI_TIP = {"tersanede": "🛠️ Tersanede", "disarida": "🌊 Dışarıda"}
TR = lambda d: d.strftime("%d.%m.%Y")


# ---------- yardımcılar ----------
def liste(s): return [x.strip() for x in s.split(",") if x.strip()]


def sozluk(table, col="isim_soyisim"):
    df = q(f"SELECT id, {col} FROM {table} ORDER BY {col}")
    return dict(zip(df["id"].tolist(), df[col].tolist()))


def kaydet(sql, msg, **p):
    """Yazma işlemi: hata göster, başarıda mesajla yeniden yükle."""
    try:
        run(sql, **p)
    except Exception as e:
        st.error(f"İşlem başarısız: {str(e).splitlines()[0]}")
        return
    st.session_state["flash"] = msg
    st.rerun()


def vardiya_hatalari(gunler, tip, izin_gunu):
    h = []
    if len(set(gunler)) < len(gunler): h.append("Aynı gün birden fazla girilmiş.")
    if any(g.weekday() == izin_gunu for g in gunler): h.append(f"Hafta izni günü ({GUN[izin_gunu]}) bir vardiyaya denk geliyor.")
    if tip == "B" and any(g + timedelta(days=1) in gunler for g in gunler):
        h.append("Tip B'de çıkış günü boşta kalmalı: ardışık günlere vardiya yazılamaz (48 saat kuralı).")
    return h


# ---------- sayfalar ----------
def ana():
    st.title("⚓ Genel Bakış")
    m = q("""SELECT (SELECT count(*) FROM personeller) y,
                    (SELECT count(*) FROM gemiler WHERE tip='tersanede') t,
                    (SELECT count(*) FROM gemiler WHERE tip='disarida') d,
                    (SELECT count(*) FROM izinler WHERE CURRENT_DATE BETWEEN baslangic_tarihi AND bitis_tarihi) i""").iloc[0]
    for col, (lbl, v) in zip(st.columns(4), [("Yağcı", m.y), ("Tersanede gemi", m.t), ("Dışarıda gemi", m.d), ("Bugün izinde", m.i)]):
        col.metric(lbl, int(v), border=True)
    st.subheader("Yaklaşan / aktif izinler")
    st.dataframe(q("""SELECT p.isim_soyisim AS "Yağcı", i.baslangic_tarihi AS "Başlangıç", i.bitis_tarihi AS "Bitiş",
                      i.toplam_vardiya_sayisi AS "Vardiya" FROM izinler i JOIN personeller p ON p.id=i.personel_id
                      WHERE i.bitis_tarihi >= CURRENT_DATE ORDER BY i.baslangic_tarihi LIMIT 15"""), hide_index=True, use_container_width=True)


def personel_formu(key, carkcilar, gemiler, r=None):
    with st.form(key, clear_on_submit=r is None):
        isim = st.text_input("İsim Soyisim (otomatik BÜYÜK harf)", r["isim_soyisim"] if r else "")
        c1, c2 = st.columns(2)
        tip = c1.radio("Vardiya tipi", list(TIP), format_func=TIP.get, index=list(TIP).index(r["vardiya_tipi"]) if r else 0)
        izin = c2.selectbox("Hafta izni günü", range(7), index=int(r["hafta_izni_gunu"]) if r else 6, format_func=GUN.__getitem__)
        mak = st.text_input("Makine bilgisi (virgülle ayır)", ", ".join(r["makine_bilgisi"]) if r else "")
        sor = st.multiselect("Sorunlu çarkçılar", list(carkcilar), format_func=carkcilar.get,
                             default=[x for x in (r["sorunlu_kisiler"] if r else []) if x in carkcilar])
        ges = st.multiselect("Geçmiş gemiler", list(gemiler), format_func=gemiler.get,
                             default=[x for x in (r["gecmis_gemiler"] if r else []) if x in gemiler])
        ok = st.form_submit_button("Kaydet", type="primary")
    return ok, dict(isim_soyisim=tr_upper(isim), vardiya_tipi=tip, hafta_izni_gunu=izin,
                    makine_bilgisi=[tr_upper(x) for x in liste(mak)], sorunlu_kisiler=sor, gecmis_gemiler=ges)


def yagcilar():
    st.title("🧑‍🔧 Yağcı Yönetimi")
    df = q("SELECT * FROM personeller ORDER BY isim_soyisim")
    recs = {r["id"]: r for r in df.to_dict("records")}
    carkcilar, gemiler = sozluk("carkcilar"), sozluk("gemiler", "ad")
    t1, t2, t3, t4 = st.tabs(["📋 Liste", "➕ Ekle", "✏️ Düzenle / Sil", "📅 Vardiya Takvimi"])

    with t1:
        if df.empty: st.info("Henüz yağcı yok.")
        else:
            v = df[["isim_soyisim", "vardiya_tipi", "hafta_izni_gunu", "makine_bilgisi"]].copy()
            v["hafta_izni_gunu"] = v["hafta_izni_gunu"].map(lambda i: GUN[i])
            v["makine_bilgisi"] = v["makine_bilgisi"].map(", ".join)
            st.dataframe(v.rename(columns={"isim_soyisim": "İsim", "vardiya_tipi": "Tip", "hafta_izni_gunu": "Hafta izni", "makine_bilgisi": "Makine"}),
                         hide_index=True, use_container_width=True)
    with t2:
        ok, v = personel_formu("ekle", carkcilar, gemiler)
        if ok:
            if not v["isim_soyisim"]: st.warning("İsim zorunlu.")
            else: kaydet("""INSERT INTO personeller (isim_soyisim,vardiya_tipi,hafta_izni_gunu,makine_bilgisi,sorunlu_kisiler,gecmis_gemiler)
                            VALUES (:isim_soyisim,:vardiya_tipi,:hafta_izni_gunu,:makine_bilgisi,:sorunlu_kisiler,:gecmis_gemiler)""",
                         f"{v['isim_soyisim']} eklendi", **v)
    with t3:
        if recs:
            pid = st.selectbox("Yağcı seç", list(recs), format_func=lambda i: recs[i]["isim_soyisim"], key="duz_sec")
            ok, v = personel_formu(f"duz{pid}", carkcilar, gemiler, recs[pid])
            if ok: kaydet("""UPDATE personeller SET isim_soyisim=:isim_soyisim, vardiya_tipi=:vardiya_tipi, hafta_izni_gunu=:hafta_izni_gunu,
                             makine_bilgisi=:makine_bilgisi, sorunlu_kisiler=:sorunlu_kisiler, gecmis_gemiler=:gecmis_gemiler WHERE id=:id""",
                          "Güncellendi", id=pid, **v)
            with st.expander("🗑️ Sil"):
                if st.checkbox("Bu yağcıyı (izin ve bildirim kayıtlarıyla) silmek istediğimi onaylıyorum", key=f"onay{pid}"):
                    if st.button("Kalıcı olarak sil", type="primary"):
                        tx(("UPDATE carkcilar SET sorunlu_yagcilar=array_remove(sorunlu_yagcilar,:i)", dict(i=pid)),
                           ("DELETE FROM personeller WHERE id=:i", dict(i=pid)))
                        st.session_state["flash"] = "Silindi"; st.rerun()
    with t4:
        if recs:
            pid = st.selectbox("Yağcı seç", list(recs), format_func=lambda i: recs[i]["isim_soyisim"], key="vard_sec")
            r = recs[pid]
            st.caption(f"{TIP[r['vardiya_tipi']]} · Hafta izni: {GUN[r['hafta_izni_gunu']]} · 1 vardiya = 2 gün")
            ed = st.data_editor(pd.DataFrame({"gun": pd.to_datetime(sorted(r["vardiya_gunleri"]))}), num_rows="dynamic", hide_index=True, key=f"ve{pid}",
                                column_config={"gun": st.column_config.DateColumn("Vardiya günü", format="DD.MM.YYYY", required=True)})
            gunler = sorted({pd.Timestamp(x).date() for x in ed["gun"].dropna()})
            hatalar = vardiya_hatalari(gunler, r["vardiya_tipi"], r["hafta_izni_gunu"])
            for h in hatalar: st.error(h)
            st.caption(f"Toplam: {len(gunler)} vardiya")
            if st.button("Vardiyaları kaydet", type="primary", disabled=bool(hatalar)):
                kaydet("UPDATE personeller SET vardiya_gunleri=:v WHERE id=:id", "Vardiyalar kaydedildi", v=gunler, id=pid)


def gemiler_sayfa():
    st.title("🚢 Gemi Yönetimi")
    df = q("SELECT * FROM gemiler ORDER BY ad")
    carkcilar = sozluk("carkcilar")
    with st.expander("➕ Yeni gemi"):
        with st.form("gemi_ekle", clear_on_submit=True):
            c1, c2 = st.columns(2)
            ad, mak = c1.text_input("Gemi adı"), c2.text_input("Makine tipi")
            kap, cark = c1.text_input("Kaptan adı"), c2.selectbox("Çarkçı", [""] + list(carkcilar.values()))
            tip = st.radio("Konum", list(GEMI_TIP), format_func=GEMI_TIP.get, horizontal=True)
            if st.form_submit_button("Ekle", type="primary"):
                if not ad.strip(): st.warning("Gemi adı zorunlu.")
                else: kaydet("INSERT INTO gemiler (ad,tip,makine_tipi,kaptan_adi,carkci_adi) VALUES (:a,:t,:m,:k,:c)", "Gemi eklendi",
                             a=tr_upper(ad), t=tip, m=tr_upper(mak) or None, k=tr_upper(kap) or None, c=cark or None)
    for tab, tip in zip(st.tabs(list(GEMI_TIP.values())), GEMI_TIP):
        with tab:
            sub = df[df.tip == tip].to_dict("records")
            if not sub: st.info("Bu kategoride gemi yok.")
            for row in range(0, len(sub), 3):
                for col, g in zip(st.columns(3), sub[row:row + 3]):
                    with col.container(border=True):
                        st.subheader(g["ad"])
                        st.caption(f"⚙️ {g['makine_tipi'] or '—'}  \n👨‍✈️ Kaptan: {g['kaptan_adi'] or '—'}  \n🔧 Çarkçı: {g['carkci_adi'] or '—'}")
                        b1, b2 = st.columns(2)
                        yeni = "disarida" if tip == "tersanede" else "tersanede"
                        if b1.button("↔️ " + GEMI_TIP[yeni].split(" ", 1)[1], key=f"mv{g['id']}"):
                            kaydet("UPDATE gemiler SET tip=:t WHERE id=:id", "Konum güncellendi", t=yeni, id=g["id"])
                        if b2.button("🗑️ Sil", key=f"dl{g['id']}"):
                            tx(("UPDATE personeller SET gecmis_gemiler=array_remove(gecmis_gemiler,:i)", dict(i=g["id"])),
                               ("DELETE FROM gemiler WHERE id=:i", dict(i=g["id"])))
                            st.session_state["flash"] = "Gemi silindi"; st.rerun()


def carkcilar_sayfa():
    st.title("🔧 Çarkçılar")
    df = q("SELECT * FROM carkcilar ORDER BY isim_soyisim")
    gemiler, yagcilar_ = sozluk("gemiler", "ad"), sozluk("personeller")
    if not df.empty:
        st.dataframe(df.assign(calistigi_gemiler=df.calistigi_gemiler.map(lambda l: ", ".join(gemiler.get(i, "?") for i in l)),
                               sorunlu_yagcilar=df.sorunlu_yagcilar.map(lambda l: ", ".join(yagcilar_.get(i, "?") for i in l))).drop(columns="id")
                     .rename(columns={"isim_soyisim": "İsim", "calistigi_gemiler": "Çalıştığı gemiler", "sorunlu_yagcilar": "Sorunlu yağcılar"}),
                     hide_index=True, use_container_width=True)
    with st.form("cark_ekle", clear_on_submit=True):
        isim = st.text_input("İsim Soyisim")
        cg = st.multiselect("Çalıştığı gemiler", list(gemiler), format_func=gemiler.get)
        sy = st.multiselect("Sorunlu yağcılar", list(yagcilar_), format_func=yagcilar_.get)
        if st.form_submit_button("Çarkçı ekle", type="primary"):
            if not isim.strip(): st.warning("İsim zorunlu.")
            else: kaydet("INSERT INTO carkcilar (isim_soyisim,calistigi_gemiler,sorunlu_yagcilar) VALUES (:n,:g,:s)", "Çarkçı eklendi", n=tr_upper(isim), g=cg, s=sy)
    if not df.empty:
        with st.expander("🗑️ Çarkçı sil"):
            d = dict(zip(df.id.tolist(), df.isim_soyisim.tolist()))
            cid = st.selectbox("Çarkçı", list(d), format_func=d.get)
            if st.button("Sil"):
                tx(("UPDATE personeller SET sorunlu_kisiler=array_remove(sorunlu_kisiler,:i)", dict(i=cid)),
                   ("UPDATE gemiler SET carkci_adi=NULL WHERE carkci_adi=:n", dict(n=d[cid])),
                   ("DELETE FROM carkcilar WHERE id=:i", dict(i=cid)))
                st.session_state["flash"] = "Çarkçı silindi"; st.rerun()


def izinler_sayfa():
    st.title("🏖️ İzinler")
    yag = sozluk("personeller")
    with st.form("izin_ekle", clear_on_submit=True):
        pid = st.selectbox("Yağcı", list(yag), format_func=yag.get) if yag else None
        aralik = st.date_input("İzin aralığı", value=(date.today(), date.today() + timedelta(days=1)), format="DD.MM.YYYY")
        if st.form_submit_button("İzin ekle", type="primary"):
            if pid is None or len(aralik) != 2: st.warning("Yağcı ve başlangıç–bitiş tarihi seçin.")
            else:
                b, e = aralik
                if not q("SELECT 1 FROM izinler WHERE personel_id=:p AND baslangic_tarihi<=:e AND bitis_tarihi>=:b", p=pid, b=b, e=e).empty:
                    st.error("Bu aralıkta zaten izin kaydı var.")
                else:
                    kaydet("INSERT INTO izinler (personel_id,baslangic_tarihi,bitis_tarihi,toplam_vardiya_sayisi) VALUES (:p,:b,:e,:t)",
                           "İzin kaydedildi", p=pid, b=b, e=e, t=ceil(((e - b).days + 1) / 2))   # 1 vardiya = 2 gün
    df = q("""SELECT i.id, p.isim_soyisim AS "Yağcı", i.baslangic_tarihi AS "Başlangıç", i.bitis_tarihi AS "Bitiş",
              i.toplam_vardiya_sayisi AS "Vardiya" FROM izinler i JOIN personeller p ON p.id=i.personel_id ORDER BY i.baslangic_tarihi DESC""")
    if not df.empty:
        df.insert(0, "Sil", False)
        ed = st.data_editor(df, hide_index=True, use_container_width=True, column_config={"id": None}, disabled=[c for c in df if c != "Sil"])
        if ed["Sil"].any() and st.button("Seçilenleri sil"):
            kaydet("DELETE FROM izinler WHERE id = ANY(:ids)", "İzin(ler) silindi", ids=ed.loc[ed["Sil"], "id"].astype(int).tolist())


def oneri_sayfa():
    st.title("🤝 Akıllı Yerine Görevlendirme")
    iz = {r["id"]: r for r in q("""SELECT i.id, i.personel_id, p.isim_soyisim, p.vardiya_tipi, i.baslangic_tarihi, i.bitis_tarihi
                                    FROM izinler i JOIN personeller p ON p.id=i.personel_id WHERE i.bitis_tarihi>=CURRENT_DATE
                                    ORDER BY i.baslangic_tarihi""").to_dict("records")}
    gem = {r["id"]: r for r in q("SELECT * FROM gemiler ORDER BY ad").to_dict("records")}
    if not iz or not gem: return st.info("Önce en az bir gemi ve güncel/gelecek bir izin kaydı gerekli.")
    c1, c2, c3 = st.columns(3)
    iid = c1.selectbox("İzin havuzu", list(iz), format_func=lambda i: f"{iz[i]['isim_soyisim']} · {TR(iz[i]['baslangic_tarihi'])}–{TR(iz[i]['bitis_tarihi'])}")
    z = iz[iid]
    gid = c2.selectbox("Gemi", list(gem), format_func=lambda i: gem[i]["ad"])
    gun = c3.selectbox("Kapatılacak gün", pd.date_range(z["baslangic_tarihi"], z["bitis_tarihi"]).date.tolist(), format_func=TR)
    st.caption(f"Yerine bakılacak: **{z['isim_soyisim']}** · {TIP[z['vardiya_tipi']]} · Çarkçı: {gem[gid]['carkci_adi'] or '—'}")
    gevset = st.checkbox("Makine/gemi tecrübesi şartını gevşet (Kriter 1)")
    if st.button("Aday öner", type="primary"):
        st.session_state["oneri"] = dict(df=adaylar(gem[gid], gun, z["vardiya_tipi"], z["personel_id"], gevset), gid=gid, gun=gun, z=z)
    o = st.session_state.get("oneri")
    if o:
        if o["df"].empty: return st.warning("Uygun aday bulunamadı. Şartı gevşetmeyi deneyin.")
        d = o["df"].set_index("id")
        sec = st.radio("Bir aday seçin", d.index.tolist(), format_func=lambda i: f"{d.loc[i, 'isim']} — {d.loc[i, 'neden']} (Tip {d.loc[i, 'tip']})")
        if st.button("✅ Görevlendir ve bildir"):
            g, zz = gem[o["gid"]], o["z"]
            cid = q("SELECT id FROM carkcilar WHERE isim_soyisim=:a", a=g["carkci_adi"] or "")["id"].tolist()
            mesaj = f"{d.loc[sec, 'isim']}, {g['ad']} gemisinde {TR(o['gun'])} tarihli vardiyada {zz['isim_soyisim']} yerine görevlendirildi."
            tx(("UPDATE personeller SET vardiya_gunleri=array_append(vardiya_gunleri,:d), gecmis_gemiler=CASE WHEN :g=ANY(gecmis_gemiler) THEN gecmis_gemiler ELSE array_append(gecmis_gemiler,:g) END WHERE id=:p",
                dict(d=o["gun"], g=g["id"], p=int(sec))),
               ("INSERT INTO bildirimler (personel_id,carkci_id,mesaj) VALUES (:p,:c,:m)", dict(p=int(sec), c=cid[0] if cid else None, m=mesaj)))
            st.session_state.pop("oneri"); st.session_state["flash"] = "Görevlendirme yapıldı, bildirim kaydedildi"; st.rerun()


def bildirimler_sayfa():
    st.title("🔔 Bildirim Kayıtları")
    st.dataframe(q("""SELECT b.tarih AS "Tarih", p.isim_soyisim AS "Yağcı", c.isim_soyisim AS "Çarkçı", b.mesaj AS "Mesaj"
                      FROM bildirimler b LEFT JOIN personeller p ON p.id=b.personel_id LEFT JOIN carkcilar c ON c.id=b.carkci_id
                      ORDER BY b.tarih DESC LIMIT 200"""), hide_index=True, use_container_width=True)


# ---------- giriş ----------
if "DATABASE_URL" not in st.secrets:
    st.error("`DATABASE_URL` bulunamadı. `.streamlit/secrets.toml` dosyasını oluşturun (örnek: secrets.toml.example).")
    st.stop()
init_db()
if msg := st.session_state.pop("flash", None): st.toast(msg, icon="✅")
st.navigation([st.Page(ana, title="Genel Bakış", icon="📊", default=True),
               st.Page(yagcilar, title="Yağcılar", icon="🧑‍🔧"),
               st.Page(gemiler_sayfa, title="Gemiler", icon="🚢"),
               st.Page(carkcilar_sayfa, title="Çarkçılar", icon="🔧"),
               st.Page(izinler_sayfa, title="İzinler", icon="🏖️"),
               st.Page(oneri_sayfa, title="Yerine Görevlendirme", icon="🤝"),
               st.Page(bildirimler_sayfa, title="Bildirimler", icon="🔔")]).run()
