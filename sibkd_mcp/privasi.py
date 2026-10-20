"""Penyamaran data pribadi sebelum keluar lewat MCP, REST API, atau CLI.

Halaman detail SIBKD menampilkan identitas dosen selengkapnya: NIK KTP, NPWP,
nomor HP, dan tanggal lahir. Data itu milik pemakai sendiri, tetapi begitu
diteruskan ke asisten AI atau aplikasi lain ia ikut tersimpan di riwayat
percakapan, log, dan cache yang tidak dikendalikan pemakai. Karena itu semua
keluaran paket ini hanya menyisakan 4 karakter terakhirnya, cukup untuk
mencocokkan dengan dokumen sendiri tanpa membuka nomornya.

Nominal tunjangan sertifikasi tidak disamarkan: pengumuman SIBKD justru meminta
dosen memeriksa apakah nominal itu sudah sesuai.

Program Python yang memang membutuhkan nilai aslinya bisa membacanya langsung
dari atribut dataclass (`detail.identitas.nik_ktp`), atau memanggil
`sebagai_dict(samarkan=False)`.
"""

from __future__ import annotations

import re

SISA_TERLIHAT = 4

# potongan nama field/label yang menandai data pribadi; dicocokkan per kata
KATA_PRIBADI = {
    "nik", "ktp", "npwp", "hp", "telp", "telepon", "ponsel", "handphone",
    "whatsapp", "wa", "lahir", "alamat", "rekening",
}


def samarkan(nilai: str, sisa: int = SISA_TERLIHAT) -> str:
    """'7371000000001234' -> '************1234'.

    Nilai yang tidak lebih panjang dari `sisa` disamarkan seluruhnya, karena
    menyisakan semua karakternya sama saja dengan tidak menyamarkan.
    """
    teks = str(nilai or "").strip()
    if not teks:
        return ""
    if len(teks) <= sisa:
        return "*" * len(teks)
    return "*" * (len(teks) - sisa) + teks[-sisa:]


def termasuk_pribadi(nama: str) -> bool:
    """Apakah nama field atau label ('NIK KTP', 'no_hp', 'Tgl Lahir') menandai data pribadi."""
    kata = re.split(r"[^a-z0-9]+", (nama or "").lower())
    return any(satu in KATA_PRIBADI for satu in kata if satu)


def samarkan_pasangan(pasangan: list[dict]) -> list[dict]:
    """Daftar {label, nilai} dengan nilai berlabel pribadi disamarkan."""
    return [
        satu | {"nilai": samarkan(satu.get("nilai", ""))} if termasuk_pribadi(satu.get("label", "")) else dict(satu)
        for satu in pasangan
    ]
