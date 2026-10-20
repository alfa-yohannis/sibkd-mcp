"""Uji penyamaran data pribadi."""

from __future__ import annotations

from sibkd_mcp.privasi import samarkan, samarkan_pasangan, termasuk_pribadi


def test_hanya_empat_karakter_terakhir_yang_tersisa():
    assert samarkan("3210000000001234") == "************1234"
    assert samarkan("1990-01-31") == "******1-31"


def test_spasi_di_ujung_tidak_ikut_dihitung():
    """Kotak NPWP di SIBKD membawa spasi di ujungnya."""
    assert samarkan("000000000005678 ") == "***********5678"


def test_nilai_pendek_disamarkan_seluruhnya():
    """Menyisakan empat karakter dari nilai empat karakter sama saja membukanya."""
    assert samarkan("1234") == "****"
    assert samarkan("") == ""
    assert samarkan(None) == ""


def test_label_pribadi_dikenali():
    for label in ("NIK KTP", "NPWP", "No. HP", "Tgl Lahir", "no_hp", "Alamat Rumah", "Nomor Rekening"):
        assert termasuk_pribadi(label), label
    for label in ("Nama Dosen", "NIDN", "Pangkat/Gol. Penyetaraan", "Penyetaraan Pembayaran Tunjangan Sertifikasi"):
        assert not termasuk_pribadi(label), label


def test_pasangan_berlabel_pribadi_disamarkan():
    hasil = samarkan_pasangan([
        {"label": "No. HP", "nilai": "081200009876"},
        {"label": "Penyetaraan Pembayaran Tunjangan Sertifikasi", "nilai": "Rp. 1.234.500"},
    ])

    assert hasil[0]["nilai"] == "********9876"
    assert hasil[1]["nilai"] == "Rp. 1.234.500"
