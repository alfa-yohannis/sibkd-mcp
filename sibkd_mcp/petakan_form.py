"""Petakan halaman SIBKD: form, field, tabel, dan endpoint yang dipanggil skripnya.

Dipakai saat menyiapkan kemampuan baru. SIBKD menaruh sebagian besar alamat
endpoint di variabel JavaScript (`var apiurl = "https://.../api_jafung" + ...`),
bukan di atribut form, jadi semua string berawalan alamat SIBKD di skrip
halaman ikut didaftar. Skrip ini hanya melakukan GET, tidak pernah mengirim data.

Pakai:
    ./sibkd petakan /dosen/bkdsister_v2
    ./sibkd petakan /dosen/bkdsister_v2/detail/20/oktober --semua-opsi
"""

from __future__ import annotations

import json
import re
import sys

import requests
from bs4 import BeautifulSoup

from sibkd_mcp.detail_laporan import skrip_sebaris
from sibkd_mcp.konfigurasi import KonfigurasiError, simpan_ke_data
from sibkd_mcp.sibkd_client import KlienSibkd, SibkdError, galat_jaringan

MAKS_OPSI_TAMPIL = 12
POLA_AJAX = re.compile(r"""url\s*:\s*[`'"]([^`'"]+)[`'"]""")
# data pribadi di halaman detail tidak boleh ikut tersimpan ke berkas peta
POLA_ANGKA_PANJANG = re.compile(r"\b\d{12,}\b")


def ringkas_field(field, *, semua_opsi: bool) -> dict:
    """Ringkas satu <input>/<select>/<textarea> jadi dict yang enak dibaca.

    Nilai field tidak ikut disalin kecuali pendek: halaman SIBKD mengisi field
    tersembunyi dengan data pribadi (mis. tanggal lahir di halaman lama).
    """
    nilai = field.get("value", "") or ""
    ringkasan = {
        "tag": field.name,
        "name": field.get("name"),
        "id": field.get("id"),
        "type": field.get("type", "select" if field.name == "select" else field.name),
        "value": POLA_ANGKA_PANJANG.sub("<angka>", nilai[:40]),
    }
    if field.name == "select":
        opsi = [
            {"value": pilihan.get("value", ""), "label": pilihan.get_text(strip=True)}
            for pilihan in field.find_all("option")
        ]
        ringkasan["jumlah_opsi"] = len(opsi)
        ringkasan["opsi"] = opsi if semua_opsi else opsi[:MAKS_OPSI_TAMPIL]
    return ringkasan


def ringkas_form(form, *, semua_opsi: bool) -> dict:
    """Ringkas satu <form> beserta seluruh field-nya."""
    field = form.find_all(["input", "select", "textarea"])
    return {
        "id": form.get("id"),
        "action": form.get("action", ""),
        "method": (form.get("method") or "get").upper(),
        "jumlah_field": len(field),
        "field": [ringkas_field(satu, semua_opsi=semua_opsi) for satu in field if satu.get("name")],
    }


def endpoint_skrip(skrip: str, base_url: str) -> list[str]:
    """Alamat SIBKD yang disebut skrip halaman, baik di `url:` maupun di variabel."""
    ditemukan = set(POLA_AJAX.findall(skrip))
    ditemukan.update(re.findall(re.escape(base_url) + r"""[^"'`\s]*""", skrip))
    return sorted(satu for satu in ditemukan if "logout" not in satu)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    path = sys.argv[1]
    semua_opsi = "--semua-opsi" in sys.argv

    klien = KlienSibkd().login()
    jawaban = klien.ambil_halaman(path)
    sup = BeautifulSoup(jawaban.text, "lxml")

    laporan = {
        "url": jawaban.url,
        "status": jawaban.status_code,
        "judul": sup.title.get_text(strip=True) if sup.title else "",
        "form": [ringkas_form(form, semua_opsi=semua_opsi) for form in sup.find_all("form")],
        "endpoint_skrip": endpoint_skrip(skrip_sebaris(sup), klien.base_url),
        "id_tombol": sorted({tombol.get("id") for tombol in sup.find_all(["button", "a"]) if tombol.get("id")}),
        "tabel": [
            {"kelas": tabel.get("class"), "kolom": [th.get_text(" ", strip=True) for th in tabel.find_all("th")]}
            for tabel in sup.find_all("table")
        ],
    }

    print(json.dumps(laporan, ensure_ascii=False, indent=2)[:6000])
    nama_aman = path.strip("/").replace("/", "_") or "beranda"
    simpan_ke_data(f"form_{nama_aman}.json", laporan)
    return 0


def jalankan() -> int:
    """Titik masuk perintah `sibkd-petakan`."""
    try:
        return main()
    except (SibkdError, KonfigurasiError) as galat:
        print(f"Gagal: {galat}", file=sys.stderr)
        return 1
    except requests.RequestException as galat:
        print(f"Gagal: {galat_jaringan(galat)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(jalankan())
