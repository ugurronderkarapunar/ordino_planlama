-- Neon PostgreSQL şeması (idempotent: uygulama açılışında otomatik çalışır)
CREATE TABLE IF NOT EXISTS gemiler (
    id          SERIAL PRIMARY KEY,
    ad          TEXT NOT NULL UNIQUE,
    tip         TEXT NOT NULL DEFAULT 'disarida' CHECK (tip IN ('tersanede','disarida')),
    makine_tipi TEXT,
    kaptan_adi  TEXT,
    carkci_adi  TEXT
);

CREATE TABLE IF NOT EXISTS carkcilar (
    id                SERIAL PRIMARY KEY,
    isim_soyisim      TEXT NOT NULL UNIQUE,
    calistigi_gemiler INTEGER[] NOT NULL DEFAULT '{}',   -- gemiler.id
    sorunlu_yagcilar  INTEGER[] NOT NULL DEFAULT '{}'    -- personeller.id
);

CREATE TABLE IF NOT EXISTS personeller (
    id              SERIAL PRIMARY KEY,
    isim_soyisim    TEXT NOT NULL UNIQUE,
    vardiya_gunleri DATE[]  NOT NULL DEFAULT '{}',       -- vardiya başlangıç günleri
    vardiya_tipi    TEXT    NOT NULL DEFAULT 'A' CHECK (vardiya_tipi IN ('A','B')),
    makine_bilgisi  TEXT[]  NOT NULL DEFAULT '{}',
    sorunlu_kisiler INTEGER[] NOT NULL DEFAULT '{}',     -- carkcilar.id
    hafta_izni_gunu SMALLINT NOT NULL DEFAULT 6 CHECK (hafta_izni_gunu BETWEEN 0 AND 6), -- 0=Pzt
    gecmis_gemiler  INTEGER[] NOT NULL DEFAULT '{}'      -- gemiler.id
);

CREATE TABLE IF NOT EXISTS izinler (
    id                   SERIAL PRIMARY KEY,
    personel_id          INTEGER NOT NULL REFERENCES personeller(id) ON DELETE CASCADE,
    baslangic_tarihi     DATE NOT NULL,
    bitis_tarihi         DATE NOT NULL,
    toplam_vardiya_sayisi INTEGER NOT NULL,              -- 1 vardiya = 2 gün
    CHECK (bitis_tarihi >= baslangic_tarihi)
);

CREATE TABLE IF NOT EXISTS bildirimler (
    id          SERIAL PRIMARY KEY,
    personel_id INTEGER REFERENCES personeller(id) ON DELETE CASCADE,
    carkci_id   INTEGER REFERENCES carkcilar(id) ON DELETE SET NULL,
    mesaj       TEXT NOT NULL,
    tarih       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_izinler_tarih ON izinler (baslangic_tarihi, bitis_tarihi);
