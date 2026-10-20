"""Nama bulan dan tanggal sebagaimana ditulis SIBKD dan pemakainya.

SIBKD mencampur dua bahasa: jadwal dan nama bulan laporan berbahasa Indonesia
("2 Oktober 2026 - 14 Oktober 2026"), sedangkan tanggal pengumuman berbahasa
Inggris ("7 August 2025"). Pemakai sendiri menulis bulan sesukanya: "Oktober
2026", "oktober", "okt", "10", atau "2026-10". Semua itu diurai di sini supaya
modul lain cukup bekerja dengan nomor bulan dan tanggal ISO.

Slug bulan pada alamat halaman detail SIBKD berupa nama bulan Indonesia huruf
kecil (`/dosen/bkdsister_v2/detail/20/oktober`). Slug itu sengaja tidak disusun
dari nama bulan di sini, melainkan diambil dari tautan pada tabel status: bulan
November dan Desember digabung menjadi satu kartu bertautan `november`.
"""

from __future__ import annotations

import re
from datetime import date, datetime

BULAN_INDONESIA = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

BULAN_INGGRIS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _kamus_bulan() -> dict[str, int]:
    """Semua ejaan bulan yang dikenali, huruf kecil, beserta nomornya."""
    kamus: dict[str, int] = {}
    for nomor, (indonesia, inggris) in enumerate(zip(BULAN_INDONESIA, BULAN_INGGRIS), start=1):
        for ejaan in (indonesia, inggris):
            kamus[ejaan.lower()] = nomor
            kamus[ejaan[:3].lower()] = nomor
    # singkatan Indonesia yang tidak sama dengan tiga huruf pertama
    kamus.update({"agt": 8, "ags": 8, "sept": 9, "nop": 11, "nopember": 11, "pebruari": 2})
    return kamus


KAMUS_BULAN = _kamus_bulan()
# nama lengkap saja; label SIBKD tidak pernah menyingkat nama bulan
NAMA_LENGKAP = {nama.lower() for nama in BULAN_INDONESIA + BULAN_INGGRIS}
POLA_KATA = re.compile(r"[a-zA-Z]+")
POLA_TAHUN = re.compile(r"\b(?:19|20)\d{2}\b")


def nama_bulan(nomor: int) -> str:
    """10 -> 'Oktober'."""
    return BULAN_INDONESIA[nomor - 1]


def slug_bulan(nomor: int) -> str:
    """10 -> 'oktober'; bentuk yang dipakai alamat halaman detail SIBKD."""
    return BULAN_INDONESIA[nomor - 1].lower()


def nomor_bulan(kata: str) -> int | None:
    """'Oktober', 'okt', 'October' -> 10; kata yang bukan bulan -> None."""
    return KAMUS_BULAN.get((kata or "").strip().lower())


def urai_bulan(teks: str) -> tuple[int, int | None]:
    """Bulan yang dimaksud pemakai, sebagai (nomor bulan, tahun atau None).

        "Oktober 2026" -> (10, 2026)      "oktober" -> (10, None)
        "10"           -> (10, None)      "2026-10" -> (10, 2026)
        "10/2026"      -> (10, 2026)      "okt 2026" -> (10, 2026)

    Teks yang tidak bisa dipahami ditolak dengan ValueError, bukan ditebak.
    """
    asli = (teks or "").strip()
    if not asli:
        raise ValueError("Bulan belum diisi")

    angka = re.fullmatch(r"(\d{4})[-/](\d{1,2})|(\d{1,2})(?:[-/](\d{4}))?", asli)
    if angka:
        if angka.group(1):
            tahun, nomor = int(angka.group(1)), int(angka.group(2))
        else:
            nomor = int(angka.group(3))
            tahun = int(angka.group(4)) if angka.group(4) else None
        if 1 <= nomor <= 12:
            return nomor, tahun
        raise ValueError(f"Nomor bulan harus 1 sampai 12, bukan {nomor}")

    nomor_ditemukan = [nomor_bulan(kata) for kata in POLA_KATA.findall(asli)]
    nomor_ditemukan = [nomor for nomor in nomor_ditemukan if nomor]
    if not nomor_ditemukan:
        raise ValueError(f"Tidak mengenali bulan dalam {asli!r}; tulis mis. 'Oktober 2026' atau 'oktober'")
    tahun = POLA_TAHUN.search(asli)
    return nomor_ditemukan[0], int(tahun.group(0)) if tahun else None


def bulan_dalam_label(label: str) -> list[int]:
    """Nomor bulan yang disebut sebuah label: 'November - Desember 2026' -> [11, 12]."""
    hasil: list[int] = []
    for kata in POLA_KATA.findall(label or ""):
        nomor = nomor_bulan(kata) if kata.lower() in NAMA_LENGKAP else None
        if nomor and nomor not in hasil:
            hasil.append(nomor)
    return hasil


def tahun_dalam_label(label: str) -> int | None:
    """Tahun terakhir yang disebut label: 'November - Desember 2026' -> 2026."""
    semua = POLA_TAHUN.findall(label or "")
    return int(semua[-1]) if semua else None


def urai_tanggal(teks: str) -> date | None:
    """Tanggal dari teks SIBKD; None kalau tidak berbentuk tanggal.

        "7 August 2025", "20 Oktober 2026", "2026-10-02", "2026-10-02 07:57:09"
    """
    teks = (teks or "").strip()
    iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", teks)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    bagian = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", teks)
    if bagian:
        nomor = nomor_bulan(bagian.group(2))
        if nomor:
            try:
                return date(int(bagian.group(3)), nomor, int(bagian.group(1)))
            except ValueError:
                return None
    return None


def tanggal_iso(teks: str) -> str:
    """Seperti urai_tanggal, tetapi hasilnya teks ISO atau kosong."""
    tanggal = urai_tanggal(teks)
    return tanggal.isoformat() if tanggal else ""


def urai_rentang(teks: str) -> tuple[str, str]:
    """'2 Oktober 2026 - 14 Oktober 2026' -> ('2026-10-02', '2026-10-14').

    Jadwal yang belum diatur ("Jadwal belum diatur") menghasilkan dua teks kosong.
    """
    bagian = [satu.strip() for satu in re.split(r"\s+-\s+|\s+s\.?d\.?\s+", teks or "") if satu.strip()]
    if len(bagian) != 2:
        return "", ""
    return tanggal_iso(bagian[0]), tanggal_iso(bagian[1])


def waktu_iso(teks: str) -> str:
    """'2026-10-02 07:57:09' -> '2026-10-02T07:57:09'; selain itu kosong."""
    try:
        return datetime.strptime((teks or "").strip(), "%Y-%m-%d %H:%M:%S").isoformat()
    except ValueError:
        return ""
