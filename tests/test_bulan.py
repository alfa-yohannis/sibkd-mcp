"""Uji penguraian bulan dan tanggal sebagaimana ditulis SIBKD dan pemakainya."""

from __future__ import annotations

from datetime import date

import pytest

from sibkd_mcp.bulan import (
    bulan_dalam_label,
    slug_bulan,
    tahun_dalam_label,
    tanggal_iso,
    urai_bulan,
    urai_rentang,
    urai_tanggal,
    waktu_iso,
)


@pytest.mark.parametrize("teks, harapan", [
    ("Oktober 2026", (10, 2026)),
    ("oktober", (10, None)),
    ("  OKTOBER  ", (10, None)),
    ("okt", (10, None)),
    ("October 2026", (10, 2026)),
    ("10", (10, None)),
    ("2026-10", (10, 2026)),
    ("10/2026", (10, 2026)),
    ("Desember 2026", (12, 2026)),
    ("Mei", (5, None)),
    ("agt", (8, None)),
    ("laporan bulan Februari 2027", (2, 2027)),
])
def test_bulan_ditulis_sesukanya(teks, harapan):
    assert urai_bulan(teks) == harapan


@pytest.mark.parametrize("teks", ["", "13", "bulan depan", "2026"])
def test_bulan_yang_tidak_jelas_ditolak(teks):
    with pytest.raises(ValueError):
        urai_bulan(teks)


def test_label_gabungan_menyebut_dua_bulan():
    """SIBKD menggabung November dan Desember jadi satu kartu."""
    assert bulan_dalam_label("November - Desember 2026") == [11, 12]
    assert tahun_dalam_label("November - Desember 2026") == 2026


def test_label_mei_tidak_hilang_walau_tiga_huruf():
    assert bulan_dalam_label("Mei 2026") == [5]


def test_label_tanpa_bulan():
    assert bulan_dalam_label("Jadwal belum diatur") == []
    assert tahun_dalam_label("Jadwal belum diatur") is None


def test_slug_mengikuti_alamat_sibkd():
    assert slug_bulan(10) == "oktober"
    assert slug_bulan(11) == "november"


@pytest.mark.parametrize("teks, harapan", [
    ("7 August 2025", date(2025, 8, 7)),
    (" 7 August 2025", date(2025, 8, 7)),
    ("20 Oktober 2026", date(2026, 10, 20)),
    ("2026-10-02 07:57:09", date(2026, 10, 2)),
    ("10 June 2025", date(2025, 6, 10)),
])
def test_tanggal_dua_bahasa(teks, harapan):
    """Pengumuman memakai bulan bahasa Inggris, bagian lain bahasa Indonesia."""
    assert urai_tanggal(teks) == harapan


def test_tanggal_tidak_jelas_jadi_kosong():
    assert urai_tanggal("kemarin") is None
    assert urai_tanggal("31 Februari 2026") is None
    assert tanggal_iso("") == ""


def test_rentang_jadwal():
    assert urai_rentang("2 Oktober 2026 - 14 Oktober 2026") == ("2026-10-02", "2026-10-14")
    assert urai_rentang("Jadwal belum diatur") == ("", "")


def test_waktu_unggah():
    assert waktu_iso("2026-10-02 07:57:09") == "2026-10-02T07:57:09"
    assert waktu_iso("") == ""
