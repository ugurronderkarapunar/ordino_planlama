"""Neon PostgreSQL bağlantısı ve küçük sorgu yardımcıları."""
from pathlib import Path
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


@st.cache_resource
def engine():
    url = st.secrets["DATABASE_URL"]
    url = url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True, pool_recycle=300)


@st.cache_resource
def init_db():
    """Şemayı bir kez oluşturur."""
    with engine().begin() as c:
        c.exec_driver_sql((Path(__file__).parent / "schema.sql").read_text(encoding="utf-8"))
    return True


def q(sql: str, **p) -> pd.DataFrame:
    with engine().connect() as c:
        return pd.read_sql(text(sql), c, params=p)


def run(sql: str, **p) -> int:
    with engine().begin() as c:
        return c.execute(text(sql), p).rowcount


def tx(*ops):
    """Birden fazla (sql, params) işlemini tek transaction'da çalıştırır."""
    with engine().begin() as c:
        for sql, p in ops:
            c.execute(text(sql), p)


def tr_upper(s) -> str:
    """Türkçe büyük harf (i→İ, ı→I)."""
    return (s or "").strip().replace("i", "İ").replace("ı", "I").upper()
